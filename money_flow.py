"""
money_flow.py — V1.5-alpha 资金流独立模块
==========================================

设计目标
--------
为后续 V1.5 "资金健康作为买入必选条件" 做准备。本模块**只读、独立**：
  - 不被任何 V1.4 主流程（run.py / check_buy / theme_auto / scorer 等）引用
  - 不写 trade_review.csv
  - 不影响任何已有买入/卖出/复盘逻辑
  - 仅在自带 cache/money_flow/ 下读写每日缓存文件

技术细节
--------
1. 复用 data_fetcher._raw_get（已在本机验证可绕过 RemoteDisconnected）。
2. 调用 push2his.eastmoney.com 资金流端点（akshare.stock_individual_fund_flow 同源）。
3. 缓存文件：cache/money_flow/{code}_{YYYYMMDD}.json，同日重复查询命中缓存。

第一版资金健康规则
------------------
近 3 日主力净流入天数 >= 2  且  累计主力净流入 > 0  → is_healthy = True

CLI
---
    python -m money_flow probe 688322 300502
    python -m money_flow probe 688322 --no-cache
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date as _date
from pathlib import Path
from typing import List, Optional

# 复用项目自带的 SSL socket helper（在本机被验证可绕过 akshare requests 失败）
from data_fetcher import _raw_get, _build_query

logger = logging.getLogger(__name__)


# ─── 路径与常量 ───────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache" / "money_flow"

EASTMONEY_HOST = "push2his.eastmoney.com"
FFLOW_PATH     = "/api/qt/stock/fflow/daykline/get"
FFLOW_TIMEOUT  = 15
FETCH_RETRIES  = 2

# 状态码 → 中文说明（用于上层渲染）
REASON_CN_MAP = {
    "":                         "近3日主力资金健康",
    "money_flow_unavailable":   "数据缺失（上市过短或接口未返回数据）",
    "money_flow_fetch_failed":  "资金流接口请求失败",
    "money_flow_not_healthy":   "近3日主力资金不健康（净流入天数<2 或 累计≤0）",
}


# ─── V1.5-alpha2 资金源健康检测（仅检测，不接入买入）──────────────────

# 固定探针集：5 只大市值蓝筹，数据稳定性最高
PROBE_SET = [
    "600000",   # 浦发银行   沪市主板
    "000001",   # 平安银行   深市主板
    "600519",   # 贵州茅台   沪市主板
    "000858",   # 五粮液    深市主板
    "600036",   # 招商银行   沪市主板
]

# 阈值（failure_rate = (failed + missing) / 探针总数）
THRESHOLD_OK_MAX        = 0.20   # ≤20% → ok
THRESHOLD_DEGRADED_MAX  = 0.50   # 20%~50% → degraded；>50% → unavailable

# 系统状态缓存有效期（秒）
SYSTEM_HEALTH_TTL       = 300

# 自检日志（独立文件，不混入 auto_run.log）
HEALTH_LOG_PATH         = BASE_DIR / "logs" / "money_flow_health.log"

# 进程内存级缓存（只在当前 Python 进程有效；进程退出即失效）
_system_health_cache: Optional[dict] = None


# ─── V1.5-alpha3 同花顺 fallback（仅观察，不接入买入）─────────────────

# AKShare 同花顺接口（独立于 eastmoney push2his，2026-05-26 实测稳定）
THS_PERIOD              = "3日排行"     # 与 V1.4 "近3日资金健康" 口径一致
THS_FETCH_TIMEOUT       = 45            # 同花顺一次拉全市场 ~20s，给足余量
THS_FETCH_RETRIES       = 1             # 失败 1 次重试

# THS 快照内存级缓存（避免同一进程内反复触发 20s 慢请求）
_ths_snapshot_cache: dict = {}   # {(period, day_str): pd.DataFrame}

# 同花顺简化版"资金健康"门槛：近3日累计净额必须严格大于此值才视为健康
THS_HEALTHY_NET_THRESHOLD = 0.0   # 元；可调，alpha 阶段先保守 0


# 数据源标识（贯穿整套返回字段）
SOURCE_PUSH2HIS    = "push2his"
SOURCE_THS_SIMPLE  = "ths_simple"
SOURCE_UNAVAILABLE = "unavailable"

LEVEL_PRIMARY      = "primary"
LEVEL_FALLBACK     = "fallback"
LEVEL_UNAVAILABLE  = "unavailable"


# ─── 市场判定 ───────────────────────────────────────────────────────────

def _market_secid_prefix(code: str) -> int:
    """
    根据股票代码推断 eastmoney secid 前缀：
      沪市（60xxxx / 68xxxx / 9xxxxx）→ 1
      深市（00xxxx / 30xxxx）+ 北交所（4/8 开头）→ 0
    与 akshare.stock_individual_fund_flow 内部 market_map 一致。
    """
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "90")):
        return 1
    return 0


def _market_label(code: str) -> str:
    """人类可读的市场标签，仅用于展示。"""
    code = str(code).zfill(6)
    if code.startswith(("60", "68", "90")): return "sh"
    if code.startswith(("4", "8")):         return "bj"
    if code.startswith(("00", "30")):       return "sz"
    return "sz"


# ─── 缓存 ──────────────────────────────────────────────────────────────

def _cache_path(code: str, day: Optional[str] = None,
                source: str = SOURCE_PUSH2HIS) -> Path:
    """
    缓存文件命名带数据源前缀，避免不同口径数据混在一起。
        push2his_{code}_{date}.json
        ths_simple_{code}_{date}.json
    """
    if day is None:
        day = _date.today().strftime("%Y%m%d")
    return CACHE_DIR / f"{source}_{str(code).zfill(6)}_{day}.json"


def _load_cache(code: str, source: str = SOURCE_PUSH2HIS) -> Optional[dict]:
    """同一天内的缓存命中即返回；不存在或解析失败返回 None。"""
    p = _cache_path(code, source=source)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[money_flow] 缓存读取失败 {p.name}: {e}")
        return None


def _save_cache(code: str, data: dict, source: str = SOURCE_PUSH2HIS) -> None:
    """写入当日缓存。失败静默，不影响主流程。"""
    p = _cache_path(code, source=source)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[money_flow] 缓存写入失败 {p.name}: {e}")


# ─── 网络获取（用 _raw_get 而非 akshare）────────────────────────────────

def _fetch_fflow_klines(code: str, retries: int = FETCH_RETRIES) -> Optional[list]:
    """
    用项目自带的 _raw_get 直连 push2his.eastmoney.com 拉日 K 资金流。
    成功返回 klines 列表（每条为逗号分隔字符串），失败返回 None。
    """
    code = str(code).zfill(6)
    secid = f"{_market_secid_prefix(code)}.{code}"
    params = {
        "lmt":     "0",           # 0 = 拉取全部历史（实测返回 ~120 个交易日）
        "klt":     "101",         # 日 K
        "secid":   secid,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut":      "b2884a393a59ad64002292a3e90d46a5",
        "_":       int(time.time() * 1000),
    }
    path = f"{FFLOW_PATH}?" + _build_query(params)

    for attempt in range(1, retries + 1):
        try:
            raw = _raw_get(EASTMONEY_HOST, path, timeout=FFLOW_TIMEOUT)
            if not raw:
                logger.debug(f"[money_flow] {code} 第 {attempt} 次：空响应")
                if attempt < retries:
                    time.sleep(1.0)
                continue
            data = json.loads(raw)
            klines = (data.get("data") or {}).get("klines") or []
            return klines if klines else None
        except Exception as e:
            logger.warning(
                f"[money_flow] {code} 第 {attempt} 次失败: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            if attempt < retries:
                time.sleep(1.0)
    return None


# ─── 数据解析 ─────────────────────────────────────────────────────────

def _parse_kline_row(line: str) -> Optional[dict]:
    """
    把 eastmoney 一条 kline 字符串解析成 dict。字段顺序（akshare 已验证一致）：
      [0]  日期
      [1]  主力净流入-净额（元）         ← key field 1
      [2]  小单净流入-净额
      [3]  中单净流入-净额
      [4]  大单净流入-净额
      [5]  超大单净流入-净额
      [6]  主力净流入-净占比（%）         ← key field 2
      [7]  小单净流入-净占比
      [8]  中单净流入-净占比
      [9]  大单净流入-净占比
      [10] 超大单净流入-净占比
      [11] 收盘价
      [12] 涨跌幅
    """
    parts = line.split(",")
    if len(parts) < 13:
        return None
    try:
        return {
            "date":            parts[0],
            "main_net_amount": float(parts[1]),
            "main_net_ratio":  float(parts[6]),
            "close":           float(parts[11]),
            "change_pct":      float(parts[12]),
        }
    except (ValueError, IndexError):
        return None


def _empty_result(code: str, days: int, status: str, reason_code: str) -> dict:
    """统一的"无数据 / 失败"结果模板。"""
    return {
        "code":                       str(code).zfill(6),
        "status":                     status,
        # —— 数据源识别（V1.5-alpha3 新增）——
        "data_source":                SOURCE_UNAVAILABLE,
        "source_level":               LEVEL_UNAVAILABLE,
        # —— push2his 字段 ——
        "latest_date":                None,
        "days":                       days,
        "main_net_inflow_days":       0,
        "main_net_inflow_total":      0.0,
        "main_net_inflow_ratio_avg":  0.0,
        "is_healthy":                 False,
        "reason_code":                reason_code,
        "reason_cn":                  REASON_CN_MAP.get(reason_code, reason_code),
        "recent_days":                [],
        # —— ths 字段 ——（默认空，仅当 source=ths_simple 时填）
        "ths_period":                 None,
        "ths_net_total":              None,
        "ths_period_pct_change":      None,
        "ths_turnover_rate":          None,
        "ths_latest_price":           None,
    }


# ─── 同花顺 fallback：数据获取与解析 ────────────────────────────────────

def _parse_chinese_amount(s) -> Optional[float]:
    """
    把同花顺中文带单位的数额字符串解析为浮点（单位：元）。
        '-1.27亿'   → -127000000.0
        '5741.33万' → 57413300.0
        '0'         → 0.0
        '--' / ''   → None
    """
    if s is None:
        return None
    raw = str(s).strip()
    if raw in ("", "--", "-", "None", "nan"):
        return None
    # 去掉百分号（虽然这个函数主要处理金额；防御性）
    raw = raw.replace(",", "")
    sign = 1
    if raw.startswith(("-", "−")):
        sign = -1
        raw = raw.lstrip("-−")
    elif raw.startswith("+"):
        raw = raw[1:]
    try:
        if raw.endswith("亿"):
            return sign * float(raw[:-1]) * 1e8
        if raw.endswith("万"):
            return sign * float(raw[:-1]) * 1e4
        return sign * float(raw)
    except (ValueError, TypeError):
        return None


def _parse_pct(s) -> Optional[float]:
    """'5.40%' → 5.40；'-' / '' → None"""
    if s is None:
        return None
    raw = str(s).strip()
    if raw in ("", "--", "-", "None", "nan"):
        return None
    raw = raw.rstrip("%").strip()
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _fetch_ths_snapshot(period: str = THS_PERIOD,
                        force_refresh: bool = False):
    """
    从同花顺拉一次全市场资金流快照（约 20s）。
    成功返回 pandas.DataFrame，失败返回 None。

    使用进程内 + 磁盘双层缓存：同一日同一 period 只调一次接口。
    缓存文件：cache/money_flow/ths_snapshot_{period}_{day}.pkl
    """
    day = _date.today().strftime("%Y%m%d")
    cache_key = (period, day)

    # 1) 进程内 cache
    if not force_refresh and cache_key in _ths_snapshot_cache:
        return _ths_snapshot_cache[cache_key]

    # 2) 磁盘 cache（pkl，因为 DataFrame 中含中文）
    disk_path = CACHE_DIR / f"ths_snapshot_{period}_{day}.pkl"
    if not force_refresh and disk_path.exists():
        try:
            import pickle
            with open(disk_path, "rb") as f:
                df = pickle.load(f)
            _ths_snapshot_cache[cache_key] = df
            return df
        except Exception as e:
            logger.warning(f"[money_flow.ths] 磁盘缓存读失败: {e}")

    # 3) 真拉
    try:
        import akshare as ak
    except ImportError:
        logger.warning("[money_flow.ths] akshare 未安装")
        return None

    for attempt in range(1, THS_FETCH_RETRIES + 2):
        try:
            t0 = time.time()
            df = ak.stock_fund_flow_individual(symbol=period)
            elapsed = time.time() - t0
            if df is None or df.empty:
                logger.warning(f"[money_flow.ths] {period} 第 {attempt} 次返回空")
                if attempt <= THS_FETCH_RETRIES:
                    time.sleep(1.5)
                continue
            logger.info(f"[money_flow.ths] {period} 拉到 {len(df)} 行 ({elapsed:.1f}s)")
            # 写双层 cache
            _ths_snapshot_cache[cache_key] = df
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                import pickle
                with open(disk_path, "wb") as f:
                    pickle.dump(df, f)
            except Exception as e:
                logger.debug(f"[money_flow.ths] 磁盘缓存写失败: {e}")
            return df
        except Exception as e:
            logger.warning(
                f"[money_flow.ths] {period} 第 {attempt} 次失败: "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            if attempt <= THS_FETCH_RETRIES:
                time.sleep(1.5)
    return None


def _lookup_ths_row(df, code: str) -> Optional[dict]:
    """
    在 THS 全市场快照里查指定 code 的那行。
    返回解析后的 dict 或 None。
    """
    if df is None or df.empty:
        return None
    code = str(code).zfill(6)

    # 找代码列（同花顺用"股票代码"）
    code_col = None
    for c in df.columns:
        if c in ("股票代码", "代码", "code"):
            code_col = c
            break
    if code_col is None:
        return None

    hit = df[df[code_col].astype(str).str.zfill(6) == code]
    if hit.empty:
        return None
    row = hit.iloc[0]

    # THS "3日排行" 字段名：序号 / 股票代码 / 股票简称 / 最新价 / 阶段涨跌幅 / 连续换手率 / 资金流入净额
    # THS "即时" 字段名：     序号 / 股票代码 / 股票简称 / 最新价 / 涨跌幅 / 换手率 / 流入资金 / 流出资金 / 净额 / 成交额
    def get(*cands):
        for c in cands:
            if c in row.index:
                return row[c]
        return None

    return {
        "name":          str(get("股票简称") or ""),
        "latest_price":  _parse_chinese_amount(get("最新价")),
        "period_pct":    _parse_pct(get("阶段涨跌幅", "涨跌幅")),
        "turnover_pct":  _parse_pct(get("连续换手率", "换手率")),
        "net_amount":    _parse_chinese_amount(get("资金流入净额", "净额")),
        # 即时模式才有的：
        "inflow":        _parse_chinese_amount(get("流入资金")),
        "outflow":       _parse_chinese_amount(get("流出资金")),
        "amount":        _parse_chinese_amount(get("成交额")),
    }


def _evaluate_via_ths_simple(code: str, use_cache: bool = True) -> dict:
    """
    通过同花顺 "3日排行" 计算简化版资金健康。
    规则：近3日累计净流入额 > THS_HEALTHY_NET_THRESHOLD（默认 0 元）→ healthy。
    与 push2his 完全独立的缓存空间（source="ths_simple"）。
    """
    code = str(code).zfill(6)

    # 同日缓存命中
    if use_cache:
        cached = _load_cache(code, source=SOURCE_THS_SIMPLE)
        if cached:
            return cached

    # 拉快照
    df = _fetch_ths_snapshot(period=THS_PERIOD)
    if df is None or df.empty:
        result = _empty_result(code, 3, "fetch_failed", "money_flow_fetch_failed")
        # 标记数据源（未取到也要标"尝试过 ths"）
        result["data_source"]  = SOURCE_UNAVAILABLE
        result["source_level"] = LEVEL_UNAVAILABLE
        return result

    row = _lookup_ths_row(df, code)
    if row is None:
        # 全市场快照中找不到这只票 — 可能是停牌/退市/北交所老股
        result = _empty_result(code, 3, "missing", "money_flow_unavailable")
        result["data_source"]  = SOURCE_THS_SIMPLE   # 尝试过该源，但个股缺失
        result["source_level"] = LEVEL_FALLBACK
        if use_cache:
            _save_cache(code, result, source=SOURCE_THS_SIMPLE)
        return result

    net_total = row.get("net_amount")
    if net_total is None:
        result = _empty_result(code, 3, "missing", "money_flow_unavailable")
        result["data_source"]  = SOURCE_THS_SIMPLE
        result["source_level"] = LEVEL_FALLBACK
        if use_cache:
            _save_cache(code, result, source=SOURCE_THS_SIMPLE)
        return result

    is_healthy = net_total > THS_HEALTHY_NET_THRESHOLD
    if is_healthy:
        reason_code = ""
        reason_cn   = REASON_CN_MAP[""] + "（同花顺简化口径：近3日累计净额 > 0）"
    else:
        reason_code = "money_flow_not_healthy"
        reason_cn   = REASON_CN_MAP["money_flow_not_healthy"] + "（同花顺简化口径）"

    result = {
        "code":                       code,
        "status":                     "ok",
        "data_source":                SOURCE_THS_SIMPLE,
        "source_level":               LEVEL_FALLBACK,
        # —— push2his 字段填默认 ——
        "latest_date":                _date.today().strftime("%Y-%m-%d"),  # 同花顺快照是"今日盘后"
        "days":                       3,
        "main_net_inflow_days":       0,
        "main_net_inflow_total":      0.0,
        "main_net_inflow_ratio_avg":  0.0,
        "recent_days":                [],
        # —— ths 专属字段 ——
        "ths_period":                 THS_PERIOD,
        "ths_net_total":              round(net_total, 2),
        "ths_period_pct_change":      row.get("period_pct"),
        "ths_turnover_rate":          row.get("turnover_pct"),
        "ths_latest_price":           row.get("latest_price"),
        "ths_stock_name":             row.get("name") or "",
        # —— 健康判定 ——
        "is_healthy":                 is_healthy,
        "reason_code":                reason_code,
        "reason_cn":                  reason_cn,
    }
    if use_cache:
        _save_cache(code, result, source=SOURCE_THS_SIMPLE)
    return result


# ─── 公开 API ────────────────────────────────────────────────────────

def get_money_flow_3d(code: str, days: int = 3, use_cache: bool = True) -> dict:
    """
    获取并解析近 `days` 日资金流数据，返回标准结果 dict（**不做健康判定**）。
    healthy 判定请用 evaluate_money_flow_health。

    Args:
        code:       6 位股票代码（前导补零）
        days:       近 N 日，默认 3
        use_cache:  是否读写当日缓存

    Returns:
        dict（包含 code/status/latest_date/days/main_net_inflow_*/is_healthy/reason_*/recent_days）
    """
    code = str(code).zfill(6)

    # 1) 同日缓存命中（push2his 源专属缓存）
    if use_cache:
        cached = _load_cache(code, source=SOURCE_PUSH2HIS)
        if cached and cached.get("days") == days:
            return cached

    # 2) 拉数据
    klines = _fetch_fflow_klines(code)
    if klines is None:
        # 接口失败 — 不缓存（下次重试）
        return _empty_result(code, days, "fetch_failed", "money_flow_fetch_failed")

    # 3) 解析
    parsed = [_parse_kline_row(line) for line in klines]
    parsed = [r for r in parsed if r is not None]
    if len(parsed) < days:
        # 数据少于 N 日（上市过短/新股）— 缓存（缺数本身不会很快变）
        result = _empty_result(code, days, "missing", "money_flow_unavailable")
        result["data_source"]  = SOURCE_PUSH2HIS
        result["source_level"] = LEVEL_PRIMARY
        if use_cache:
            _save_cache(code, result, source=SOURCE_PUSH2HIS)
        return result

    # 4) 取最近 N 日
    recent = parsed[-days:]
    nets   = [r["main_net_amount"] for r in recent]
    ratios = [r["main_net_ratio"]  for r in recent]
    inflow_days = sum(1 for v in nets if v > 0)
    total       = sum(nets)
    avg_ratio   = sum(ratios) / len(ratios) if ratios else 0.0
    latest_date = recent[-1]["date"]

    # 用 _empty_result 模板 + 覆盖，保证字段全（含 ths_* 默认值）
    result = _empty_result(code, days, "ok", "")
    result.update({
        "data_source":                SOURCE_PUSH2HIS,
        "source_level":               LEVEL_PRIMARY,
        "latest_date":                latest_date,
        "main_net_inflow_days":       inflow_days,
        "main_net_inflow_total":      round(total, 2),
        "main_net_inflow_ratio_avg":  round(avg_ratio, 2),
        "reason_code":                "",
        "reason_cn":                  "",
        "recent_days": [
            {"date": r["date"],
             "net":   round(r["main_net_amount"], 2),
             "ratio": round(r["main_net_ratio"],  2)}
            for r in recent
        ],
    })
    if use_cache:
        _save_cache(code, result, source=SOURCE_PUSH2HIS)
    return result


def evaluate_money_flow_health(
    code: str,
    days: int = 3,
    use_cache: bool = True,
    allow_fallback: bool = True,
) -> dict:
    """
    评估资金健康状态。两级数据源策略（V1.5-alpha3）：

      ① 主源 push2his：近 days 日主力净流入天数 >= 2  AND  累计 > 0  → healthy
      ② 主源不可用且 allow_fallback=True → 备源 ths_simple：
         近 3 日累计净流入 > THS_HEALTHY_NET_THRESHOLD → healthy（简化口径）
      ③ 两者都不可用 → is_healthy=False，reason_code 给出细分原因

    返回 dict 中关键字段：
      data_source:   push2his | ths_simple | unavailable
      source_level:  primary  | fallback   | unavailable
      is_healthy:    bool
      status:        ok | missing | fetch_failed
      reason_code, reason_cn

    ⚠️ V1.5-alpha 阶段：本函数 **只供观察**，不接入 run.py / check_buy。
    """
    # ── ① 试主源 push2his ──
    primary = get_money_flow_3d(code, days=days, use_cache=use_cache)

    if primary.get("status") == "ok":
        # 主源 OK → 应用主源健康规则
        inflow_days = primary.get("main_net_inflow_days", 0)
        total       = primary.get("main_net_inflow_total", 0.0)
        is_healthy  = (inflow_days >= 2) and (total > 0)

        primary["data_source"]  = SOURCE_PUSH2HIS
        primary["source_level"] = LEVEL_PRIMARY
        primary["is_healthy"]   = is_healthy
        if is_healthy:
            primary["reason_code"] = ""
            primary["reason_cn"]   = REASON_CN_MAP[""]
        else:
            primary["reason_code"] = "money_flow_not_healthy"
            primary["reason_cn"]   = REASON_CN_MAP["money_flow_not_healthy"]

        if use_cache:
            _save_cache(code, primary, source=SOURCE_PUSH2HIS)
        return primary

    # ── ② 主源失败且允许 fallback → 尝试同花顺简化口径 ──
    if not allow_fallback:
        primary["data_source"]  = SOURCE_UNAVAILABLE
        primary["source_level"] = LEVEL_UNAVAILABLE
        return primary

    fallback = _evaluate_via_ths_simple(code, use_cache=use_cache)
    # 关键判定：data_source==THS_SIMPLE 表示**同花顺接口本身能用**（不论个股是否在快照里）
    # 这种情况要返回 fallback（即使 status=missing 也比 fetch_failed 更精准）
    if fallback.get("data_source") == SOURCE_THS_SIMPLE:
        return fallback

    # ── ③ 主源 + 备源 接口都不可用 ──
    final = _empty_result(code, days, "fetch_failed", "money_flow_fetch_failed")
    final["data_source"]  = SOURCE_UNAVAILABLE
    final["source_level"] = LEVEL_UNAVAILABLE
    final["reason_cn"]    = "主源（push2his）与备源（同花顺）当前均不可用，资金健康无法判定"
    return final


# ─── V1.5-alpha2: 资金源系统健康检测 ───────────────────────────────────

def check_money_flow_system_health(
    probe_codes: Optional[List[str]] = None,
    force_refresh: bool = False,
) -> dict:
    """
    V1.5-alpha3 资金源整体健康检测（**仅检测，不接入买入**）。

    设计目的：
      - 区分"个股资金不健康" vs "资金源整体故障"
      - 区分"主源 push2his 不可用" vs "备源同花顺也挂了"
      - 当数据源整体挂时，未来 V1.5 正式版可基于 should_apply_money_flow_gate 决定
        是否禁用资金闸 → 回退 V1.4 决策，避免接口故障误杀全市场

    判定规则（V1.5-alpha3）：
      系统状态：
        primary push2his 探针失败率 ≤ 20%  → primary_status="ok"
        20% < 失败率 ≤ 50%              → primary_status="degraded"
        > 50%                            → primary_status="unavailable"
        同花顺快照成功                    → fallback_status="ok"
        同花顺快照失败                    → fallback_status="unavailable"
      综合：
        primary ok                       → system_status="ok"        active_source=push2his
        primary 挂 + fallback ok         → system_status="degraded"  active_source=ths_simple
        primary 挂 + fallback 挂         → system_status="unavailable" active_source=unavailable

    Args:
        probe_codes:    主源探针股票列表；None → PROBE_SET
        force_refresh:  True 强制重测；False 命中 5 分钟缓存即返回

    Returns:
        dict 含主/备状态详情 + active_source / system_status / 等
    """
    global _system_health_cache
    now = time.time()

    # 1) 5 分钟内缓存命中
    if not force_refresh and _system_health_cache is not None:
        age = now - _system_health_cache.get("_cached_at", 0)
        if age < SYSTEM_HEALTH_TTL:
            cached = dict(_system_health_cache)
            cached["_from_cache"] = True
            cached["_cache_age_s"] = round(age, 1)
            return cached

    # 2) ─── 探测主源 push2his ───
    codes = list(probe_codes) if probe_codes else list(PROBE_SET)
    probe_detail: dict = {}
    n_success = n_failed = n_missing = 0

    if not codes:
        primary_status_dict = _make_primary_status_dict(
            checked_at=_now_str(), codes=[], detail={},
            success=0, failed=0, missing=0,
        )
    else:
        for c in codes:
            c6 = str(c).zfill(6)
            try:
                klines = _fetch_fflow_klines(c6, retries=1)
            except Exception as e:
                logger.warning(
                    f"[money_flow.health] {c6} 主源探测异常: "
                    f"{type(e).__name__}: {e}"
                )
                klines = None

            if klines is None:
                probe_detail[c6] = "fetch_failed"; n_failed += 1
            elif len(klines) < 3:
                probe_detail[c6] = "missing"; n_missing += 1
            else:
                probe_detail[c6] = "ok"; n_success += 1
            time.sleep(0.3)

        primary_status_dict = _make_primary_status_dict(
            checked_at=_now_str(), codes=codes, detail=probe_detail,
            success=n_success, failed=n_failed, missing=n_missing,
        )

    primary_status = primary_status_dict["primary_status"]

    # 3) ─── 探测备源同花顺（仅当主源不 ok 时才探，节省时间）───
    fallback_detail: dict = {}
    if primary_status == "ok":
        # 主源 ok 时不浪费 20 秒去查同花顺；标"未探测"
        fallback_status = "not_checked"
        fallback_detail = {"note": "主源 push2his 已可用，未对备源做探测"}
    else:
        ths_df = _fetch_ths_snapshot(period=THS_PERIOD, force_refresh=force_refresh)
        if ths_df is None or len(ths_df) < 100:
            fallback_status = "unavailable"
            fallback_detail = {"note": "同花顺接口返回空/少", "rows": 0 if ths_df is None else len(ths_df)}
        else:
            fallback_status = "ok"
            fallback_detail = {
                "rows":       len(ths_df),
                "period":     THS_PERIOD,
                "columns":    list(ths_df.columns)[:10],
            }

    # 4) ─── 综合 system_status + active_source ───
    if primary_status == "ok":
        system_status = "ok"
        active_source = SOURCE_PUSH2HIS
        should_gate = True
        gate_reason = "主源 push2his 探针失败率在可接受范围"
    elif primary_status == "degraded" and fallback_status in ("ok", "not_checked"):
        # 主源仅边缘失败（20%-50%），仍以主源为 active
        system_status = "degraded"
        active_source = SOURCE_PUSH2HIS
        should_gate = True
        gate_reason = "主源 push2his 处于警戒区间但仍可用"
    elif fallback_status == "ok":
        # 主源 unavailable 但备源 ok → 降级到备源
        system_status = "degraded"
        active_source = SOURCE_THS_SIMPLE
        # V1.5-alpha 阶段：备源仅观察，不接入买入 ← 用户明确要求
        should_gate = False
        gate_reason = (
            "主源 push2his 不可用，已降级到备源同花顺；"
            "alpha 阶段备源仅用于观察，不参与正式买入闸"
        )
    else:
        system_status = "unavailable"
        active_source = SOURCE_UNAVAILABLE
        should_gate = False
        gate_reason = "主源 push2his 和备源同花顺均不可用，资金闸禁用，应回退 V1.4 决策"

    # fallback_available：未来 V1.5 正式版可参考的"备源是否就绪"标志
    fallback_available = (fallback_status == "ok")

    result = {
        "system_status":                 system_status,
        "active_source":                 active_source,

        # 主源
        "primary_source":                SOURCE_PUSH2HIS,
        "primary_status":                primary_status,
        "primary_probe_count":           primary_status_dict["probe_count"],
        "primary_probe_success":         primary_status_dict["probe_success"],
        "primary_probe_failed":          primary_status_dict["probe_failed"],
        "primary_probe_missing":         primary_status_dict["probe_missing"],
        "primary_failure_rate":          primary_status_dict["failure_rate"],
        "primary_probe_detail":          probe_detail,

        # 备源
        "fallback_source":               SOURCE_THS_SIMPLE,
        "fallback_status":               fallback_status,
        "fallback_probe_detail":         fallback_detail,
        "fallback_available":            fallback_available,

        # 买入闸（alpha 阶段仅返回建议值，不接入正式交易）
        "should_apply_money_flow_gate":  should_gate,
        "reason":                        gate_reason,

        # 元数据
        "checked_at":                    _now_str(),
        "next_recheck_minutes":          int(SYSTEM_HEALTH_TTL // 60),

        # —— 兼容旧字段（V1.5-alpha2 callers/dashboard 引用）——
        "probe_count":                   primary_status_dict["probe_count"],
        "probe_success":                 primary_status_dict["probe_success"],
        "probe_failed":                  primary_status_dict["probe_failed"],
        "probe_missing":                 primary_status_dict["probe_missing"],
        "failure_rate":                  primary_status_dict["failure_rate"],
        "probe_detail":                  probe_detail,
    }

    # 5) 进程内缓存
    result["_cached_at"] = now
    _system_health_cache = result
    return result


def _make_primary_status_dict(
    checked_at: str, codes: list, detail: dict,
    success: int, failed: int, missing: int,
) -> dict:
    """
    把主源 push2his 的探针计数转成 primary_* 状态。仅返回主源相关字段；
    系统综合状态（包含 fallback）由调用方在 check_money_flow_system_health 里合成。
    """
    total = max(len(codes), 1)
    fail_count = failed + missing
    failure_rate = round(fail_count / total, 4)

    if failure_rate <= THRESHOLD_OK_MAX:
        primary_status = "ok"
    elif failure_rate <= THRESHOLD_DEGRADED_MAX:
        primary_status = "degraded"
    else:
        primary_status = "unavailable"

    return {
        "primary_status":  primary_status,
        "probe_count":     total,
        "probe_success":   success,
        "probe_failed":    failed,
        "probe_missing":   missing,
        "failure_rate":    failure_rate,
        "checked_at":      checked_at,
        "probe_detail":    detail,
    }


def _make_system_status_dict(
    checked_at: str, codes: list, detail: dict,
    success: int, failed: int, missing: int,
) -> dict:
    """[V1.5-alpha2 兼容] 把探测计数转成标准 system_status dict。已被新逻辑取代。"""
    total = max(len(codes), 1)
    fail_count = failed + missing
    failure_rate = round(fail_count / total, 4)

    if failure_rate <= THRESHOLD_OK_MAX:
        status = "ok"
        gate = True
        reason = f"{fail_count}/{total} 个探针失败，处于可接受范围（≤{int(THRESHOLD_OK_MAX*100)}%）"
    elif failure_rate <= THRESHOLD_DEGRADED_MAX:
        status = "degraded"
        gate = True
        reason = (
            f"{fail_count}/{total} 个探针失败（失败率 {failure_rate*100:.0f}%），"
            f"处于警戒区间（{int(THRESHOLD_OK_MAX*100)}%~{int(THRESHOLD_DEGRADED_MAX*100)}%）；"
            f"未来正式接入 V1.5 时需要在微信/看板加警告横幅"
        )
    else:
        status = "unavailable"
        gate = False
        reason = (
            f"{fail_count}/{total} 个探针失败（失败率 {failure_rate*100:.0f}%），"
            f"超过 {int(THRESHOLD_DEGRADED_MAX*100)}% 阈值；"
            f"资金源整体不可用，未来正式接入 V1.5 时应回退 V1.4 决策，不启用资金闸"
        )

    return {
        "system_status":                status,
        "checked_at":                   checked_at,
        "probe_count":                  total,
        "probe_success":                success,
        "probe_failed":                 failed,
        "probe_missing":                missing,
        "failure_rate":                 failure_rate,
        "should_apply_money_flow_gate": gate,
        "reason":                       reason,
        "probe_detail":                 detail,
        "next_recheck_minutes":         int(SYSTEM_HEALTH_TTL // 60),
    }


def _now_str() -> str:
    """带时区的 ISO 8601 时间戳。"""
    from datetime import datetime, timezone, timedelta
    tz_cst = timezone(timedelta(hours=8))   # 北京时间
    return datetime.now(tz=tz_cst).strftime("%Y-%m-%dT%H:%M:%S%z")


def get_cached_system_status() -> Optional[dict]:
    """
    若 SYSTEM_HEALTH_TTL 秒内已检测过，返回缓存结果；否则 None。
    供未来主流程"懒触发"用：先查缓存，没有再调 check_money_flow_system_health()。
    """
    if _system_health_cache is None:
        return None
    age = time.time() - _system_health_cache.get("_cached_at", 0)
    if age >= SYSTEM_HEALTH_TTL:
        return None
    return dict(_system_health_cache)


def log_system_health_snapshot(status: dict, trigger: str = "manual") -> None:
    """
    把一次系统健康检测的结果以 **JSONL 单行** 追加到
    logs/money_flow_health.log。

    完全只读策略数据，不写 trade_review.csv，不写 auto_run.log。
    失败静默（即使日志写不进去也不影响主流程）。

    Args:
        status:  check_money_flow_system_health 返回的 dict
        trigger: 触发来源（manual / cli_health / cli_probe / future_check_buy 等）
    """
    try:
        HEALTH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 拷贝一份避免把内部字段（_cached_at / _from_cache 等）写出去
        snap = {
            "ts":                            status.get("checked_at"),
            "trigger":                       trigger,
            # 综合
            "status":                        status.get("system_status"),
            "active_source":                 status.get("active_source"),
            "should_apply_money_flow_gate":  status.get("should_apply_money_flow_gate"),
            # 主源
            "primary_source":                status.get("primary_source"),
            "primary_status":                status.get("primary_status"),
            "primary_failure_rate":          status.get("primary_failure_rate", status.get("failure_rate")),
            "primary_probe_count":           status.get("primary_probe_count", status.get("probe_count")),
            "primary_probe_success":         status.get("primary_probe_success", status.get("probe_success")),
            "primary_probe_failed":          status.get("primary_probe_failed", status.get("probe_failed")),
            "primary_probe_missing":         status.get("primary_probe_missing", status.get("probe_missing")),
            "primary_probe_detail":          status.get("primary_probe_detail", status.get("probe_detail")),
            # 备源
            "fallback_source":               status.get("fallback_source"),
            "fallback_status":               status.get("fallback_status"),
            "fallback_available":            status.get("fallback_available"),
        }
        with HEALTH_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[money_flow.health] 写入日志失败（不影响主流程）: {e}")


def format_system_health_summary(status: dict) -> str:
    """渲染 system_status dict 为多行人类可读字符串（CLI / 日志 / debug 用）。"""
    sys_emoji = {"ok": "✅", "degraded": "⚠️", "unavailable": "❌"}
    src_emoji = {"ok": "✓", "degraded": "△", "unavailable": "✗", "not_checked": "·"}

    emoji = sys_emoji.get(status.get("system_status"), "?")
    cached_tag = ""
    if status.get("_from_cache"):
        cached_tag = f"  （读自 {status.get('_cache_age_s')}s 前缓存）"

    primary_status = status.get("primary_status", "?")
    fallback_status = status.get("fallback_status", "?")
    active = status.get("active_source", "?")

    primary_count = status.get("primary_probe_count", status.get("probe_count", 0))
    primary_success = status.get("primary_probe_success", status.get("probe_success", 0))
    primary_failed = status.get("primary_probe_failed", status.get("probe_failed", 0))
    primary_missing = status.get("primary_probe_missing", status.get("probe_missing", 0))
    primary_rate = status.get("primary_failure_rate", status.get("failure_rate", 0)) or 0

    lines = [
        f"{emoji} 资金源系统状态：{status.get('system_status', '?').upper()}{cached_tag}",
        f"  当前 active_source: {active}",
        f"  探测时间：{status.get('checked_at')}",
        "",
        f"  ─── 主源 {status.get('primary_source', SOURCE_PUSH2HIS)} ───",
        f"    状态：{src_emoji.get(primary_status, '?')} {primary_status}",
        f"    探针：成功 {primary_success} / 失败 {primary_failed} / 缺失 {primary_missing} / 共 {primary_count}",
        f"    失败率：{primary_rate*100:.1f}%",
        f"    探针明细：",
    ]
    for code, st in (status.get("primary_probe_detail") or status.get("probe_detail") or {}).items():
        st_em = src_emoji.get(st, "?")
        lines.append(f"      {st_em} {code}  {st}")

    lines += [
        "",
        f"  ─── 备源 {status.get('fallback_source', SOURCE_THS_SIMPLE)}（同花顺）───",
        f"    状态：{src_emoji.get(fallback_status, '?')} {fallback_status}",
    ]
    fb_detail = status.get("fallback_probe_detail") or {}
    if "rows" in fb_detail:
        lines.append(f"    快照行数：{fb_detail['rows']} (period={fb_detail.get('period', '?')})")
    if "note" in fb_detail:
        lines.append(f"    备注：{fb_detail['note']}")
    lines.append(f"    fallback_available: {status.get('fallback_available')}")

    lines += [
        "",
        f"  是否启用资金闸（V1.5-alpha 仅建议，未接入买入）："
        f"{'✅ 启用' if status.get('should_apply_money_flow_gate') else '❌ 禁用'}",
        f"  理由：{status.get('reason')}",
        f"  下次允许重测：{status.get('next_recheck_minutes')} 分钟后（用 --force 立即重测）",
    ]
    return "\n".join(lines)


def format_money_flow_summary(result: dict) -> str:
    """
    把结果 dict 渲染成多行人类可读字符串（CLI / 日志 / debug 用）。
    完全只读，不写入任何东西。
    """
    code        = result.get("code", "?")
    status      = result.get("status", "?")
    market      = _market_label(code)
    data_source = result.get("data_source", "?")
    src_level   = result.get("source_level", "?")
    status_emoji = {"ok": "✓", "missing": "·", "fetch_failed": "✗"}.get(status, "?")
    source_tag = f"[{data_source} / {src_level}]"

    def _fmt_money(v: float) -> str:
        if v is None:                  return "—"
        if abs(v) >= 1e8:              return f"{v/1e8:+.2f}亿"
        if abs(v) >= 1e4:              return f"{v/1e4:+.0f}万"
        return f"{v:+,.0f}元"

    def _fmt_pct(v) -> str:
        if v is None: return "—"
        return f"{v:+.2f}%"

    lines = [f"{status_emoji} {code} ({market})  status={status}  {source_tag}"]

    if status != "ok":
        lines.append(f"  原因: {result.get('reason_cn', '')}")
        return "\n".join(lines)

    health_emoji = "✅" if result.get("is_healthy") else "❌"

    if data_source == SOURCE_PUSH2HIS:
        # 主源详细字段
        days   = result.get("days", 0)
        inflow = result.get("main_net_inflow_days", 0)
        total  = result.get("main_net_inflow_total", 0.0)
        ratio  = result.get("main_net_inflow_ratio_avg", 0.0)
        date   = result.get("latest_date", "—")

        lines.append(
            f"  近{days}日主力净流入: {_fmt_money(total)}  "
            f"(净流入天数 {inflow}/{days})  净占比均值 {ratio:+.2f}%"
        )
        lines.append(f"  数据日期: {date}")
        lines.append(f"  健康判定: {health_emoji} {result.get('reason_cn', '')}")

        details = result.get("recent_days", [])
        if details:
            lines.append("  明细：")
            for d in details:
                lines.append(
                    f"    {d['date']}  主力净额 {_fmt_money(d['net'])}  "
                    f"净占比 {d['ratio']:+.2f}%"
                )
    elif data_source == SOURCE_THS_SIMPLE:
        # 备源简化字段
        period       = result.get("ths_period", "3日排行")
        net_total    = result.get("ths_net_total")
        period_pct   = result.get("ths_period_pct_change")
        turnover     = result.get("ths_turnover_rate")
        price        = result.get("ths_latest_price")
        stock_name   = result.get("ths_stock_name", "")

        lines.append(f"  ⚠️ 主源 push2his 不可用，已降级到备源同花顺（{period}）")
        if stock_name:
            lines.append(f"  股票: {stock_name}  最新价: {price if price else '—'}")
        lines.append(
            f"  近3日累计净额（同花顺）: {_fmt_money(net_total)}  "
            f"阶段涨跌幅 {_fmt_pct(period_pct)}  连续换手率 {_fmt_pct(turnover)}"
        )
        lines.append(f"  健康判定: {health_emoji} {result.get('reason_cn', '')}")
        lines.append(
            f"  ⚠️ 备源数据缺少主力分级（超大/大/中/小），仅用于观察，"
            f"alpha 阶段不接入正式买入"
        )
    else:
        lines.append(f"  数据源未知: {data_source}")
        lines.append(f"  健康判定: {health_emoji} {result.get('reason_cn', '')}")

    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────

def _cli_probe(codes: List[str], no_cache: bool = False) -> int:
    if not codes:
        print("用法: python -m money_flow probe <code> [code...] [--no-cache]")
        return 1

    print()
    print("=" * 70)
    print(f"  V1.5-alpha 资金流探测  共 {len(codes)} 只  "
          f"(use_cache={'False' if no_cache else 'True'})")
    print("  只读模式，不写 trade_review.csv，不影响 V1.4 买入规则")
    print("=" * 70)

    use_cache = not no_cache
    healthy_n = 0
    for i, c in enumerate(codes, 1):
        result = evaluate_money_flow_health(c, days=3, use_cache=use_cache)
        if result.get("is_healthy"):
            healthy_n += 1
        print()
        print(f"[{i}/{len(codes)}]")
        print(format_money_flow_summary(result))

    print()
    print("=" * 70)
    print(f"  汇总：健康 {healthy_n} / 共 {len(codes)}")
    print("=" * 70)
    return 0


def _cli_health(force_refresh: bool = True) -> int:
    """
    CLI: python -m money_flow health [--no-force]

    强制探测资金源状态，打印结果，并追加一行到 logs/money_flow_health.log。
    完全只读策略数据，不写 trade_review.csv，不影响 V1.4 买入。
    """
    print()
    print("=" * 70)
    print("  V1.5-alpha2 资金源系统健康检测")
    print(f"  探针集 PROBE_SET = {PROBE_SET}")
    print(f"  force_refresh = {force_refresh}")
    print("  仅检测，不接入买入；不写 trade_review.csv；不影响 V1.4")
    print("=" * 70)

    status = check_money_flow_system_health(force_refresh=force_refresh)
    print()
    print(format_system_health_summary(status))

    # 追加 JSONL 日志
    log_system_health_snapshot(status, trigger="cli_health")
    print()
    print(f"  📜 已追加日志: {HEALTH_LOG_PATH.relative_to(BASE_DIR)}")
    print("=" * 70)
    return 0


def _main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("V1.5-alpha money_flow CLI")
        print()
        print("用法：")
        print("  python -m money_flow probe <code> [code...] [--no-cache]")
        print("  python -m money_flow health [--no-force]")
        print()
        print("示例：")
        print("  python -m money_flow probe 688322 300502")
        print("  python -m money_flow probe 688322 --no-cache")
        print("  python -m money_flow health")
        print("  python -m money_flow health --no-force   # 命中 5 分钟缓存时直接返回")
        return 0

    cmd, rest = args[0], args[1:]
    if cmd == "probe":
        no_cache = "--no-cache" in rest
        codes = [c for c in rest if not c.startswith("--")]
        return _cli_probe(codes, no_cache=no_cache)

    if cmd == "health":
        force_refresh = "--no-force" not in rest
        return _cli_health(force_refresh=force_refresh)

    print(f"未知命令: {cmd!r}")
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    sys.exit(_main())
