"""
scripts/build_tomorrow_plan.py
================================
V1.6 Stage 1：明日交易计划派生脚本（严格只读 + 派生写）

定位（用户原话，严格收窄）：
  - 第一阶段只生成计划，不接 dashboard、不接推荐、不接 check_buy
  - 不影响 buy_signal_0935、simulated_trade_return、V1.4 买入规则、V1.5 资金条件
  - 不修改 trade_review.csv、launchd
  - 不运行 python run.py 任何子命令

输入（严格只读）：
  - output/market_daily/market_daily_{report_date}.csv     ← 大盘环境 + 主线板块
  - output/trade_review.csv                                ← 今日候选股 + 已买入
  - output/candidate_lifecycle/candidate_lifecycle_{report_date}.csv  ← 止损情况
  - output/money_flow_simulation/money_flow_simulation_{report_date}.csv  ← 资金模拟
  - data_fetcher.next_trading_date()                       ← 算 next_trade_date

输出（仅派生）：
  - output/tomorrow_plan/tomorrow_plan_{report_date}.csv
  - output/tomorrow_plan/tomorrow_plan_{report_date}.md
  - output/tomorrow_plan/tomorrow_plan_latest.csv（覆盖式）
  - output/tomorrow_plan/tomorrow_plan_latest.md（覆盖式）

核心原则（用户原话照搬，写进代码注释 + MD 文件提示）：
  "计划看好 ≠ 直接买入。第二天 9:36 仍由 V1.4/V1.5 规则决定是否模拟买入。"

数据不足时降级（用户原话）：
  - market_state = 数据不足
  - trade_permission = 只观察
  - risk_level = 高
  - manual_review_required = True
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR   = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR  = BASE_DIR / "output"
PLAN_DIR    = OUTPUT_DIR / "tomorrow_plan"
TR_CSV      = OUTPUT_DIR / "trade_review.csv"
MD_DIR      = OUTPUT_DIR / "market_daily"
LC_DIR      = OUTPUT_DIR / "candidate_lifecycle"
MF_DIR      = OUTPUT_DIR / "money_flow_simulation"

PLAN_VERSION = "v1"


# ════════════════════════════════════════════════════════════════════
# CSV schema（28 列）— 字段顺序固定，便于 dashboard 后续接入
# ════════════════════════════════════════════════════════════════════
CSV_FIELDS = [
    # 标识
    "report_date", "next_trade_date", "plan_version", "built_at",
    # 市场状态判定
    "market_state",                # 冰点 / 回暖 / 主升 / 分歧 / 退潮 / 数据不足
    "market_state_confidence",     # low / medium / high / manual
    "market_state_source",         # auto / semi_auto / manual_override
    "trade_permission",            # 正常交易 / 小仓试错 / 只做主线核心 / 只观察 / 禁止交易
    "risk_level",                  # 低 / 中 / 高
    # 方向建议
    "allowed_themes",
    "avoid_themes",
    "focus_stocks",
    "focus_stocks_reason",
    # 触发/失效条件（人工补充）
    "trigger_conditions",
    "invalidation_conditions",
    "emergency_plan",
    # 策略描述
    "tomorrow_strategy_desc",
    # 数据完整度审计
    "sentiment_data_status",
    "sector_data_status",
    "mf_simulation_available",
    "lifecycle_available",
    # 自动 vs 人工标记
    "auto_fields_filled",
    "semi_auto_fields_filled",
    "manual_review_required",
    "manual_reviewed_at",
    # 元数据
    "source_files",
    "notes",
]


# ════════════════════════════════════════════════════════════════════
# 规则映射（用户原话照搬）
# ════════════════════════════════════════════════════════════════════
# 复盘观察口径 → 市场状态 5 态映射（"回暖"需对比昨日，Stage 1 不自动判，留人工）
ENV_VERDICT_TO_MARKET_STATE = {
    "强势":     ("主升", "high"),
    "中性":     ("分歧", "medium"),
    "弱势":     ("退潮", "medium"),
    "极弱":     ("冰点", "high"),
    "数据不足": ("数据不足", "low"),
    "未知":     ("数据不足", "low"),
}

MARKET_STATE_TO_PERMISSION = {
    "主升":     "正常交易",
    "回暖":     "小仓试错",
    "分歧":     "只做主线核心",
    "退潮":     "只观察",
    "冰点":     "禁止交易",
    "数据不足": "只观察",   # 保守默认（用户原话）
}

MARKET_STATE_TO_RISK = {
    "主升":     "中",     # 主升也有高位回落风险
    "回暖":     "中",
    "分歧":     "高",
    "退潮":     "高",
    "冰点":     "高",
    "数据不足": "高",     # 数据不足时保守
}


def _data_gap_reasons(
    market_state: str,
    sentiment_data_status: str,
    sector_data_status: str,
    allowed_themes: list,
) -> list:
    """Return conservative safety reasons that require observation mode."""
    reasons = []
    if market_state == "数据不足":
        reasons.append("market_state=数据不足")
    if sentiment_data_status != "ok":
        reasons.append(f"sentiment_data_status={sentiment_data_status or 'missing'}")
    if sector_data_status != "ok":
        reasons.append(f"sector_data_status={sector_data_status or 'missing'}")
    if not allowed_themes:
        reasons.append("allowed_themes 为空")
    return reasons


# 默认 noise blocklist（与 build_market_daily.py 保持一致）
SECTOR_NOISE_BLOCKLIST_KEYWORDS = [
    "融资融券", "深股通", "沪股通", "创业板综",
    "富时罗素", "MSCI", "证金持仓", "QFII持仓", "AH股", "机构重仓",
    "小盘股", "大盘股", "中盘股",
    "昨日连板", "昨日涨停", "昨日首板", "昨日打二板",
    "昨日高振幅", "最近多板", "东方财富热股",
    "次新股",
]


# ════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════

def _safe_str(v) -> str:
    if v is None: return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "null"): return ""
    return s


def _safe_float(v) -> Optional[float]:
    s = _safe_str(v)
    if not s: return None
    try:
        f = float(s)
        return None if f != f else f
    except (ValueError, TypeError):
        return None


def _safe_bool_str(v) -> Optional[bool]:
    s = _safe_str(v).lower()
    if s in ("true", "1", "yes"):  return True
    if s in ("false", "0", "no"):  return False
    return None


def _next_trading_date_safe(report_date: str) -> str:
    """调 data_fetcher.next_trading_date；失败时按 weekday +1 兜底。"""
    try:
        from data_fetcher import next_trading_date
        return next_trading_date(report_date)
    except Exception:
        from datetime import datetime as _dt, timedelta as _td
        d = _dt.strptime(report_date, "%Y%m%d").date()
        nd = d + _td(days=1)
        while nd.weekday() >= 5:
            nd += _td(days=1)
        return nd.strftime("%Y%m%d")


# ════════════════════════════════════════════════════════════════════
# 数据加载（全部容错；缺文件返回 None / 空 dict / 空 list）
# ════════════════════════════════════════════════════════════════════

def _load_market_daily(report_date: str) -> Optional[dict]:
    fp = MD_DIR / f"market_daily_{report_date}.csv"
    if not fp.exists():
        return None
    try:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        return rows[0] if rows else None
    except Exception:
        return None


def _load_trade_review_for_date(report_date: str) -> list:
    if not TR_CSV.exists():
        return []
    try:
        with TR_CSV.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return [r for r in reader if _safe_str(r.get("report_date")) == report_date]
    except Exception:
        return []


def _load_candidate_lifecycle(report_date: str) -> list:
    fp = LC_DIR / f"candidate_lifecycle_{report_date}.csv"
    if not fp.exists():
        return []
    try:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _load_mf_simulation(report_date: str) -> list:
    fp = MF_DIR / f"money_flow_simulation_{report_date}.csv"
    if not fp.exists():
        return []
    try:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


# ════════════════════════════════════════════════════════════════════
# 派生逻辑
# ════════════════════════════════════════════════════════════════════

def _derive_market_state(daily: Optional[dict]) -> tuple:
    """
    返回 (market_state, confidence, source)
    Stage 1 仅做 auto 推导；"回暖"留人工 override 选项。

    保守降级规则（用户原话）：
      - sentiment_data_status != "ok" → 数据不足
      - market_env_verdict in (数据不足/未知) → 数据不足
      - sector_data_status != "ok" → 数据不足（主线板块缺失/过期也降级）
    """
    if daily is None:
        return ("数据不足", "low", "auto")
    env_v = _safe_str(daily.get("market_env_verdict")) or "未知"
    sentiment_data = _safe_str(daily.get("sentiment_data_status")) or "missing"
    sector_data    = _safe_str(daily.get("sector_data_status"))    or "missing"

    # 数据不足时保守
    if sentiment_data != "ok" or env_v in ("数据不足", "未知"):
        return ("数据不足", "low", "auto")
    # 🆕 主线板块数据不新鲜 → 不允许判 market_state（保守降级）
    if sector_data != "ok":
        return ("数据不足", "low", "auto")

    state, conf = ENV_VERDICT_TO_MARKET_STATE.get(env_v, ("数据不足", "low"))
    return (state, conf, "auto")


def _derive_allowed_themes(daily: Optional[dict], top_n: int = 5) -> list:
    """
    从 market_daily Top N 取主线板块（已在 build_market_daily 阶段剔除 noise）。

    🆕 新鲜度守卫（用户原话）：
      - sector_data_status != "ok" → 直接返回空 list
      - 旧 cache 不会再被写入 tomorrow_plan
    """
    if daily is None:
        return []
    # 🆕 守卫：板块数据不新鲜（missing / stale / mismatch / unknown）→ 拒绝生成
    sector_status = _safe_str(daily.get("sector_data_status")) or "missing"
    if sector_status != "ok":
        return []

    out = []
    for i in range(1, top_n + 1):
        name = _safe_str(daily.get(f"top_sector_{i}_name"))
        if not name: continue
        pc = _safe_float(daily.get(f"top_sector_{i}_pct_chg"))
        up = _safe_str(daily.get(f"top_sector_{i}_up_count"))
        leader = _safe_str(daily.get(f"top_sector_{i}_leader"))
        leader_pct = _safe_float(daily.get(f"top_sector_{i}_leader_pct"))
        desc = f"{name}"
        if pc is not None:     desc += f"（{pc:+.2f}%"
        if up:                 desc += f"，涨停 {up}"
        if leader:             desc += f"，领涨 {leader}"
        if leader_pct is not None: desc += f" {leader_pct:+.2f}%"
        desc += "）"
        out.append({
            "name": name, "pct_chg": pc, "up_count": up,
            "leader": leader, "leader_pct": leader_pct, "desc": desc,
        })
    return out


def _derive_avoid_themes() -> list:
    """默认 noise blocklist，第一阶段不区分 ETF/宽基/情绪面。"""
    return [
        "宽基类（融资融券、深股通、沪股通、创业板综、富时罗素、机构重仓）",
        "情绪面（昨日连板、昨日涨停、昨日首板、东方财富热股）",
        "市值分类（小盘股、大盘股、中盘股）",
        "次新股",
    ]


def _derive_focus_stocks(tr_rows: list, mf_rows: list) -> tuple:
    """
    核心观察股 = 今日已买入票 + theme_auto 模式 rank=1 的票。
    去重，最多 5 只。
    返回 (focus_codes_list, reason_text)
    """
    seen = set()
    out = []
    # 1) 已买入票
    for r in tr_rows:
        sig = _safe_bool_str(r.get("buy_signal_0935"))
        if sig is True:
            code = _safe_str(r.get("stock_code")).zfill(6)
            if code and code not in seen:
                seen.add(code)
                name = _safe_str(r.get("stock_name"))
                mode = _safe_str(r.get("mode"))
                theme = _safe_str(r.get("theme_name"))
                score = _safe_float(r.get("total_score"))
                reason_parts = []
                if mode: reason_parts.append(f"{mode}模式买入")
                if theme: reason_parts.append(f"主题:{theme}")
                if score is not None: reason_parts.append(f"总分{score:.1f}")
                out.append({
                    "code": code, "name": name,
                    "reason": " / ".join(reason_parts) or "今日已买入",
                })

    # 2) theme_auto rank=1
    for r in tr_rows:
        if _safe_str(r.get("mode")) != "theme_auto": continue
        if _safe_str(r.get("rank")) != "1": continue
        code = _safe_str(r.get("stock_code")).zfill(6)
        if code and code not in seen:
            seen.add(code)
            name = _safe_str(r.get("stock_name"))
            theme = _safe_str(r.get("theme_name"))
            ts = _safe_float(r.get("theme_strength"))
            reason_parts = ["theme_auto 主题龙头"]
            if theme: reason_parts.append(f"主题:{theme}")
            if ts is not None: reason_parts.append(f"主题强度 {ts:.0f}")
            out.append({
                "code": code, "name": name,
                "reason": " / ".join(reason_parts),
            })

    return (out[:5], None)


def _has_stop_loss_today(lc_rows: list) -> tuple:
    """
    检查今日是否有止损票（已买入 + T+1 止损）。
    返回 (n_stopped, list_of_dicts)
    """
    stopped = []
    for r in lc_rows:
        # candidate_lifecycle 只在有止损票时才有数据；空文件 / 空表说明无止损
        sim_ret = _safe_float(r.get("simulated_trade_return"))
        if sim_ret is not None and sim_ret < 0:
            stopped.append({
                "code": _safe_str(r.get("stock_code")).zfill(6),
                "name": _safe_str(r.get("stock_name")),
                "sim_ret": sim_ret,
                "washout": _safe_str(r.get("suspected_washout_flag")) == "True",
            })
    return (len(stopped), stopped)


def _build_default_trigger_invalidation(
    state: str, allowed_themes: list, focus_stocks: list
) -> tuple:
    """
    生成 trigger / invalidation / emergency 的模板骨架（人工后续补充）。
    返回 (trigger, invalidation, emergency)，每项都是中文字符串。
    """
    # 通用触发条件骨架
    trigger_lines = [
        "[需人工确认] 大盘高开 0% ~ +0.8% 且 涨家数 >= 1800",
    ]
    if allowed_themes:
        names = "、".join(t["name"] for t in allowed_themes[:3])
        trigger_lines.append(f"[需人工确认] 主线板块（{names}）继续高开高走，龙头未一字")
    if focus_stocks:
        names = "、".join(s["name"] for s in focus_stocks[:3])
        trigger_lines.append(f"[需人工确认] 核心股（{names}）开盘正常、9:36 站上开盘价")
    trigger = " ｜ ".join(trigger_lines)

    # 通用失效条件骨架
    invalidation_lines = [
        "[需人工确认] 大盘低开 < -1% 且 涨家数 < 1500",
        "[需人工确认] 主线板块整体低开 < -1%",
    ]
    if focus_stocks:
        invalidation_lines.append(
            f"[需人工确认] 核心股（{focus_stocks[0]['name']}）低开 < -2%"
        )
    invalidation = " ｜ ".join(invalidation_lines)

    # 通用应急预案骨架
    emergency_lines = [
        "[需人工确认] 核心股低开低走 → 当日放弃，等修复",
        "[需人工确认] 主线扩散 → 仍只做核心 + 中军，不追后排",
        "[需人工确认] 市场弱于预期 → 不开新仓，已持仓按 V1.4 止损规则",
    ]
    if state == "数据不足":
        emergency_lines.insert(0, "⚠️ 数据不足，强烈建议人工先复核 market_daily 完整度")
    emergency = " ｜ ".join(emergency_lines)

    return (trigger, invalidation, emergency)


def _build_strategy_desc(state: str, permission: str, allowed_themes: list) -> str:
    """一句话明日策略，骨架由 state + permission 拼接。"""
    base = {
        "主升":     "积极仓位（5-7 成），主线核心 + 中军可参与",
        "回暖":     "小仓试错（≤3 成），只做最强主线核心",
        "分歧":     "去弱留强，只做主线核心，避免后排",
        "退潮":     "降低仓位（≤2 成），只观察不追",
        "冰点":     "空仓等待，不交易",
        "数据不足": "暂不判定，今日只观察，等数据补全 + 人工确认",
    }
    desc = base.get(state, "数据不足，今日只观察")
    if allowed_themes and state in ("主升", "回暖", "分歧"):
        names = "、".join(t["name"] for t in allowed_themes[:3])
        desc += f"；优先方向：{names}"
    return f"[需人工确认] {desc}"


# ════════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════════

def build_tomorrow_plan(report_date: str) -> dict:
    """
    构建明日交易计划 dict。
    所有失败路径都降级为"数据不足"，绝不抛异常给上层。
    """
    next_td = _next_trading_date_safe(report_date)
    built_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 加载输入 ──
    daily   = _load_market_daily(report_date)
    tr_rows = _load_trade_review_for_date(report_date)
    lc_rows = _load_candidate_lifecycle(report_date)
    mf_rows = _load_mf_simulation(report_date)

    source_files = []
    if daily is not None:
        source_files.append(f"market_daily_{report_date}.csv")
    if tr_rows:
        source_files.append("trade_review.csv")
    if lc_rows is not None:
        # candidate_lifecycle 可能是空表也算"已运行"
        lc_fp = LC_DIR / f"candidate_lifecycle_{report_date}.csv"
        if lc_fp.exists():
            source_files.append(f"candidate_lifecycle_{report_date}.csv")
    if mf_rows:
        source_files.append(f"money_flow_simulation_{report_date}.csv")

    # ── 派生 ──
    state, confidence, state_source = _derive_market_state(daily)
    allowed_themes_data = _derive_allowed_themes(daily, top_n=5)
    avoid_themes_data   = _derive_avoid_themes()
    focus_stocks_data, _ = _derive_focus_stocks(tr_rows, mf_rows)
    n_stopped, _stopped_list = _has_stop_loss_today(lc_rows)

    # 审计字段
    sentiment_data_status = _safe_str(daily.get("sentiment_data_status")) if daily else "missing"
    sector_data_status    = _safe_str(daily.get("sector_data_status"))    if daily else "missing"
    mf_available          = bool(mf_rows)
    lifecycle_available   = bool(lc_rows is not None and (LC_DIR / f"candidate_lifecycle_{report_date}.csv").exists())

    permission = MARKET_STATE_TO_PERMISSION.get(state, "只观察")
    risk_level = MARKET_STATE_TO_RISK.get(state, "高")
    data_gap_reasons = _data_gap_reasons(
        state, sentiment_data_status, sector_data_status, allowed_themes_data
    )
    if data_gap_reasons:
        permission = "只观察"
        risk_level = "高"

    trigger, invalidation, emergency = _build_default_trigger_invalidation(
        state, allowed_themes_data, focus_stocks_data
    )
    strategy_desc = _build_strategy_desc(state, permission, allowed_themes_data)

    # 是否需要人工确认
    manual_review_required = (
        state == "数据不足"
        or sentiment_data_status != "ok"
        or sector_data_status    != "ok"   # 🆕 主线板块数据缺失/过期也需要人工确认
        or not allowed_themes_data
        or "[需人工确认]" in (trigger + invalidation + emergency + strategy_desc)
    )

    # 🆕 notes 增补：主线板块数据缺失/过期时明确写入（用户原话）
    notes_parts = [f"n_stopped_today={n_stopped}"]
    if data_gap_reasons:
        notes_parts.append(
            "数据不足/主线缺失，仅观察；原因：" + "、".join(data_gap_reasons)
        )
    if sector_data_status != "ok":
        sector_detail = ""
        if daily is not None:
            sector_detail = _safe_str(daily.get("sector_data_freshness_detail"))
        sector_note = (
            f"主线板块数据 status={sector_data_status}（{sector_detail}）"
            f"，禁止自动生成 allowed_themes" if sector_detail
            else f"主线板块数据 status={sector_data_status}，禁止自动生成 allowed_themes"
        )
        notes_parts.append(sector_note)

    # 序列化字符串
    allowed_themes_str = "|".join(t["name"] for t in allowed_themes_data)
    avoid_themes_str   = "|".join(avoid_themes_data)
    focus_stocks_str   = "|".join(f"{s['code']}:{s['name']}" for s in focus_stocks_data)
    focus_stocks_reason = "|".join(s["reason"] for s in focus_stocks_data)

    record = {
        # 标识
        "report_date":              report_date,
        "next_trade_date":          next_td,
        "plan_version":             PLAN_VERSION,
        "built_at":                 built_at,
        # 市场状态
        "market_state":             state,
        "market_state_confidence":  confidence,
        "market_state_source":      state_source,
        "trade_permission":         permission,
        "risk_level":               risk_level,
        # 方向
        "allowed_themes":           allowed_themes_str,
        "avoid_themes":             avoid_themes_str,
        "focus_stocks":             focus_stocks_str,
        "focus_stocks_reason":      focus_stocks_reason,
        # 触发/失效
        "trigger_conditions":       trigger,
        "invalidation_conditions":  invalidation,
        "emergency_plan":           emergency,
        # 策略
        "tomorrow_strategy_desc":   strategy_desc,
        # 数据审计
        "sentiment_data_status":    sentiment_data_status,
        "sector_data_status":       sector_data_status,
        "mf_simulation_available":  "True" if mf_available else "False",
        "lifecycle_available":      "True" if lifecycle_available else "False",
        # 自动 vs 人工
        "auto_fields_filled":       "True",
        "semi_auto_fields_filled":  "True",
        "manual_review_required":   "True" if manual_review_required else "False",
        "manual_reviewed_at":       "",
        # 元数据
        "source_files":             "|".join(source_files) if source_files else "",
        "notes":                    " ｜ ".join(notes_parts),
    }

    # —— 携带原始 data 给 MD 渲染（不进 CSV）——
    record["_allowed_themes_data"] = allowed_themes_data
    record["_focus_stocks_data"]   = focus_stocks_data
    record["_n_stopped_today"]     = n_stopped

    return record


# ════════════════════════════════════════════════════════════════════
# CSV 写出（28 列）
# ════════════════════════════════════════════════════════════════════

def write_csv(record: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    row = {k: record.get(k, "") for k in CSV_FIELDS}
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerow(row)


# ════════════════════════════════════════════════════════════════════
# MD 渲染（人类可读）
# ════════════════════════════════════════════════════════════════════

def render_md(record: dict) -> str:
    rd  = record["report_date"]
    ntd = record["next_trade_date"]
    state    = record["market_state"]
    perm     = record["trade_permission"]
    risk     = record["risk_level"]
    conf     = record["market_state_confidence"]
    src      = record["market_state_source"]
    strategy = record["tomorrow_strategy_desc"]
    trigger  = record["trigger_conditions"]
    invalid  = record["invalidation_conditions"]
    emergcy  = record["emergency_plan"]

    allowed_data = record.get("_allowed_themes_data", [])
    focus_data   = record.get("_focus_stocks_data",   [])
    n_stopped    = record.get("_n_stopped_today", 0)

    rd_fmt  = f"{rd[:4]}-{rd[4:6]}-{rd[6:8]}"
    ntd_fmt = f"{ntd[:4]}-{ntd[4:6]}-{ntd[6:8]}"

    need_review = record["manual_review_required"] == "True"
    review_banner = (
        "⚠️ **待人工确认** — 自动判定已完成，部分字段需要人工补充"
        if need_review else "✅ **已确认**"
    )

    # —— 数据完整度审计 ——
    audit_lines = []
    sds = record["sentiment_data_status"]
    audit_lines.append(f"{'✅' if sds == 'ok' else '⚠️'} 大盘情绪数据：{sds}")
    sec = record["sector_data_status"]
    audit_lines.append(f"{'✅' if sec == 'ok' else '⚠️'} 主线板块数据：{sec}")
    mfa = record["mf_simulation_available"]
    audit_lines.append(
        f"{'✅' if mfa == 'True' else '❌'} V1.5-alpha 资金模拟：{'已运行' if mfa == 'True' else '未运行'}"
    )
    lca = record["lifecycle_available"]
    audit_lines.append(
        f"{'✅' if lca == 'True' else '❌'} 候选生命周期（止损跟踪）：{'已生成' if lca == 'True' else '未生成'}"
    )
    if n_stopped:
        audit_lines.append(f"🔴 今日有 {n_stopped} 只止损票，请人工核查应急预案是否合理")

    # —— allowed_themes 表格 ——
    if allowed_data:
        themes_md = "| # | 板块名 | 涨幅 | 涨停家数 | 领涨股票 | 领涨涨幅 |\n"
        themes_md += "|---|---|---:|---:|---|---:|\n"
        for i, t in enumerate(allowed_data, 1):
            pc = f"{t['pct_chg']:+.2f}%" if t['pct_chg'] is not None else "—"
            lp = f"{t['leader_pct']:+.2f}%" if t['leader_pct'] is not None else "—"
            themes_md += f"| {i} | **{t['name']}** | {pc} | {t['up_count'] or '—'} | {t['leader'] or '—'} | {lp} |\n"
    else:
        themes_md = "_（主线板块数据未生成或全部被 noise 过滤）_"

    # —— focus_stocks 列表 ——
    if focus_data:
        focus_md = "| 代码 | 名称 | 入选原因 |\n|---|---|---|\n"
        for s in focus_data:
            focus_md += f"| `{s['code']}` | **{s['name']}** | {s['reason']} |\n"
    else:
        focus_md = "_（今日无核心观察股）_"

    # —— 人工待办清单 ——
    todo_lines = []
    if state == "数据不足":
        todo_lines.append("- [ ] 复核 `market_state`（自动判定为「数据不足」，是否需要人工 override？）")
    if "[需人工确认]" in strategy:
        todo_lines.append("- [ ] 补充 `tomorrow_strategy_desc`（一句话明日策略）")
    if "[需人工确认]" in trigger:
        todo_lines.append("- [ ] 补充 `trigger_conditions`（明日可以做的具体催化/位置）")
    if "[需人工确认]" in invalid:
        todo_lines.append("- [ ] 补充 `invalidation_conditions`（计划失效的具体阈值）")
    if "[需人工确认]" in emergcy:
        todo_lines.append("- [ ] 补充 `emergency_plan`（应急预案的具体动作）")
    todo_lines.append("- [ ] 确认完毕后填入 `manual_reviewed_at` 时间戳")
    todo_md = "\n".join(todo_lines) if todo_lines else "_（无待办）_"

    src_files = record["source_files"] or "—"

    return f"""# 明日交易计划 · {ntd_fmt}

**复盘日**：{rd_fmt}
**指导交易日**：{ntd_fmt}
**生成时间**：{record["built_at"]}
**审核状态**：{review_banner}

---

## 📊 一、市场状态判定

| 维度 | 值 |
|---|---|
| 市场状态 | **{state}** （置信度：{conf}） |
| 交易权限 | **{perm}** |
| 风险等级 | **{risk}** |
| 判定来源 | {src} |
| 计划版本 | {record["plan_version"]} |

---

## 🎯 二、明日一句话策略

> {strategy}

---

## 🔥 三、允许方向（基于今日 Top 5 主线板块，半自动）

{themes_md}

> ⚠️ 以上为系统从今日主线板块自动推导，**需人工复核「主线是否真成立」**：
> - 板块成交额是否明显放大？
> - 是否有 3-5 只个股形成联动？
> - 有明确龙头/中军/补涨梯队？
> - 次日是否仍有溢价或弱转强可能？

---

## 🚫 四、回避方向（默认 noise blocklist）

{chr(10).join('- ' + t for t in record["avoid_themes"].split("|") if t)}

---

## ⭐ 五、核心观察股

{focus_md}

> ⚠️ **观察 ≠ 买入**。第二天 9:36 仍由 V1.4 五条 + V1.5 资金条件决定是否模拟买入。

---

## ✅ 六、触发条件（明日可以做的情况）

{trigger}

## ❌ 七、失效条件（计划失效的情况）

{invalid}

## 🆘 八、应急预案

{emergcy}

---

## 📋 九、数据完整度审计

{chr(10).join(audit_lines)}

---

## ⚠️ 十、人工确认待办

{todo_md}

**确认完毕后**：在 dashboard 点"确认计划"或手动编辑 CSV 把 `manual_reviewed_at` 填入时间戳。

---

## 📑 元数据

- **数据来源**：{src_files}
- **note**：{record["notes"]}
- **plan_version**：{record["plan_version"]}

---

> ⚠️ **本计划由 V1.6 系统自动生成 + 待人工确认，仅作决策辅助**。
>
> **核心原则**：
> - 计划看好 ≠ 直接买入
> - 第二天 9:36 仍由 V1.4 五条买入规则 + V1.5 资金条件决定是否模拟买入
> - 本系统永远是模拟盘验证，不自动下单、不自动调仓位
>
> V1.6 第一阶段（Stage 1）：仅生成计划文件，不影响推荐、不影响买入、不写 trade_review.csv。
"""


# ════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════
# 覆盖保护（用户原话规则 · 防止静默覆盖人工确认版本）
# ════════════════════════════════════════════════════════════════════

# Exit code 约定
EXIT_OK              = 0
EXIT_GENERIC         = 1
EXIT_BAD_ARGS        = 2
EXIT_MANUAL_CONFIRMED = 5   # 已人工确认，拒绝默认覆盖

# --merge-keep-manual 模式下需要保留的字段（用户原话照搬）
MERGE_KEEP_FIELDS = (
    "trade_permission",
    "risk_level",
    "tomorrow_strategy_desc",
    "trigger_conditions",
    "invalidation_conditions",
    "emergency_plan",
    "manual_review_required",   # 保持 False
    "manual_reviewed_at",        # 保持原值
)


def _load_existing_plan(report_date: str) -> Optional[dict]:
    """读已存在的 tomorrow_plan_{report_date}.csv；不存在返回 None。"""
    fp = PLAN_DIR / f"tomorrow_plan_{report_date}.csv"
    if not fp.exists():
        return None
    try:
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        return rows[0] if rows else None
    except Exception as e:
        print(f"  [warn] 读已有 plan 失败（视为不存在）: {type(e).__name__}: {e}")
        return None


def _is_manually_reviewed(existing: Optional[dict]) -> tuple:
    """
    判定已有 plan 是否已人工确认。
    返回 (is_reviewed: bool, reason: str)

    判定（用户原话）：
      manual_review_required == "False" AND manual_reviewed_at 非空 → 已确认
    """
    if existing is None:
        return False, "文件不存在"
    rv = str(existing.get("manual_review_required", "True")).strip().lower()
    at = str(existing.get("manual_reviewed_at", "")).strip()
    if rv == "false" and at:
        return True, (
            f"已人工确认（manual_reviewed_at={at}，"
            f"trade_permission={existing.get('trade_permission', '')!r}）"
        )
    return False, (
        f"未确认（manual_review_required={rv!r}, manual_reviewed_at={at!r}）"
    )


def _merge_keep_manual(new_record: dict, existing: dict) -> dict:
    """
    把 existing 中人工字段合入 new_record（覆盖自动生成的版本）。
    其它字段（market_state / allowed_themes / focus_stocks 等）保持 new_record 的新值。
    """
    merged = dict(new_record)
    data_gap_reasons = _data_gap_reasons(
        str(new_record.get("market_state", "")).strip(),
        str(new_record.get("sentiment_data_status", "")).strip() or "missing",
        str(new_record.get("sector_data_status", "")).strip() or "missing",
        [t.strip() for t in str(new_record.get("allowed_themes", "")).split("|") if t.strip()],
    )
    kept_fields = []
    for k in MERGE_KEEP_FIELDS:
        if data_gap_reasons and k in ("trade_permission", "risk_level", "manual_review_required", "manual_reviewed_at"):
            continue
        if k in existing and str(existing.get(k, "")).strip():
            merged[k] = existing[k]
            kept_fields.append(k)
    if data_gap_reasons:
        merged["trade_permission"] = "只观察"
        merged["risk_level"] = "高"
        merged["manual_review_required"] = "True"
        merged["manual_reviewed_at"] = ""
        note = str(merged.get("notes", "")).strip()
        safety_note = (
            "merge-keep-manual 安全保护：当前数据不足/主线缺失，未保留旧的正常交易人工字段；原因："
            + "、".join(data_gap_reasons)
        )
        merged["notes"] = f"{note} ｜ {safety_note}" if note else safety_note
        print(f"  [merge-keep-manual] 安全保护：{safety_note}")
    print(f"  [merge-keep-manual] 保留 {len(kept_fields)} 个人工字段：{kept_fields}")
    return merged


def main() -> int:
    p = argparse.ArgumentParser(
        description="V1.6 Stage 1：明日交易计划派生脚本（只读 + 派生写）"
    )
    p.add_argument("--report-date", type=str, default=None,
                   help="复盘日 YYYYMMDD（默认今天）")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印不写文件")
    p.add_argument("--no-latest", action="store_true",
                   help="不写 tomorrow_plan_latest.* 软链接")
    # —— 覆盖保护（互斥）——
    group = p.add_mutually_exclusive_group()
    group.add_argument("--force", action="store_true",
                       help="强制覆盖已人工确认的 plan（包括人工文案字段）")
    group.add_argument("--merge-keep-manual", action="store_true",
                       help="重新生成自动字段，但保留 8 个人工字段（trade_permission / "
                            "risk_level / tomorrow_strategy_desc / trigger_conditions / "
                            "invalidation_conditions / emergency_plan / "
                            "manual_review_required=False / manual_reviewed_at 原值）")
    args = p.parse_args()

    report_date = args.report_date or datetime.now().strftime("%Y%m%d")
    if not (len(report_date) == 8 and report_date.isdigit()):
        print(f"❌ report_date 格式错误: {report_date!r}（应为 YYYYMMDD）")
        return EXIT_BAD_ARGS

    print("=" * 60)
    print(f"build_tomorrow_plan.py · report_date={report_date}")
    if args.force:               print(f"  覆盖模式: --force（强制覆盖人工字段）")
    if args.merge_keep_manual:   print(f"  覆盖模式: --merge-keep-manual（保留人工字段）")
    print("=" * 60)

    # —— 覆盖保护（用户原话核心规则）——
    existing = _load_existing_plan(report_date)
    is_reviewed, review_detail = _is_manually_reviewed(existing)
    print(f"[覆盖保护] {review_detail}")

    if is_reviewed and not (args.force or args.merge_keep_manual):
        # 默认拒绝覆盖
        print()
        print("⚠️ 已存在人工确认过的 plan，默认拒绝覆盖以保护人工编辑内容。")
        print(f"   - 文件：output/tomorrow_plan/tomorrow_plan_{report_date}.csv")
        if existing:
            print(f"   - manual_reviewed_at={existing.get('manual_reviewed_at', '')!r}")
            print(f"   - trade_permission={existing.get('trade_permission', '')!r}")
            ts = str(existing.get('tomorrow_strategy_desc', '')).strip()
            if ts:
                print(f"   - tomorrow_strategy_desc={ts[:60]!r}")
        print()
        print("如需操作，请加：")
        print("  --force                覆盖全部字段（包括人工文案）")
        print("  --merge-keep-manual    重新生成自动字段，但保留 8 个人工字段")
        print()
        # dry-run 时也要提示（用户原话）
        if args.dry_run:
            print("（dry-run：仍走 dry-run 流程，但真跑时会被拒绝）")
        else:
            print(f"exit {EXIT_MANUAL_CONFIRMED}")
            return EXIT_MANUAL_CONFIRMED

    # —— 生成新 plan ——
    record = build_tomorrow_plan(report_date)

    # —— merge-keep-manual 合并 ——
    if args.merge_keep_manual and existing is not None:
        record = _merge_keep_manual(record, existing)

    print(f"\n[plan] next_trade_date={record['next_trade_date']}")
    print(f"[plan] market_state={record['market_state']!r} "
          f"(confidence={record['market_state_confidence']!r}, "
          f"source={record['market_state_source']!r})")
    print(f"[plan] trade_permission={record['trade_permission']!r}")
    print(f"[plan] risk_level={record['risk_level']!r}")
    print(f"[plan] allowed_themes (Top 5): {record['allowed_themes']!r}")
    print(f"[plan] focus_stocks: {record['focus_stocks']!r}")
    print(f"[plan] manual_review_required={record['manual_review_required']!r}")
    print(f"[plan] manual_reviewed_at={record.get('manual_reviewed_at', '')!r}")
    print(f"[plan] source_files: {record['source_files']!r}")

    out_csv = PLAN_DIR / f"tomorrow_plan_{report_date}.csv"
    out_md  = PLAN_DIR / f"tomorrow_plan_{report_date}.md"

    if args.dry_run:
        print(f"\n── DRY-RUN：以下为 CSV 字段（未写文件）──")
        for k in CSV_FIELDS:
            v = record.get(k, "")
            if v:
                print(f"  {k:30s} = {v!r}")
        print(f"\n── DRY-RUN：以下为 MD 前 40 行预览 ──")
        md_text = render_md(record)
        for i, line in enumerate(md_text.splitlines()[:40], 1):
            print(f"  L{i:3d}: {line}")
        print(f"  ...（共 {len(md_text.splitlines())} 行）")
        print(f"\n  （未写入：{out_csv.name} / {out_md.name}）")
        return EXIT_OK

    # —— 真跑：写文件 ——
    if args.force and is_reviewed:
        print(f"\n⚠️ --force 模式：即将覆盖已人工确认的 plan（{review_detail}）")
    write_csv(record, out_csv)
    out_md.write_text(render_md(record), encoding="utf-8")
    print(f"\n✅ 已写入：{out_csv.relative_to(BASE_DIR)}")
    print(f"✅ 已写入：{out_md.relative_to(BASE_DIR)}")

    if not args.no_latest:
        latest_csv = PLAN_DIR / "tomorrow_plan_latest.csv"
        latest_md  = PLAN_DIR / "tomorrow_plan_latest.md"
        shutil.copy(out_csv, latest_csv)
        shutil.copy(out_md,  latest_md)
        print(f"✅ 已覆盖：{latest_csv.relative_to(BASE_DIR)}")
        print(f"✅ 已覆盖：{latest_md.relative_to(BASE_DIR)}")

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
