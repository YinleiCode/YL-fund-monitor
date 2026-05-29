"""
scripts/build_market_daily.py
==============================
派生脚本：构建单日大盘环境 + 主线板块快照。

第一阶段定位（用户明确）：
  - 只读 trade_review.csv + board_df_cache_{data_date}.json
  - 不调任何外部行情 API
  - 缺数字段就标 *_status=missing，绝不硬造
  - 单行 CSV，每天一份，重跑覆盖

输出文件：
  output/market_daily/market_daily_{report_date}.csv

严格只读保证：
  ✅ 不写 output/trade_review.csv
  ✅ 不写 cache/
  ✅ 不调 run.py
  ✅ 只读 trade_review.csv + 已存在的 board_df_cache_*.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR   = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
CSV_PATH   = OUTPUT_DIR / "trade_review.csv"
OUT_DIR    = OUTPUT_DIR / "market_daily"
BREADTH_DIR = OUTPUT_DIR / "market_breadth"


# —— 主线板块过滤白名单 ——
# 剔除"宽基指数 / 情绪面噪声 / 资金面归类"等不能代表"主线"的板块。
# 这些板块即使 pct_chg 高，也不是用户复盘想看的"主线题材"。
SECTOR_NOISE_BLOCKLIST_KEYWORDS = [
    # 宽基指数
    "融资融券", "深股通", "沪股通", "创业板综",
    "富时罗素", "MSCI", "证金持仓", "QFII持仓", "AH股", "机构重仓",
    # 市值分类
    "小盘股", "大盘股", "中盘股",
    # 情绪面 / 涨停分类（非题材）
    "昨日连板", "昨日涨停", "昨日首板", "昨日打二板",
    "昨日高振幅", "最近多板", "东方财富热股",
    # 上市时间分类
    "次新股",
]


def _is_noise_sector(name: str) -> bool:
    """板块名包含任一 blocklist 关键词 → 视为 noise，剔除。"""
    if not name:
        return True
    for kw in SECTOR_NOISE_BLOCKLIST_KEYWORDS:
        if kw in name:
            return True
    return False


def _safe_float(v) -> Optional[float]:
    if v is None: return None
    try:
        if isinstance(v, str):
            s = v.strip()
            if not s or s.lower() in ("nan", "none", "null"): return None
            return float(s)
        f = float(v)
        return None if f != f else f
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    f = _safe_float(v)
    return int(f) if f is not None else None


def _load_trade_review_for_date(report_date: str) -> Optional[dict]:
    """从 trade_review.csv 取该日的 market_sentiment 和 data_date。"""
    if not CSV_PATH.exists():
        return None
    try:
        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get("report_date", "")).strip() == report_date:
                    return {
                        "data_date":          str(row.get("data_date", "")).strip(),
                        "market_sentiment":   _safe_float(row.get("market_sentiment")),
                    }
        return None
    except Exception as e:
        print(f"  [warn] 读 trade_review.csv 异常: {type(e).__name__}: {e}")
        return None


def _load_board_df_cache(data_date: str) -> Optional[list]:
    """读 board_df_cache_{data_date}.json，返回 list[dict] 或 None。"""
    fp = OUTPUT_DIR / f"board_df_cache_{data_date}.json"
    if not fp.exists():
        return None


def _load_market_breadth_cache(report_date: str) -> Optional[dict]:
    """Read same-day market breadth cache. Never falls back to older files."""
    fp = BREADTH_DIR / f"market_breadth_{report_date}.csv"
    if not fp.exists():
        return None
    try:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        row = rows[0]
        if str(row.get("report_date", "")).strip() != report_date:
            print(
                f"  [warn] market_breadth 日期不匹配: "
                f"{row.get('report_date')!r} != {report_date!r}"
            )
            return None
        return row
    except Exception as e:
        print(f"  [warn] 读 {fp.name} 异常: {type(e).__name__}: {e}")
        return None
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else None
    except Exception as e:
        print(f"  [warn] 读 {fp.name} 异常: {type(e).__name__}: {e}")
        return None


def _check_board_cache_freshness(report_date: str) -> tuple:
    """
    校验 board_df_cache_{report_date}.json 的新鲜度（方案 E · 用户原话）。

    返回 (is_fresh: bool, status: str, mtime_str: str, detail: str)
      status ∈ {"ok", "missing", "stale", "error", "unknown"}

    核心规则（用户原话）：
      1. cache 文件名必须与 report_date 同日（不读 data_date）
      2. 不允许 fallback 到前一日 cache
      3. mtime 必须 >= report_date 当日 15:00（盘后数据）才算 fresh
      4. mtime < 15:00 → stale（盘中实时数据不算复盘数据）
      5. 文件不存在 → missing

    本函数纯只读，不写文件、不抛异常。
    """
    fp = OUTPUT_DIR / f"board_df_cache_{report_date}.json"
    if not fp.exists():
        err_fp = OUTPUT_DIR / f"board_df_cache_{report_date}.error.json"
        if err_fp.exists():
            try:
                err = json.loads(err_fp.read_text(encoding="utf-8"))
                msg = str(err.get("message", "")).strip()
                attempts = err.get("attempts") if isinstance(err.get("attempts"), list) else []
                cats = [str(a.get("category", "")).strip() for a in attempts if isinstance(a, dict)]
                cats = [c for c in cats if c]
                detail = msg or "盘后板块快照生成失败"
                if cats:
                    detail += "；错误分类：" + "、".join(cats)
                detail += "；未写 board_df_cache 主文件，不使用旧缓存"
                return (False, "error", "—", detail)
            except Exception as e:
                return (False, "error", "—",
                        f"找到失败审计 {err_fp.name}，但读取异常: {type(e).__name__}: {e}")
        return (False, "missing", "—",
                f"找不到 board_df_cache_{report_date}.json"
                f"（按方案 E：cache 必须与 report_date 同日，不允许 fallback 到 data_date）")

    # —— 时间戳/日期解析（任何失败 → unknown）——
    try:
        from datetime import datetime as _dt
        rd_close = _dt.strptime(report_date + "1500", "%Y%m%d%H%M")   # 当日 15:00 收盘
    except (ValueError, TypeError):
        return (False, "unknown", "—",
                f"report_date={report_date!r} 格式异常")

    try:
        mtime = fp.stat().st_mtime
    except Exception as e:
        return (False, "unknown", "—",
                f"读 cache mtime 异常: {type(e).__name__}: {e}")

    from datetime import datetime as _dt2
    mtime_dt  = _dt2.fromtimestamp(mtime)
    mtime_str = mtime_dt.strftime("%Y-%m-%d %H:%M:%S")

    # 核心判定：mtime 必须 >= report_date 当日 15:00（盘后才算合格）
    if mtime < rd_close.timestamp():
        return (False, "stale", mtime_str,
                f"cache mtime={mtime_str} < {report_date} 15:00（盘后切线）；"
                f"早于盘后的快照视为盘中实时数据，不算复盘数据")

    return (True, "ok", mtime_str,
            f"cache 新鲜（mtime={mtime_str} >= {report_date} 15:00 盘后切线）")


def _verdict_raw_score(score: Optional[float]) -> str:
    """
    V1.4 原系统情绪分 → 中文定性（保持原口径，仅基于 score 一个数）。
    这只反映「原系统打出的分」，不代表"真实赚钱效应"。
    """
    if score is None: return "未知"
    if score > 7: return "强势"
    if score >= 5: return "中性"
    return "弱势"


def _judge_market_env(
    score:                Optional[float],
    advance_count:        Optional[int],
    decline_count:        Optional[int],
    limit_up_count:       Optional[int],
    limit_down_count:     Optional[int],
    burst_count:          Optional[int],
    index_change_pct:     Optional[float],
    total_amount:         Optional[float],
) -> tuple:
    """
    复盘观察口径 — 基于真实赚钱效应判定 market_env_verdict。

    返回 (verdict, desc, weak_breadth_flag, breadth_desc, adv_dec_ratio, burst_rate)
      verdict ∈ {"数据不足", "极弱", "弱势", "中性", "强势", "未知"}

    设计原则（用户原话）：
      - 只有 score、缺细分 → "数据不足"（不允许直接说"强势"）
      - decline_count >= 4000 → 极弱
      - decline_count >= 3500 → 弱势
      - advance_decline_ratio < 0.5 → weak_breadth_flag=True
      - limit_down_count 明显 / burst_rate 高 → 降低市场定性
    """
    # —— 派生比率（先存 raw 值，最后展示再 round，避免边界 case 精度丢失）——
    adv_dec_ratio_raw = None
    if advance_count is not None and decline_count is not None and decline_count > 0:
        adv_dec_ratio_raw = advance_count / decline_count

    burst_rate_raw = None
    if burst_count is not None and limit_up_count is not None:
        # 炸板率 = 炸板 / (涨停 + 炸板)：炸板是从涨停状态打开的票数
        denom = limit_up_count + burst_count
        if denom > 0:
            burst_rate_raw = burst_count / denom

    # —— 宽度旗标（用 raw 值判，避免 round 引入边界假阴）——
    weak_breadth_flag = False
    if adv_dec_ratio_raw is not None:
        weak_breadth_flag = adv_dec_ratio_raw < 0.5

    # 展示用 round 后的值
    adv_dec_ratio = round(adv_dec_ratio_raw, 3) if adv_dec_ratio_raw is not None else None
    burst_rate    = round(burst_rate_raw,    3) if burst_rate_raw    is not None else None

    if adv_dec_ratio is None:
        breadth_desc = "涨跌家数缺失"
    elif adv_dec_ratio < 0.5:
        breadth_desc = f"涨 {advance_count} / 跌 {decline_count}（涨跌比 {adv_dec_ratio:.2f}），宽度严重失衡"
    elif adv_dec_ratio < 1.0:
        breadth_desc = f"涨 {advance_count} / 跌 {decline_count}（涨跌比 {adv_dec_ratio:.2f}），宽度略偏弱"
    elif adv_dec_ratio < 2.0:
        breadth_desc = f"涨 {advance_count} / 跌 {decline_count}（涨跌比 {adv_dec_ratio:.2f}），宽度正常"
    else:
        breadth_desc = f"涨 {advance_count} / 跌 {decline_count}（涨跌比 {adv_dec_ratio:.2f}），宽度健康"

    # —— 数据完整性判定 ——
    # 必须至少有 advance_count + decline_count 才能算"真实赚钱效应"
    has_breadth = (advance_count is not None and decline_count is not None)
    has_limit   = (limit_up_count is not None and limit_down_count is not None)

    if not has_breadth and not has_limit:
        # 完全没有细分数据 — 不允许 verdict 直接用 raw score
        return (
            "数据不足",
            "仅有原始情绪分，缺少涨跌家数/涨跌停/炸板/成交额明细，暂不判定真实赚钱效应",
            weak_breadth_flag, breadth_desc, adv_dec_ratio, burst_rate,
        )

    # —— 真实赚钱效应判定（用户原话规则）——
    notes = []
    base = "中性"   # 起始值

    # 1) 跌家数阈值（用户原话）
    if decline_count is not None and decline_count >= 4000:
        base = "极弱"
        notes.append(f"跌家数 {decline_count} ≥ 4000")
    elif decline_count is not None and decline_count >= 3500:
        base = "弱势"
        notes.append(f"跌家数 {decline_count} ≥ 3500")

    # 2) 涨跌比 < 0.5（宽度失衡）
    if weak_breadth_flag:
        notes.append(f"涨跌比 {adv_dec_ratio:.2f} < 0.5（宽度失衡）")
        if base in ("中性", "强势"):
            base = "弱势"

    # 3) 跌停家数显著
    if limit_down_count is not None:
        if limit_down_count >= 100:
            notes.append(f"跌停 {limit_down_count} 家（>= 100）")
            if base in ("中性", "强势"): base = "弱势"
        elif limit_down_count >= 50:
            notes.append(f"跌停 {limit_down_count} 家（>= 50）")
            if base == "中性": base = "弱势"

    # 4) 炸板率高
    if burst_rate is not None and burst_rate >= 0.5:
        notes.append(f"炸板率 {burst_rate*100:.0f}%（>= 50%）")
        if base == "中性": base = "弱势"

    # 5) 上证显著下跌
    if index_change_pct is not None and index_change_pct <= -2.0:
        notes.append(f"上证 {index_change_pct:+.2f}%（深度下跌）")
        if base in ("中性", "强势"): base = "弱势"

    # 6) 全部正面：score 高 + 涨多跌少 + 涨停可观，且无任何负面信号 → 强势
    #    用 raw 值判，避免边界精度丢失
    positive = (
        score is not None and score >= 7
        and adv_dec_ratio_raw is not None and adv_dec_ratio_raw >= 1.5
        and (limit_up_count is None or limit_up_count >= 30)
    )
    if not notes and positive:
        base = "强势"
        notes.append(f"涨跌比 {adv_dec_ratio:.2f} 健康，无明显负面信号")

    desc = "；".join(notes) if notes else "盘面无明显异常"
    return (base, desc, weak_breadth_flag, breadth_desc, adv_dec_ratio, burst_rate)


def _pick_top_sectors(board_list: list, top_n: int = 5) -> list:
    """
    从 board_df_cache 里筛主线板块（剔除 noise blocklist），按 pct_chg 倒序取 top_n。
    返回 list[dict]，每项含 name/pct_chg/up_count/down_count/leader/leader_pct。
    """
    filtered = []
    for item in board_list:
        name = str(item.get("name", "")).strip()
        if not name or _is_noise_sector(name):
            continue
        filtered.append({
            "name":       name,
            "pct_chg":    _safe_float(item.get("pct_chg")),
            "up_count":   _safe_int(item.get("up_count")),
            "down_count": _safe_int(item.get("down_count")),
            "leader":     str(item.get("领涨股票", "") or "").strip(),
            "leader_pct": _safe_float(item.get("领涨股票-涨跌幅")),
        })
    # 按 pct_chg 倒序
    filtered.sort(key=lambda x: x["pct_chg"] if x["pct_chg"] is not None else -999, reverse=True)
    return filtered[:top_n]


def build_market_daily(report_date: str) -> dict:
    """
    主入口：构建单日 market_daily 快照（dict）。
    """
    print(f"[market_daily] report_date={report_date}")
    record: dict = {
        "report_date":               report_date,
        "data_date":                 "",

        # —— V1.4 原系统情绪分（保留，仅反映"原系统打的分"）——
        "market_sentiment_score_raw":   "",
        "market_sentiment_raw_verdict": "",
        "sentiment_data_status":        "missing",   # missing / partial / ok

        # —— 复盘观察口径（V2 新增，基于真实赚钱效应）——
        "sentiment_detail_available":   "False",
        "market_env_verdict":           "",          # 数据不足 / 极弱 / 弱势 / 中性 / 强势
        "market_env_desc":              "",
        "weak_breadth_flag":            "",         # True / False / ""(缺数据)
        "breadth_desc":                 "",

        # —— 真实赚钱效应明细字段（第一阶段无 API，先留空）——
        "advance_count":                "",
        "decline_count":                "",
        "advance_decline_ratio":        "",
        "limit_up_count":               "",
        "limit_down_count":             "",
        "burst_count":                  "",
        "burst_rate":                   "",
        "index_change_pct":             "",
        "total_amount":                 "",

        # —— 主线板块 ——
        "sector_data_status":           "missing",   # ok / missing / stale / error / mismatch / unknown
        "sector_data_date":             "",
        "sector_filter_applied":        "noise_blocklist",
        "sector_data_freshness_detail": "",          # 中文，描述新鲜度校验结果

        # 元数据
        "built_at":                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_files":                 "",
    }
    # 顶级板块字段先占位（top_sector_1..5）
    for i in range(1, 6):
        record[f"top_sector_{i}_name"]       = ""
        record[f"top_sector_{i}_pct_chg"]    = ""
        record[f"top_sector_{i}_up_count"]   = ""
        record[f"top_sector_{i}_down_count"] = ""
        record[f"top_sector_{i}_leader"]     = ""
        record[f"top_sector_{i}_leader_pct"] = ""

    source_files = []
    score = None   # 后面 _judge_market_env 要用

    # —— 1) trade_review.csv：取 market_sentiment + data_date ——
    tr_info = _load_trade_review_for_date(report_date)
    if tr_info is None:
        print(f"  ⚠️ trade_review.csv 中无 report_date={report_date} 的记录")
        record["sentiment_data_status"] = "missing"
    else:
        source_files.append("trade_review.csv")
        record["data_date"] = tr_info["data_date"]
        score = tr_info["market_sentiment"]
        if score is not None:
            record["market_sentiment_score_raw"]   = round(score, 2)
            record["market_sentiment_raw_verdict"] = _verdict_raw_score(score)
            # 第一阶段无 API，细分字段缺 → partial
            record["sentiment_data_status"]        = "partial"
        else:
            record["sentiment_data_status"]        = "missing"
        print(f"  ✓ trade_review: data_date={record['data_date']!r} "
              f"raw_score={record['market_sentiment_score_raw']!r} "
              f"raw_verdict={record['market_sentiment_raw_verdict']!r}")

    # —— 1b) market_breadth：真实赚钱效应明细（同日 cache，不 fallback）——
    breadth = _load_market_breadth_cache(report_date)
    if breadth is None:
        print(f"  ⚠️ market_breadth_{report_date}.csv 缺失，真实赚钱效应保持数据不足")
    else:
        source_files.append(f"market_breadth_{report_date}.csv")
        breadth_status = str(breadth.get("status", "")).strip() or "missing"
        for k in (
            "advance_count", "decline_count", "advance_decline_ratio",
            "limit_up_count", "limit_down_count", "burst_count",
            "burst_rate", "index_change_pct", "total_amount",
        ):
            if str(breadth.get(k, "")).strip() != "":
                record[k] = breadth[k]
        print(
            f"  ✓ market_breadth: status={breadth_status!r} "
            f"missing={breadth.get('missing_fields', '') or '—'}"
        )

    # —— 1c) 真实赚钱效应判定（基于明细字段，缺数据时降级为"数据不足"）——
    ac = _safe_int(record["advance_count"])
    dc = _safe_int(record["decline_count"])
    lu = _safe_int(record["limit_up_count"])
    ld = _safe_int(record["limit_down_count"])
    bc = _safe_int(record["burst_count"])
    ix = _safe_float(record["index_change_pct"])
    ta = _safe_float(record["total_amount"])
    env_verdict, env_desc, weak_flag, breadth_desc, adr, br = _judge_market_env(
        score, ac, dc, lu, ld, bc, ix, ta
    )
    record["market_env_verdict"] = env_verdict
    record["market_env_desc"]    = env_desc
    record["weak_breadth_flag"]  = "" if (ac is None and dc is None) else ("True" if weak_flag else "False")
    record["breadth_desc"]       = breadth_desc
    if adr is not None: record["advance_decline_ratio"] = adr
    if br  is not None: record["burst_rate"]            = br
    # detail_available：所有 6 项核心明细（adv/dec/lu/ld/index/total_amount）都有 → True
    detail_have = sum(x is not None for x in (ac, dc, lu, ld, ix, ta))
    if detail_have == 6:
        record["sentiment_data_status"]    = "ok"
        record["sentiment_detail_available"] = "True"
    elif detail_have > 0:
        record["sentiment_data_status"]    = "partial"
        record["sentiment_detail_available"] = "False"
    # 否则保持原值（missing / partial）

    print(f"  ✓ env_verdict={env_verdict!r}  weak_breadth={record['weak_breadth_flag']!r}  "
          f"detail_have={detail_have}/6")

    # —— 2) board_df_cache：主线板块 Top 5（方案 E · 按 report_date 加载）——
    # 核心修复（用户原话）：
    #   - cache 路径用 report_date，不再用 data_date
    #   - 不允许 fallback 到前一日 cache
    #   - mtime 必须 >= report_date 当日 15:00（盘后数据）才算 fresh
    is_fresh, fresh_status, mtime_str, fresh_detail = _check_board_cache_freshness(
        record["report_date"]
    )
    record["sector_data_status"]            = fresh_status
    record["sector_data_date"]              = record["report_date"]   # ← 改用 report_date
    record["sector_data_freshness_detail"]  = fresh_detail
    print(f"  [board cache] freshness={fresh_status!r}  mtime={mtime_str}")
    print(f"  [board cache] detail={fresh_detail}")

    if not is_fresh:
        # 任何 missing/stale/unknown → 拒绝生成 Top 5；top_sector_1..5_* 保持空
        print(f"  ⚠️ sector_data_status={fresh_status!r}，拒绝生成 Top 5 主线板块")
    else:
        # 新鲜：用 report_date 加载 cache（不再用 data_date）
        board_list = _load_board_df_cache(record["report_date"])
        if board_list is None:
            record["sector_data_status"]           = "missing"
            record["sector_data_freshness_detail"] = "freshness 校验通过但读盘失败"
            print(f"  ⚠️ 读 cache 失败，sector_data_status 降级为 missing")
        else:
            source_files.append(f"board_df_cache_{record['report_date']}.json")
            top = _pick_top_sectors(board_list, top_n=5)
            if not top:
                record["sector_data_status"]           = "missing"
                record["sector_data_freshness_detail"] = "Top 5 为空（被 noise blocklist 过滤）"
            else:
                for i, sec in enumerate(top, start=1):
                    record[f"top_sector_{i}_name"]       = sec["name"]
                    pc = sec["pct_chg"]
                    record[f"top_sector_{i}_pct_chg"]    = "" if pc is None else round(pc, 2)
                    record[f"top_sector_{i}_up_count"]   = "" if sec["up_count"]   is None else sec["up_count"]
                    record[f"top_sector_{i}_down_count"] = "" if sec["down_count"] is None else sec["down_count"]
                    record[f"top_sector_{i}_leader"]     = sec["leader"]
                    lp = sec["leader_pct"]
                    record[f"top_sector_{i}_leader_pct"] = "" if lp is None else round(lp, 2)
                print(f"  ✓ board_df_cache: 主线板块 Top {len(top)}")
                for i, sec in enumerate(top, start=1):
                    pc = sec["pct_chg"]
                    pc_s = f"{pc:+.2f}%" if pc is not None else "—"
                    print(f"      {i}. {sec['name']:18s} {pc_s:>8s}  "
                          f"涨停 {sec['up_count']}  领涨 {sec['leader']}")

    record["source_files"] = " | ".join(source_files) if source_files else ""
    return record


def write_csv(record: dict, out_path: Path) -> None:
    """把 record 写成单行 CSV（含表头）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(record.keys())
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(record)


def main() -> int:
    p = argparse.ArgumentParser(
        description="构建单日大盘环境 + 主线板块快照（只读、不接策略）"
    )
    p.add_argument("--report-date", type=str, default=None,
                   help="目标 report_date (YYYYMMDD)，默认今天")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印不写文件")
    args = p.parse_args()

    report_date = args.report_date or datetime.now().strftime("%Y%m%d")
    if not (len(report_date) == 8 and report_date.isdigit()):
        print(f"❌ report_date 格式错误: {report_date!r} (应为 YYYYMMDD)")
        return 2

    print("=" * 60)
    print(f"build_market_daily.py · report_date={report_date}")
    print("=" * 60)
    record = build_market_daily(report_date)

    out_path = OUT_DIR / f"market_daily_{report_date}.csv"
    if args.dry_run:
        print()
        print("─── DRY-RUN：以下为 record 内容（未写入）───")
        for k, v in record.items():
            if v not in ("", None):
                print(f"  {k:30s} = {v!r}")
        print(f"\n  （未写入：{out_path}）")
    else:
        write_csv(record, out_path)
        print(f"\n✅ 已写入：{out_path.relative_to(BASE_DIR)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
