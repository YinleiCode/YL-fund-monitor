"""
AKShare 数据获取，带可配置 fallback 和本地缓存。

数据源策略（由 config.yaml data_source.prefer_source 控制）：
  auto       东方财富优先，失败后新浪兜底（默认）
  eastmoney  只用东方财富，失败报错
  sina       直接用新浪

全市场快照三级 fallback（auto 模式）：
  1. ak.stock_zh_a_spot_em()        东方财富 AKShare
  2. push2delay.eastmoney.com clist 东方财富直连（绕过代理）
  3. ak.stock_zh_a_spot()           新浪财经（盘前/盘后均有效，无换手率）

历史K线三级 fallback（auto 模式）：
  1. ak.stock_zh_a_hist()           东方财富 AKShare
  2. push2delay.eastmoney.com kline 东方财富直连（绕过代理）
  3. ak.stock_zh_a_daily()          新浪财经（稳定）

每次运行结束后可通过 get_run_provenance() 查询数据源溯源记录。
"""
import json
import os
import re
import time
import logging
import ssl
import socket
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests as _requests

import data_cache as cache

logger = logging.getLogger(__name__)

_DELAY_HOST = "push2delay.eastmoney.com"

try:
    import akshare as ak
    _AKSHARE_OK = True
except ImportError:
    _AKSHARE_OK = False
    logger.warning("AKShare 未安装，将全部使用 fallback 接口")


# =================== 数据源溯源 ===================

_provenance: dict = {
    "spot_source_used": None,
    "hist_source_used": None,
    "fallback_used":    False,
    "fallback_reason":  None,
    "price_adjustment": "unadjusted",
    "is_stale_cache":   False,         # 是否使用了过期缓存（不参与正式买入确认）
    "stale_cache_date": None,          # 缓存对应的交易日
    "spot_attempts":    [],            # [(source_name, ok|error_msg), ...]
}
_hist_source_detail: Dict[str, str] = {}


def reset_run_provenance() -> None:
    global _provenance, _hist_source_detail
    _provenance = {
        "spot_source_used": None,
        "hist_source_used": None,
        "fallback_used":    False,
        "fallback_reason":  None,
        "price_adjustment": "unadjusted",
        "is_stale_cache":   False,
        "stale_cache_date": None,
        "spot_attempts":    [],
    }
    _hist_source_detail = {}


def get_run_provenance() -> dict:
    """返回本次运行的数据源溯源信息（已聚合历史K线统计）。"""
    prov = _provenance.copy()
    if _hist_source_detail:
        em_cnt   = sum(1 for v in _hist_source_detail.values() if "eastmoney" in v)
        sina_cnt = sum(1 for v in _hist_source_detail.values() if "sina" in v)
        total    = len(_hist_source_detail)
        if sina_cnt == 0:
            prov["hist_source_used"] = "eastmoney"
        elif em_cnt == 0:
            prov["hist_source_used"] = "sina"
        else:
            prov["hist_source_used"] = f"mixed ({em_cnt}东方财富/{sina_cnt}新浪)"
        prov["hist_eastmoney_count"] = em_cnt
        prov["hist_sina_count"]      = sina_cnt
        prov["hist_total_count"]     = total
    return prov


# =================== 底层工具 ===================

def _prev_weekday(d: date) -> date:
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _next_weekday(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def calc_dates() -> Tuple[str, str]:
    """
    返回 (data_date, report_date)，格式 YYYYMMDD。
    data_date  = 实际行情数据日期（收盘数据来源日）
    report_date = 本报告对应的盘前交易日
    """
    now     = datetime.now()
    today   = now.date()
    weekday = today.weekday()

    if weekday >= 5:
        data_date   = _prev_weekday(today)
        report_date = _next_weekday(today)
    elif now.hour >= 15:
        data_date   = today
        report_date = _next_weekday(today)
    else:
        data_date   = _prev_weekday(today)
        report_date = today

    return data_date.strftime("%Y%m%d"), report_date.strftime("%Y%m%d")


def _last_trading_date() -> str:
    return calc_dates()[0]


def next_trading_date(date_str: str) -> str:
    """返回 date_str 的下一个交易日（仅排除周末，不含节假日）。"""
    d = datetime.strptime(date_str, "%Y%m%d").date()
    return _next_weekday(d).strftime("%Y%m%d")


def _retry(fn, *args, retries=3, delay=2, **kwargs):
    for i in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if i < retries - 1:
                logger.warning(f"第{i+1}次请求失败: {e}，{delay}秒后重试...")
                time.sleep(delay)
            else:
                raise


def _raw_get(host: str, path: str, timeout: int = 20) -> bytes:
    """直接用 SSL socket 发 GET，绕过 requests/urllib3 代理。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ip = socket.gethostbyname(host)
    s  = socket.create_connection((ip, 443), timeout=timeout)
    ss = ctx.wrap_socket(s, server_hostname=host)
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: Mozilla/5.0\r\n"
        "Accept: application/json\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    ss.send(req)
    chunks = []
    while True:
        chunk = ss.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    ss.close()
    raw = b"".join(chunks)
    if b"\r\n\r\n" in raw:
        body = raw.split(b"\r\n\r\n", 1)[1]
        if b"\r\n" in body and body[:10].strip().replace(b"\r\n", b"").isalnum():
            try:
                lines   = body.split(b"\r\n")
                decoded = b"".join(lines[i] for i in range(1, len(lines), 2) if i < len(lines))
                if decoded.strip().startswith(b"{"):
                    return decoded
            except Exception:
                pass
        return body
    return raw


def _build_query(params: dict) -> str:
    return "&".join(f"{k}={v}" for k, v in params.items())


# =================== 全市场快照 — 各数据源 ===================

def _spot_via_akshare() -> Optional[pd.DataFrame]:
    if not _AKSHARE_OK:
        return None
    df = _retry(ak.stock_zh_a_spot_em, retries=2, delay=2)
    return df if df is not None and not df.empty else None


def _spot_via_push2delay() -> pd.DataFrame:
    """push2delay.eastmoney.com 分页拉取（盘中/盘后有效；盘前返回"-"）。"""
    base_params = {
        "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": "m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80",
        "fields": "f12,f14,f2,f3,f5,f6,f8,f9,f10,f15,f16,f17,f18,f20,f23",
    }
    rows = []
    pz   = 500

    params = {**base_params, "pn": 1, "pz": pz}
    path   = "/api/qt/clist/get?" + _build_query(params)
    raw    = _raw_get(_DELAY_HOST, path)
    data   = json.loads(raw)
    total  = data["data"]["total"]
    rows.extend(data["data"]["diff"])
    pages  = (total + pz - 1) // pz
    logger.info(f"push2delay clist: 共 {total} 只，分 {pages} 页")

    for pn in range(2, pages + 1):
        params["pn"] = pn
        path = "/api/qt/clist/get?" + _build_query(params)
        raw  = _raw_get(_DELAY_HOST, path)
        rows.extend(json.loads(raw)["data"]["diff"])
        time.sleep(0.1)

    df = pd.DataFrame(rows).rename(columns={
        "f12": "代码", "f14": "名称",
        "f2": "最新价", "f3": "涨跌幅",
        "f5": "成交量", "f6": "成交额",
        "f8": "换手率", "f9": "市盈率-动态",
        "f10": "量比",  "f15": "最高",
        "f16": "最低",  "f17": "今开",
        "f18": "昨收",  "f20": "总市值",
        "f23": "市净率",
    })
    for col in ["涨跌额", "振幅"]:
        if col not in df.columns:
            df[col] = float("nan")
    return df


def _fetch_simulated_spot() -> pd.DataFrame:
    """
    模拟行情：生成带典型特征的 DataFrame，用于测试/演示。
    不连任何数据源，不影响缓存。
    """
    import random as _r
    _r.seed(42)
    codes  = [f"{i:06d}" for i in range(600000, 600200)]    # 200 只沪市
    codes += [f"{i:06d}" for i in range(1, 101)]            # 100 只深市 000001–000100
    names  = [f"模拟股{i}" for i in range(len(codes))]
    rows   = []
    for code, name in zip(codes, names):
        rows.append({
            "code":          code,
            "name":          name,
            "close":         round(_r.uniform(5, 80), 2),
            "open":          round(_r.uniform(5, 80), 2),
            "high":          round(_r.uniform(5, 80), 2),
            "low":           round(_r.uniform(5, 80), 2),
            "pre_close":     round(_r.uniform(5, 80), 2),
            "amount":        _r.randint(50_000_000, 5_000_000_000),
            "volume":        _r.randint(1_000_000, 100_000_000),
            "change_pct":    round(_r.uniform(-5, 10), 2),
            "turnover_rate": round(_r.uniform(0.5, 30), 2),
        })
    df = pd.DataFrame(rows)
    logger.info(f"[simulate] 生成模拟行情 {len(df)} 只股票")
    return df


def _spot_via_sina() -> pd.DataFrame:
    """
    新浪财经 ak.stock_zh_a_spot()，盘前/盘后均可用（约30秒）。
    换手率新浪不提供，设为 NaN；filters.py 允许 NaN 通过。
    """
    if not _AKSHARE_OK:
        return pd.DataFrame()
    logger.info("新浪 stock_zh_a_spot() 获取全市场行情（约30秒）...")
    df = ak.stock_zh_a_spot()
    if df is None or df.empty:
        return pd.DataFrame()
    df["代码"] = df["代码"].str.replace(r"^[a-z]+", "", regex=True)
    df["换手率"] = float("nan")
    df["振幅"]   = float("nan")
    for col in ["市盈率-动态", "市净率", "量比", "总市值"]:
        if col not in df.columns:
            df[col] = float("nan")
    return df


def _process_spot_raw(raw_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """统一列名、过滤A股代码、转数值类型。返回空 DataFrame 表示无有效数据。"""
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()
    df = raw_df.rename(columns={
        "代码": "code",  "名称": "name",
        "最新价": "close",  "涨跌幅": "change_pct", "涨跌额": "change_amount",
        "成交量": "volume", "成交额": "amount",     "振幅": "amplitude",
        "最高": "high",   "最低": "low",
        "今开": "open",   "昨收": "prev_close",
        "换手率": "turnover_rate",
        "市盈率-动态": "pe", "市净率": "pb",
    })
    df = df[df["code"].astype(str).str.match(r"^[036]\d{5}$")].copy()
    for col in ["close", "change_pct", "amount", "turnover_rate",
                "high", "low", "open", "prev_close"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close", "change_pct", "amount"])
    return df.reset_index(drop=True)


def _is_premarket_garbage(df: Optional[pd.DataFrame]) -> Optional[str]:
    """
    检测行情快照是否为"盘前占位数据"（close/amount/change_pct 几乎全为 0）。
    返回错误说明字符串；返回 None 表示数据健康。
    这是数据质量检查，与选股策略完全无关。
    """
    if df is None or df.empty:
        return "empty"
    try:
        total       = int(len(df))
        valid_close = int((df["close"] > 0).sum()) if "close" in df.columns else 0
        amt_sum     = float(df["amount"].sum()) if "amount" in df.columns else 0.0
        chg_nonzero = (
            int((df["change_pct"].abs() > 0.01).sum())
            if "change_pct" in df.columns else 0
        )
    except Exception as e:
        return f"validation exception: {e}"
    if valid_close < total * 0.5:
        return f"only {valid_close}/{total} rows have close>0 (premarket placeholder)"
    if amt_sum <= 0:
        return "total amount=0 (no trades, premarket placeholder)"
    if chg_nonzero == 0:
        return "all change_pct=0 (premarket placeholder)"
    return None


def _purge_cache_file(key: str, date_str: str) -> None:
    """物理删除一份缓存文件（用于丢弃被检测出来的脏缓存）。"""
    try:
        p = cache._path(key, date_str)  # type: ignore[attr-defined]
        if p.exists():
            p.unlink()
            logger.info(f"已删除脏缓存: {p.name}")
    except Exception as e:
        logger.debug(f"删除缓存文件失败 [{key}/{date_str}]: {e}")


def _is_stale_hist_cache(
    df: Optional[pd.DataFrame], trade_date: str
) -> Optional[str]:
    """
    判断一份 hist DataFrame 是否相对于 trade_date 已经"陈旧"。
    返回 None 表示新鲜；返回字符串表示陈旧（含原因，用于日志）。

    判定口径（明确只看 last_kline 日期，**不看行数**）：
      - df 为 None/空 → 陈旧
      - df 缺 date 列 → 陈旧
      - df 最后一条 K 线日期 != trade_date → 陈旧
      - df 最后一条 K 线日期 == trade_date → 新鲜
    设计说明：
      行数少（新股/次新只有 5、10、20 行）属于结构性真实数据，不算脏；
      只要 last_kline 与 trade_date 严格相等，就视为该批数据涵盖了 trade_date 当日。

    背景：修复 688322 类问题——15:25 update_review 用了 T 日实时数据，
    fetch_stock_history 把"截止 T-1 的数据"按 T 日命名缓存，导致后续重跑读到毒缓存。
    本 helper 让读/写两端都能严格拦截这种情况。

    本函数纯只读，不写文件、不抛异常。
    """
    if df is None:
        return "df is None"
    try:
        if not isinstance(df, pd.DataFrame):
            return f"not a DataFrame (got {type(df).__name__})"
        if df.empty:
            return "df is empty"
        if "date" not in df.columns:
            return f"missing 'date' column (cols={list(df.columns)})"
        last_dt = df["date"].iloc[-1]
        last_str = pd.Timestamp(last_dt).strftime("%Y%m%d")
        if last_str == trade_date:
            return None
        return f"last_kline_date={last_str} != trade_date={trade_date}"
    except Exception as e:
        # 任何异常都视为脏（保守策略，宁可重拉也不读疑似毒数据）
        return f"freshness check error: {type(e).__name__}: {e}"


# =================== 全市场快照 — 主入口 ===================

def _load_recent_market_spot_cache(
    trade_date: str, max_days_back: int = 7
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    向前回溯最多 max_days_back 天，寻找最近一次"健康"的 market_spot 缓存。
    脏缓存（盘前占位 0 值）会被自动跳过且物理删除。
    返回 (DataFrame|None, 命中缓存对应日期|None)。
    """
    try:
        d = datetime.strptime(trade_date, "%Y%m%d").date()
    except ValueError:
        d = date.today()
    for delta in range(0, max_days_back + 1):
        candidate = (d - timedelta(days=delta)).strftime("%Y%m%d")
        df = cache.load("market_spot", candidate)
        if df is None or df.empty:
            continue
        poison = _is_premarket_garbage(df)
        if poison is None:
            return df, candidate
        logger.warning(
            f"[spot] 过期缓存 [{candidate}] 同样为脏数据 ({poison})，删除并继续回溯"
        )
        _purge_cache_file("market_spot", candidate)
    return None, None


def fetch_market_spot(
    trade_date: Optional[str] = None,
    cfg: Optional[dict] = None,
) -> pd.DataFrame:
    """
    获取A股全市场行情快照，多源 fallback + 过期缓存兜底。
    无论 prefer_source 设置如何，full 全A模式都不会只依赖单一数据源：

      prefer=sina      顺序: sina → eastmoney_akshare → eastmoney_push2delay → cache_stale
      prefer=eastmoney 顺序: eastmoney_akshare → eastmoney_push2delay → cache_stale
      prefer=auto      顺序: eastmoney_akshare → eastmoney_push2delay → sina → cache_stale

    若使用过期缓存兜底，会在 _provenance 中标记 is_stale_cache=True，
    调用方应根据该标记决定是否写入 trade_review.csv 并在推送中给出"仅供观察"提示。

    支持模拟模式（Simulate Mode）：
      环境变量 SIMULATE_MODE=true 或 config.yaml data_source.simulate_data=true 时，
      返回模拟行情，不连真实数据源。用于调试/演示/测试。
    """
    # ── 模拟模式检测：优先于一切真实数据源熔断 ──
    sim_env  = os.environ.get("SIMULATE_MODE", "").lower() == "true"
    sim_cfg  = (cfg or {}).get("data_source", {}).get("simulate_data", False)
    if sim_env or sim_cfg:
        return _fetch_simulated_spot()

    if trade_date is None:
        trade_date = _last_trading_date()

    # 当日缓存（同 trade_date）—— 先做数据质量校验再返回，避免读到盘前占位脏数据
    cached = cache.load("market_spot", trade_date)
    if cached is not None and not cached.empty:
        poison = _is_premarket_garbage(cached)
        if poison is None:
            logger.info(f"使用缓存市场行情 [{trade_date}]，共 {len(cached)} 只")
            _provenance.update({
                "spot_source_used": f"cache({trade_date})",
                "spot_attempts":    [("cache_today", "ok")],
            })
            return cached
        logger.warning(
            f"日内缓存 [{trade_date}] 被检测为脏数据 ({poison})，"
            f"删除文件并改用实时数据源"
        )
        _purge_cache_file("market_spot", trade_date)

    ds_cfg          = (cfg or {}).get("data_source", {})
    prefer          = ds_cfg.get("prefer_source", "auto")
    allow_sina      = ds_cfg.get("allow_sina_fallback", True)
    log_src         = ds_cfg.get("log_data_source", True)
    min_spot_count  = ds_cfg.get("min_spot_count", 4000)

    # —— 关键修复：无论 prefer 是什么，full 模式都启用三源 fallback 顺序 ——
    if prefer == "sina":
        sources = [
            ("sina",                 _spot_via_sina),
            ("eastmoney_akshare",    _spot_via_akshare),
            ("eastmoney_push2delay", _spot_via_push2delay),
        ]
    elif prefer == "eastmoney":
        sources = [
            ("eastmoney_akshare",    _spot_via_akshare),
            ("eastmoney_push2delay", _spot_via_push2delay),
        ]
        if allow_sina:
            sources.append(("sina", _spot_via_sina))
    else:  # auto
        sources = [
            ("eastmoney_akshare",    _spot_via_akshare),
            ("eastmoney_push2delay", _spot_via_push2delay),
        ]
        if allow_sina:
            sources.append(("sina", _spot_via_sina))

    processed       = pd.DataFrame()
    src_used        = "none"
    fallback_used   = False
    fallback_reason = None
    attempts: list  = []

    for idx, (src_name, src_fn) in enumerate(sources):
        logger.info(f"[spot] 尝试数据源 {idx+1}/{len(sources)}: {src_name}")
        try:
            raw = src_fn()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            logger.warning(f"[spot] {src_name} 异常: {err}")
            attempts.append((src_name, err))
            fallback_used   = True
            fallback_reason = f"{src_name} 异常({type(e).__name__})"
            continue

        p = _process_spot_raw(raw)
        if p.empty:
            logger.warning(f"[spot] {src_name} 处理后无有效数据，尝试下一源")
            attempts.append((src_name, "empty_after_process"))
            fallback_used   = True
            fallback_reason = f"{src_name} 无有效数据"
            continue

        # 数据完整性检查：返回行数过少时也视为失败，切到下一源
        if len(p) < min_spot_count and src_name != "sina":
            msg = f"only {len(p)} rows (< min_spot_count={min_spot_count})"
            logger.warning(f"[spot] {src_name} {msg}，尝试下一源")
            attempts.append((src_name, msg))
            fallback_used   = True
            fallback_reason = f"{src_name} {msg}"
            continue

        # 数据质量校验：拒绝盘前占位（close/amount/change_pct 全 0）
        poison = _is_premarket_garbage(p)
        if poison is not None:
            logger.warning(
                f"[spot] {src_name} 返回盘前占位数据 ({poison})，尝试下一源"
            )
            attempts.append((src_name, f"premarket_garbage: {poison}"))
            fallback_used   = True
            fallback_reason = f"{src_name} pre-market placeholder ({poison})"
            continue

        attempts.append((src_name, f"ok ({len(p)} rows)"))
        processed = p
        src_used  = src_name
        if idx > 0:
            fallback_used = True
        break

    # —— 所有实时源失败：尝试过期缓存兜底 ——
    if processed.empty:
        logger.warning("[spot] 所有实时数据源失败，尝试过期缓存兜底...")
        stale_df, stale_date = _load_recent_market_spot_cache(trade_date)
        if stale_df is not None and stale_date is not None:
            logger.warning(
                f"[spot] 命中过期缓存 cache_stale (date={stale_date}, "
                f"共 {len(stale_df)} 只) —— 仅供观察，不参与正式买入确认"
            )
            attempts.append(("cache_stale", f"ok ({stale_date}, {len(stale_df)} rows)"))
            _provenance.update({
                "spot_source_used": "cache_stale",
                "fallback_used":    True,
                "fallback_reason":  fallback_reason or "所有实时数据源失败，使用过期缓存",
                "is_stale_cache":   True,
                "stale_cache_date": stale_date,
                "spot_attempts":    attempts,
            })
            if log_src:
                logger.info(
                    f"市场行情就绪：{len(stale_df)} 只A股  "
                    f"[source=cache_stale  date={stale_date}]  "
                    f"⚠️ 今日行情接口失败，使用缓存，仅供观察，不参与正式买入确认"
                )
            return stale_df

        # 缓存也没有 —— 彻底失败
        attempts.append(("cache_stale", "miss"))
        logger.error(
            f"所有数据源均失败，市场行情为空 (prefer={prefer})；"
            f"尝试记录: {attempts}"
        )
        _provenance.update({
            "spot_source_used": "none",
            "fallback_used":    True,
            "fallback_reason":  fallback_reason or "所有数据源失败且无可用缓存",
            "is_stale_cache":   False,
            "stale_cache_date": None,
            "spot_attempts":    attempts,
        })
        return pd.DataFrame()

    if log_src:
        fb = f"  [fallback: {fallback_reason}]" if fallback_used else ""
        logger.info(
            f"市场行情就绪：{len(processed)} 只A股  [source={src_used}]{fb}  "
            f"尝试记录: {attempts}"
        )

    _provenance.update({
        "spot_source_used": src_used,
        "fallback_used":    _provenance["fallback_used"] or fallback_used,
        "fallback_reason":  fallback_reason or _provenance["fallback_reason"],
        "is_stale_cache":   False,
        "stale_cache_date": None,
        "spot_attempts":    attempts,
    })

    cache.save("market_spot", processed, trade_date)
    return processed


# =================== 实时行情（单股快速接口） ===================

def fetch_realtime_spot(codes: List[str]) -> pd.DataFrame:
    """
    获取指定股票实时行情（新浪 hq.sinajs.cn，毫秒级）。
    用于 --check-buy 在9:36获取开盘价和当前价。
    返回列：code, name, open, prev_close, close, high, low, volume, amount
    """
    def _to_sina(code: str) -> str:
        return f"sh{code}" if code.startswith(("6", "5")) else f"sz{code}"

    codes_clean = [str(c).zfill(6) for c in codes]
    sina_list   = ",".join(_to_sina(c) for c in codes_clean)
    url         = f"https://hq.sinajs.cn/list={sina_list}"
    headers     = {"Referer": "https://finance.sina.com.cn"}

    for attempt in range(2):
        try:
            resp = _requests.get(url, headers=headers, timeout=10)
            resp.encoding = "gbk"
            text = resp.text
            break
        except Exception as e:
            if attempt == 0:
                logger.warning(f"fetch_realtime_spot 第1次失败: {e}，重试...")
                time.sleep(2)
            else:
                logger.error(f"fetch_realtime_spot 失败: {e}")
                return pd.DataFrame()

    rows = []
    for line in text.strip().split("\n"):
        m = re.match(r'var hq_str_(\w+)="(.*)"', line.strip())
        if not m:
            continue
        sina_code = m.group(1)          # e.g. sh600519
        fields    = m.group(2).split(",")
        if len(fields) < 10 or not fields[0]:
            continue
        code = sina_code[2:].zfill(6)   # strip sh/sz prefix
        try:
            rows.append({
                "code":       code,
                "name":       fields[0],
                "open":       float(fields[1]),
                "prev_close": float(fields[2]),
                "close":      float(fields[3]),
                "high":       float(fields[4]),
                "low":        float(fields[5]),
                "volume":     float(fields[8]),  # 成交量（手）
                "amount":     float(fields[9]),  # 成交额（元）
            })
        except (ValueError, IndexError):
            logger.warning(f"fetch_realtime_spot 解析失败: {sina_code}")

    if not rows:
        logger.warning("fetch_realtime_spot 未解析到任何数据")
    return pd.DataFrame(rows)


# =================== 历史K线 — 各数据源 ===================

def _secid(code: str) -> str:
    return f"1.{code}" if code.startswith(("6", "5")) else f"0.{code}"


def _hist_via_push2delay(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """push2delay.eastmoney.com kline 接口（当前环境下 klines 常为空）。"""
    secid  = _secid(symbol)
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": 101, "fqt": 0,
        "secid": secid,
        "beg": start_date, "end": end_date,
    }
    path   = "/api/qt/stock/kline/get?" + _build_query(params)
    raw    = _raw_get(_DELAY_HOST, path)
    if not raw:
        return None
    data   = json.loads(raw)
    klines = data.get("data", {}).get("klines")
    if not klines:
        return None
    records = []
    for line in klines:
        p = line.split(",")
        if len(p) < 11:
            continue
        records.append({
            "date":          pd.to_datetime(p[0]),
            "open":          float(p[1]),
            "close":         float(p[2]),
            "high":          float(p[3]),
            "low":           float(p[4]),
            "volume":        float(p[5]),
            "amount":        float(p[6]),
            "amplitude":     float(p[7]),
            "change_pct":    float(p[8]),
            "change_amount": float(p[9]),
            "turnover_rate": float(p[10]),
        })
    return pd.DataFrame(records) if records else None


def _hist_via_sina(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """新浪财经 ak.stock_zh_a_daily()，不复权，稳定可用。"""
    if not _AKSHARE_OK:
        return None
    prefix = "sh" if symbol.startswith(("6", "5")) else "sz"
    df     = ak.stock_zh_a_daily(symbol=f"{prefix}{symbol}", adjust="")
    if df is None or df.empty:
        return None
    df = df.tail(days).copy()
    df["change_pct"]    = (df["close"] / df["close"].shift(1) - 1) * 100
    df["change_amount"] = df["close"] - df["close"].shift(1)
    df["turnover_rate"] = df["turnover"] * 100
    df["amplitude"]     = float("nan")
    df["date"]          = pd.to_datetime(df["date"])
    return df[["date", "open", "close", "high", "low", "volume",
               "amount", "amplitude", "change_pct", "change_amount", "turnover_rate"]]


# =================== 历史K线 — 主入口 ===================

def fetch_stock_history(
    symbol: str,
    days: int = 80,
    trade_date: Optional[str] = None,
    cfg: Optional[dict] = None,
) -> Optional[pd.DataFrame]:
    """
    获取个股历史日K线（不复权），带三级 fallback。
    """
    if trade_date is None:
        trade_date = _last_trading_date()

    key    = f"hist_{symbol}"
    cached = cache.load(key, trade_date)
    if cached is not None:
        # —— hist 缓存新鲜度校验（修复 688322 类毒缓存问题）——
        # 仅 hist 缓存做此校验；market_spot / money_flow 等其它缓存不受影响。
        stale_reason = _is_stale_hist_cache(cached, trade_date)
        if stale_reason:
            logger.warning(
                f"[hist-cache] {symbol} 命中缓存但已陈旧，丢弃并重新拉取: {stale_reason}"
            )
            _purge_cache_file(key, trade_date)
            cached = None   # 视为未命中，进入下面正常拉取流程
        else:
            return cached

    ds_cfg     = (cfg or {}).get("data_source", {})
    prefer     = ds_cfg.get("prefer_source", "auto")
    allow_sina = ds_cfg.get("allow_sina_fallback", True)

    end_str   = date.today().strftime("%Y%m%d")
    start_str = (date.today() - timedelta(days=days * 2 + 30)).strftime("%Y%m%d")
    window    = days * 2 + 30

    def _try_akshare() -> Optional[pd.DataFrame]:
        if not _AKSHARE_OK:
            return None
        df = _retry(
            ak.stock_zh_a_hist,
            symbol=symbol, period="daily",
            start_date=start_str, end_date=end_str,
            adjust="",
            retries=2, delay=1,
        )
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "日期": "date",  "开盘": "open",  "收盘": "close",
            "最高": "high",  "最低": "low",   "成交量": "volume",
            "成交额": "amount", "振幅": "amplitude",
            "涨跌幅": "change_pct", "涨跌额": "change_amount",
            "换手率": "turnover_rate",
        })
        return df if "date" in df.columns else None

    def _try_push2delay() -> Optional[pd.DataFrame]:
        return _hist_via_push2delay(symbol, start_str, end_str)

    def _try_sina() -> Optional[pd.DataFrame]:
        return _hist_via_sina(symbol, window)

    if prefer == "sina":
        attempts = [("sina", _try_sina)]
    elif prefer == "eastmoney":
        attempts = [
            ("eastmoney_akshare",    _try_akshare),
            ("eastmoney_push2delay", _try_push2delay),
        ]
    else:  # auto
        attempts = [
            ("eastmoney_akshare",    _try_akshare),
            ("eastmoney_push2delay", _try_push2delay),
        ]
        if allow_sina:
            attempts.append(("sina", _try_sina))

    raw_df   = None
    src_used = None

    for src_name, src_fn in attempts:
        try:
            raw_df = src_fn()
        except Exception as e:
            logger.debug(f"{symbol} [{src_name}] 异常: {e}")
            continue
        if raw_df is not None and not raw_df.empty:
            src_used = src_name
            break

    if raw_df is None or raw_df.empty or src_used is None:
        return None

    if "date" not in raw_df.columns:
        logger.warning(f"{symbol}: 历史数据缺少 date 列，列名: {list(raw_df.columns)}")
        return None

    raw_df["date"] = pd.to_datetime(raw_df["date"])
    raw_df = raw_df.sort_values("date").tail(days).reset_index(drop=True)

    _hist_source_detail[symbol] = src_used

    # —— 写缓存前再做一次新鲜度校验，避免源数据本身就"陈旧"导致毒化下次 ——
    # 典型场景：盘前抢跑（08:00 前跑），数据源仅返回截止 T-1 的 K 线；
    # 若按 T 日命名写盘，会污染当日缓存。写前拦截，宁可不写也不写脏。
    # 注意：返回值 raw_df 仍正常返回给调用方（业务可见，仅"缓存"被抑制）。
    stale_reason = _is_stale_hist_cache(raw_df, trade_date)
    if stale_reason:
        logger.warning(
            f"[hist-cache] {symbol} 拒绝写入陈旧数据（避免毒化缓存）: {stale_reason}"
        )
    else:
        cache.save(key, raw_df, trade_date)
    return raw_df


def fetch_batch_history(
    symbols: List[str],
    days: int = 80,
    trade_date: Optional[str] = None,
    delay: float = 0.2,
    cfg: Optional[dict] = None,
) -> Dict[str, Optional[pd.DataFrame]]:
    """批量获取历史数据，带速率限制。完成后聚合数据源统计到 _provenance。"""
    if trade_date is None:
        trade_date = _last_trading_date()

    results: Dict[str, Optional[pd.DataFrame]] = {}
    total = len(symbols)
    logger.info(f"开始拉取 {total} 只股票历史数据...")

    for i, sym in enumerate(symbols, 1):
        results[sym] = fetch_stock_history(sym, days=days, trade_date=trade_date, cfg=cfg)
        if i % 10 == 0 or i == total:
            ok = sum(1 for v in results.values() if v is not None)
            logger.info(f"  进度: {i}/{total}，成功 {ok} 只")
        time.sleep(delay)

    # 聚合 hist fallback 信息到 _provenance
    if _hist_source_detail:
        sina_cnt = sum(1 for v in _hist_source_detail.values() if "sina" in v)
        if sina_cnt > 0 and not _provenance["fallback_used"]:
            _provenance["fallback_used"] = True
            _provenance["fallback_reason"] = (
                _provenance.get("fallback_reason") or
                f"历史K线 {sina_cnt}/{total} 只用新浪 fallback"
            )

    return results


# =================== 涨停/炸板池（市场情绪） ===================

def fetch_limit_up_pool(trade_date: str) -> Optional[pd.DataFrame]:
    cached = cache.load("zt_pool", trade_date)
    if cached is not None:
        return cached
    if not _AKSHARE_OK:
        return None
    try:
        df = _retry(ak.stock_zt_pool_em, date=trade_date)
        if df is not None and not df.empty:
            cache.save("zt_pool", df, trade_date)
        return df
    except Exception as e:
        logger.warning(f"涨停池获取失败 [{trade_date}]: {e}")
        return None


def fetch_burst_board_pool(trade_date: str) -> Optional[pd.DataFrame]:
    cached = cache.load("zbgc_pool", trade_date)
    if cached is not None:
        return cached
    if not _AKSHARE_OK:
        return None
    try:
        df = _retry(ak.stock_zt_pool_zbgc_em, date=trade_date)
        if df is not None and not df.empty:
            cache.save("zbgc_pool", df, trade_date)
        return df
    except Exception as e:
        logger.warning(f"炸板池获取失败 [{trade_date}]: {e}")
        return None


# =================== 上证指数 ===================

def fetch_sh_index_change(trade_date: str) -> float:
    cached = cache.load("sh_index_chg", trade_date)
    if cached is not None:
        return cached
    if not _AKSHARE_OK:
        return 0.0
    try:
        end   = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=10)).strftime("%Y%m%d")
        df    = _retry(ak.index_zh_a_hist, symbol="000001", period="daily",
                       start_date=start, end_date=end)
        if df is None or df.empty:
            return 0.0
        chg_col = next((c for c in df.columns if "涨跌幅" in c), None)
        if chg_col is None:
            return 0.0
        chg = float(df[chg_col].iloc[-1])
        cache.save("sh_index_chg", chg, trade_date)
        return chg
    except Exception as e:
        logger.warning(f"上证指数获取失败: {e}")
        return 0.0


def last_trading_date() -> str:
    return _last_trading_date()
