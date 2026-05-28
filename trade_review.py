"""
模拟复盘模块。
每次 run.py 运行后自动追加推荐记录到 output/trade_review.csv。
用户手动补录 open_price / price_0935 / buy_price / T+1 数据后，
运行 python run.py --review-summary 自动计算收益指标并输出统计。
"""
import logging
import math
from datetime import date as _date
from pathlib import Path
from typing import Optional

import pandas as pd

import cn_display

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
CSV_PATH = BASE_DIR / "output" / "trade_review.csv"

COLUMNS = [
    # 自动生成
    "report_date", "data_date", "rank",
    "mode",
    "theme_name", "theme_strength", "theme_bonus", "theme_auto_score", "theme_source_boards",
    "stock_code", "stock_name",
    "total_score", "popularity_score", "technical_score", "space_score", "risk_score",
    "market_sentiment",
    "recommended_close_price", "ma5", "ma10", "ma20",
    "yesterday_low", "yesterday_amount", "circulating_market_cap",
    # 手动必填
    "open_price", "price_0935", "buy_signal_0935", "buy_price",
    "t1_open", "t1_high", "t1_low", "t1_close",
    # 手动可选
    "open_change_pct", "intraday_avg_line_pass", "first_5min_amount_ratio",
    "sector_strength", "price_1000", "broke_yesterday_low",
    "unable_to_buy", "unable_to_buy_reason", "notes",
    # 10:00 二次确认观察（V1.4 实验性观察项，不计入正式收益）
    "second_check_time", "second_check_passed", "second_check_reason",
    "second_check_observe_price",
    # 自动计算
    "required_conditions_passed",
    "adjusted_buy_price", "stop_price", "stop_loss_triggered",
    "simulated_sell_price", "adjusted_sell_price",
    "t1_max_return", "t1_close_return", "max_drawdown", "simulated_trade_return",
    "is_active_success", "is_strong_surge", "is_close_success",
    "risk_adjusted_success", "ambiguous_path",
    "not_bought_tracking",
    # ── V1.5-beta 审计字段（仅记录；update_review/_calc_row 永不读 → 不影响 simulated_trade_return）──
    # 仅在 check_buy() 阶段被填写。observe_only 模式下永远不影响 buy_signal_0935。
    "v15_gate_mode",          # observe_only / mark_only / block_buy / disabled / fallback_to_v14
    "v15_money_decision",     # 资金通过 / 资金不通过 / 资金数据缺失 / 资金源不可用 / —
    "v15_money_source",       # push2his / ths_simple / unavailable
    "v15_money_reason",       # 中文原因（来自 money_flow.evaluate_money_flow_health 的 reason_cn）
    "v15_blocks_buy",         # True / False（仅 block_buy 模式且资金不通过时 True；其它恒 False）
    # ── V1.6 计划字段（候选资格层；update_review/_calc_row 永不读）──
    # 在 append_rows() 阶段被填写。计划缺失/日期不匹配时全部为 disabled/False。
    "v16_plan_enabled",            # True / False — plan 是否对该候选生效
    "v16_plan_date",               # 计划生成日（tomorrow_plan 的 report_date）
    "v16_market_state",            # 从 plan copy
    "v16_trade_permission",        # 从 plan copy
    "v16_allowed_theme_match",     # True / False — 该股 theme 是否在 allowed_themes
    "v16_focus_stock_match",       # True / False — 该股是否在 focus_stocks
    "v16_avoid_theme_match",       # True / False — 该股 theme 是否在 avoid_themes
    "v16_plan_action",             # 5 档中文动作描述
    "v16_plan_reason",             # 中文原因
    "v16_only_observe",            # True / False — check_buy 前置门读这个字段
]


# 二次确认观察的失败原因白名单 / 黑名单（V1.4 实验性观察项）
SECOND_CHECK_ELIGIBLE_REASONS: set = {
    "price_below_open",
    "price_below_ma5",
    "open_change_weak_watch",
}
SECOND_CHECK_INELIGIBLE_REASONS: set = {
    "market_sentiment_below_5",
    "theme_strength_too_low",
    "full_score_not_strong_enough",
    "open_change_too_low_hard",
    "open_change_too_high",
    "unable_to_buy_limit_up",
}


# ════════════════════════════════════════════════════════════════════
# V1.5-beta 配置加载（懒加载 + 安全默认值 + 守卫）
# ════════════════════════════════════════════════════════════════════
# 严格收窄：仅作用于 check_buy() 第六条资金规则。
# 不影响推荐池、scoring、theme_auto、update_review、T+1 收益、止损规则。

_V15_FLAGS_CACHE: Optional[dict] = None


def _load_v15_flags() -> dict:
    """
    读 config/version_flags.yaml 的 v15 部分；缺失/异常返回安全默认值（全关）。
    缓存到进程内变量，避免每次调用都读盘。
    """
    global _V15_FLAGS_CACHE
    if _V15_FLAGS_CACHE is not None:
        return _V15_FLAGS_CACHE

    # 安全默认值：等同 V1.4 行为
    default = {
        "enabled":                                False,
        "check_buy_mode":                         "observe_only",
        "fallback_to_v14_when_money_unavailable": True,
        "allow_block_buy":                        False,
    }

    try:
        import yaml
        fp = BASE_DIR / "config" / "version_flags.yaml"
        if not fp.exists():
            logger.debug("[v15] config/version_flags.yaml 不存在，使用安全默认（V1.4 行为）")
            _V15_FLAGS_CACHE = default
            return default
        d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        v15 = d.get("v15", {}) or {}
        out = {**default, **v15}

        # —— 守卫：第一阶段禁止 block_buy（即使配了也强制降级）——
        if out.get("check_buy_mode") == "block_buy" and not out.get("allow_block_buy", False):
            logger.warning(
                "[v15] check_buy_mode=block_buy 被守卫拒绝"
                "（allow_block_buy=false），自动降级为 mark_only"
            )
            out["check_buy_mode"] = "mark_only"

        # —— 守卫：未知 mode → 降级 observe_only ——
        if out.get("check_buy_mode") not in ("observe_only", "mark_only", "block_buy"):
            logger.warning(
                f"[v15] 未知 check_buy_mode={out.get('check_buy_mode')!r}，降级为 observe_only"
            )
            out["check_buy_mode"] = "observe_only"

        _V15_FLAGS_CACHE = out
        return out
    except Exception as e:
        logger.warning(f"[v15] 读取 version_flags.yaml 失败，回退安全默认: {type(e).__name__}: {e}")
        _V15_FLAGS_CACHE = default
        return default


def _reset_v15_flags_cache() -> None:
    """单元测试用：强制重新读盘。"""
    global _V15_FLAGS_CACHE
    _V15_FLAGS_CACHE = None


# ════════════════════════════════════════════════════════════════════
# V1.6 复盘计划驱动第二天选股
# ════════════════════════════════════════════════════════════════════
# 作用域：
#   - append_rows: 写候选股时打 V1.6 标签
#   - check_buy:   前置门读 v16_only_observe，True 时跳过 V1.4/V1.5 判定
#
# 容错原则（用户原话）：
#   - tomorrow_plan 缺失 / 日期不匹配 / next_trade_date 不等于 report_date
#     → 自动 fallback 到 V1.4/V1.5，不阻断推荐
#     → 所有 v16_* 字段填 disabled/False
#     → v16_plan_reason 写明 fallback 原因

_V16_FLAGS_CACHE: Optional[dict] = None


def _load_v16_flags() -> dict:
    """读 config/version_flags.yaml 的 v16 部分；缺失/异常返回安全默认值（全关）。"""
    global _V16_FLAGS_CACHE
    if _V16_FLAGS_CACHE is not None:
        return _V16_FLAGS_CACHE

    default = {
        "enabled":                          False,
        "plan_filter_enabled":              False,
        "plan_source":                      "latest",
        "fallback_to_v14_when_plan_missing": True,
        "affect_check_buy":                 False,
    }
    try:
        import yaml
        fp = BASE_DIR / "config" / "version_flags.yaml"
        if not fp.exists():
            _V16_FLAGS_CACHE = default
            return default
        d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        v16 = d.get("v16", {}) or {}
        out = {**default, **v16}
        _V16_FLAGS_CACHE = out
        return out
    except Exception as e:
        logger.warning(f"[v16] 读取 version_flags.yaml 失败，回退默认: {type(e).__name__}: {e}")
        _V16_FLAGS_CACHE = default
        return default


def _reset_v16_flags_cache() -> None:
    """单元测试用。"""
    global _V16_FLAGS_CACHE
    _V16_FLAGS_CACHE = None


def _load_v16_plan_for_report_date(report_date: str, flags: dict) -> Optional[dict]:
    """
    加载 tomorrow_plan，并校验它指导的日期等于 report_date。
    返回 plan dict（含派生 allowed_themes_set / avoid_themes_set / focus_codes_set）；
    任何缺失/不匹配返回 None（上层做 fallback）。
    """
    if not flags.get("enabled", False) or not flags.get("plan_filter_enabled", False):
        return None

    source = flags.get("plan_source", "latest")
    plan_dir = BASE_DIR / "output" / "tomorrow_plan"

    if source == "latest":
        fp = plan_dir / "tomorrow_plan_latest.csv"
    else:
        # by_date 模式：用 report_date 的"前一交易日"作为 plan_date
        # 第一阶段仅支持 latest，by_date 留接口
        fp = plan_dir / f"tomorrow_plan_{report_date}.csv"

    if not fp.exists():
        return None

    try:
        import csv as _csv
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(_csv.DictReader(f))
        if not rows:
            return None
        plan = rows[0]
    except Exception as e:
        logger.warning(f"[v16] 读 plan 文件异常: {type(e).__name__}: {e}")
        return None

    # 关键校验：plan 的 next_trade_date 必须等于 report_date
    # 即：今天 (report_date) 的推荐，要由昨天生成的计划指导
    plan_next_td = str(plan.get("next_trade_date", "")).strip()
    if plan_next_td != str(report_date):
        logger.warning(
            f"[v16] plan.next_trade_date={plan_next_td!r} != report_date={report_date!r}，"
            f"日期不匹配，本次推荐 V1.6 不生效"
        )
        return None

    # 派生集合（提速 + 集中）
    plan["_allowed_themes_set"] = set(
        t.strip() for t in str(plan.get("allowed_themes", "")).split("|") if t.strip()
    )
    plan["_avoid_themes_set"] = set(
        t.strip() for t in str(plan.get("avoid_themes", "")).split("|") if t.strip()
    )
    # focus_stocks 格式 "600143:金发科技|600580:卧龙电驱" → 提取代码 set
    focus_codes = set()
    for item in str(plan.get("focus_stocks", "")).split("|"):
        if not item.strip(): continue
        code = item.split(":")[0].strip()
        if code: focus_codes.add(code.zfill(6))
    plan["_focus_codes_set"] = focus_codes

    return plan


# 5 档 trade_permission → plan_action 推导规则（用户原话照搬）
def _derive_v16_plan_action(
    trade_permission: str,
    in_allowed_theme: bool,
    in_focus_stocks:  bool,
    in_avoid_theme:   bool,
) -> tuple:
    """
    返回 (plan_action, only_observe_bool, reason_cn)
    严格按用户原话 5 档规则。
    """
    is_priority = in_allowed_theme or in_focus_stocks

    if trade_permission == "禁止交易":
        return ("禁止交易日仅观察", True, "明日计划：禁止交易，所有候选仅观察不买入")

    if trade_permission == "只观察":
        return ("只观察", True, "明日计划：只观察，不参与正式买入")

    if trade_permission == "只做主线核心":
        if is_priority:
            return ("主线核心优先", False,
                    "明日计划：只做主线核心，该股属于 allowed_themes/focus_stocks")
        return ("非计划方向，只观察", True,
                "明日计划：只做主线核心，该股不在 allowed_themes/focus_stocks")

    if trade_permission == "小仓试错":
        if in_avoid_theme:
            return ("回避方向，只观察", True,
                    "明日计划：小仓试错 + 该股属于 avoid_themes")
        if is_priority:
            return ("优先观察", False,
                    "明日计划：小仓试错，该股属于 allowed_themes/focus_stocks，优先观察")
        return ("正常观察", False, "明日计划：小仓试错，该股属于一般候选")

    if trade_permission == "正常交易":
        if in_avoid_theme:
            return ("回避方向，只观察", True,
                    "明日计划：正常交易 + 该股属于 avoid_themes（回避）")
        if is_priority:
            return ("优先观察", False,
                    "明日计划：正常交易，该股属于 allowed_themes/focus_stocks，优先观察")
        return ("正常观察", False, "明日计划：正常交易，该股属于一般候选")

    # 未知 permission → 保守降级
    return ("只观察", True, f"明日计划：未识别 trade_permission={trade_permission!r}，保守只观察")


def _apply_v16_plan_to_candidate(
    stock_code: str,
    theme_name: str,
    plan: Optional[dict],
    flags: dict,
) -> dict:
    """
    给单只候选股生成 10 个 v16_* 字段。
    plan=None 时（缺失/日期不匹配）→ 全部 disabled，v16_plan_reason 写 fallback 原因。
    """
    out = {
        "v16_plan_enabled":         "false",
        "v16_plan_date":            "",
        "v16_market_state":         "",
        "v16_trade_permission":     "",
        "v16_allowed_theme_match":  "false",
        "v16_focus_stock_match":    "false",
        "v16_avoid_theme_match":    "false",
        "v16_plan_action":          "",
        "v16_plan_reason":          "",
        "v16_only_observe":         "false",
    }

    # —— Fallback：v16 关 / plan_filter 关 / plan 缺失 ——
    if not flags.get("enabled", False):
        out["v16_plan_reason"] = "V1.6 总开关关闭，按 V1.4/V1.5 运行"
        return out
    if not flags.get("plan_filter_enabled", False):
        out["v16_plan_reason"] = "V1.6 plan_filter 关闭，按 V1.4/V1.5 运行"
        return out
    if plan is None:
        if flags.get("fallback_to_v14_when_plan_missing", True):
            out["v16_plan_reason"] = "明日计划缺失或日期不匹配，已回退 V1.4/V1.5"
        else:
            # 第一阶段不允许 fallback=false（守卫）
            out["v16_plan_reason"] = "明日计划缺失（fallback_to_v14 已强制启用）"
        return out

    # —— plan 存在，开始打标 ——
    code = str(stock_code).zfill(6)
    theme = str(theme_name or "").strip()

    in_allowed = bool(theme) and theme in plan["_allowed_themes_set"]
    in_focus   = code in plan["_focus_codes_set"]
    in_avoid   = bool(theme) and any(theme in av or av in theme
                                      for av in plan["_avoid_themes_set"])

    trade_permission = str(plan.get("trade_permission", "")).strip() or "只观察"
    action, only_observe, reason = _derive_v16_plan_action(
        trade_permission, in_allowed, in_focus, in_avoid,
    )

    # 人工待确认提示（不改变 plan_action，但在 reason 后追加）
    if str(plan.get("manual_review_required", "")).strip().lower() == "true":
        reason = reason + "（⚠️ 明日计划待人工确认）"

    out.update({
        "v16_plan_enabled":         "true",
        "v16_plan_date":            str(plan.get("report_date", "")),
        "v16_market_state":         str(plan.get("market_state", "")),
        "v16_trade_permission":     trade_permission,
        "v16_allowed_theme_match":  "true" if in_allowed else "false",
        "v16_focus_stock_match":    "true" if in_focus   else "false",
        "v16_avoid_theme_match":    "true" if in_avoid   else "false",
        "v16_plan_action":          action,
        "v16_plan_reason":          reason,
        "v16_only_observe":         "true" if only_observe else "false",
    })
    return out


def _evaluate_v15_money_for_check_buy(code: str, flags: dict) -> dict:
    """
    V1.5 第六条资金规则的判定 — 仅在 check_buy() 内调用。
    返回字典含 5 个审计字段 + is_healthy(派生) + should_block(派生)。

    边界：
      - flags["enabled"]=False → 返回 mode="disabled"，不调 money_flow
      - 资金源全死 + fallback=True → mode="fallback_to_v14"，should_block=False
      - 任何异常 → mode 保持，decision="资金数据缺失"，should_block=False
    """
    out = {
        "v15_gate_mode":      "disabled",
        "v15_money_decision": "—",
        "v15_money_source":   "",
        "v15_money_reason":   "",
        "v15_blocks_buy":     False,
        "is_healthy":         None,    # 派生用，不写 CSV
        "should_block":       False,   # 派生用，不写 CSV
    }
    if not flags.get("enabled", False):
        return out

    mode = flags.get("check_buy_mode", "observe_only")
    out["v15_gate_mode"] = mode

    # —— 整批资金源全死，已在 check_buy 顶部预检设为 fallback_to_v14 ——
    # 此时跳过 money_flow 单股调用，直接返回（不影响 buy_signal_0935）
    if mode == "fallback_to_v14":
        out["v15_money_decision"] = "资金源不可用"
        out["v15_money_source"]   = "unavailable"
        out["v15_money_reason"]   = "资金源全死，本日回退 V1.4 五条规则"
        return out

    try:
        import money_flow
        mf = money_flow.evaluate_money_flow_health(
            code, days=3, use_cache=True, allow_fallback=True,
        )
    except Exception as e:
        logger.warning(f"[v15] {code} 资金判定异常: {type(e).__name__}: {e}")
        out["v15_money_decision"] = "资金数据缺失"
        out["v15_money_reason"]   = f"调用异常: {type(e).__name__}"
        return out

    data_source = str(mf.get("data_source", "") or "").lower()
    status      = str(mf.get("status",      "") or "").lower()
    is_healthy  = bool(mf.get("is_healthy", False))
    reason_cn   = str(mf.get("reason_cn",   "") or "")

    out["v15_money_source"] = data_source
    out["v15_money_reason"] = reason_cn
    out["is_healthy"]       = is_healthy

    if data_source == "unavailable" or status == "fetch_failed":
        out["v15_money_decision"] = "资金源不可用"
    elif status == "missing":
        out["v15_money_decision"] = "资金数据缺失"
    elif is_healthy:
        out["v15_money_decision"] = "资金通过"
    else:
        out["v15_money_decision"] = "资金不通过"

    # —— 仅在 block_buy 模式 + 资金不通过 + 数据可信时才"拦截买入" ——
    if mode == "block_buy" \
       and not is_healthy \
       and data_source != "unavailable" \
       and status != "fetch_failed":
        out["should_block"]   = True
        out["v15_blocks_buy"] = True

    return out


def _ensure_columns(df: pd.DataFrame, extra_cols: list = None) -> pd.DataFrame:
    """
    给老 CSV 平滑加上新列（保留旧数据）。
    任何新增列默认填空字符串，不影响已有字段。
    """
    cols = list(extra_cols) if extra_cols else list(COLUMNS)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df


# =================== 类型转换工具 ===================

def _gf(v) -> Optional[float]:
    """安全浮点转换；NaN/None/空字符串均返回 None。"""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _gb(v) -> Optional[bool]:
    """安全布尔转换；不可识别值返回 None（unknown，不等同于 False）。"""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def _pct(ratio: Optional[float]) -> str:
    return f"{ratio * 100:.1f}%" if ratio is not None else "N/A"


# =================== CSV 读写 ===================

def _read_csv() -> Optional[pd.DataFrame]:
    if not CSV_PATH.exists():
        return None
    return pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)


# =================== 自动计算字段 ===================

def _calc_row(row: pd.Series, slippage_rate: float, apply_sell_slippage: bool) -> pd.Series:
    """对单行计算所有自动字段，返回更新后的行。"""
    row = row.copy()

    ms        = _gf(row.get("market_sentiment"))
    ma5       = _gf(row.get("ma5"))
    rec_close = _gf(row.get("recommended_close_price"))
    open_p    = _gf(row.get("open_price"))
    p0935     = _gf(row.get("price_0935"))
    buy_p     = _gf(row.get("buy_price"))
    unable    = _gb(row.get("unable_to_buy"))

    # open_change_pct 自动计算（若用户未填）
    ocp = _gf(row.get("open_change_pct"))
    if ocp is None and open_p is not None and rec_close and rec_close != 0:
        ocp = round((open_p / rec_close - 1) * 100, 2)
        row["open_change_pct"] = str(ocp)

    # required_conditions_passed（所有必要字段就绪时才写入）
    if all(v is not None for v in [ms, ocp, p0935, open_p, ma5]):
        rcp = (
            ms >= 5
            and -1 <= ocp <= 4
            and p0935 >= open_p
            and p0935 >= ma5
            and unable is not True
        )
        row["required_conditions_passed"] = "true" if rcp else "false"

    # 交易字段：仅当 buy_signal_0935=True 且 buy_price 已填
    buy_sig = _gb(row.get("buy_signal_0935"))
    if buy_sig is not True or buy_p is None:
        return row

    # adjusted_buy_price / stop_price 不需要 T+1，立即计算
    adj_buy = buy_p * (1 + slippage_rate)
    stop    = adj_buy * 0.97
    row["adjusted_buy_price"] = str(round(adj_buy, 4))
    row["stop_price"]         = str(round(stop, 4))

    t1_open  = _gf(row.get("t1_open"))
    t1_high  = _gf(row.get("t1_high"))
    t1_low   = _gf(row.get("t1_low"))
    t1_close = _gf(row.get("t1_close"))

    if any(v is None for v in [t1_open, t1_high, t1_low, t1_close]):
        return row

    if t1_open <= stop:
        stop_triggered = True
        sim_sell = t1_open
    elif t1_low <= stop:
        stop_triggered = True
        sim_sell = stop
    else:
        stop_triggered = False
        sim_sell = t1_close

    row["stop_loss_triggered"]  = "true" if stop_triggered else "false"
    row["simulated_sell_price"] = str(round(sim_sell, 4))

    adj_sell = sim_sell * (1 - slippage_rate) if apply_sell_slippage else sim_sell
    row["adjusted_sell_price"] = str(round(adj_sell, 4))

    t1_max_ret   = t1_high / adj_buy - 1
    t1_close_ret = t1_close / adj_buy - 1
    max_dd       = t1_low / adj_buy - 1
    trade_ret    = adj_sell / adj_buy - 1

    def _bs(b: bool) -> str:
        return "true" if b else "false"

    row["t1_max_return"]          = str(round(t1_max_ret, 4))
    row["t1_close_return"]        = str(round(t1_close_ret, 4))
    row["max_drawdown"]           = str(round(max_dd, 4))
    row["simulated_trade_return"] = str(round(trade_ret, 4))
    row["is_active_success"]       = _bs(t1_max_ret >= 0.03)
    row["is_strong_surge"]         = _bs(t1_max_ret >= 0.05)
    row["is_close_success"]        = _bs(t1_close_ret > 0)
    row["risk_adjusted_success"]   = _bs(t1_max_ret >= 0.03 and max_dd > -0.03)
    row["ambiguous_path"]          = _bs(t1_high >= adj_buy * 1.03 and t1_low <= stop)

    return row


# =================== 追加记录 ===================

def append_rows(
    top3: list,
    market_data: dict,
    data_date: str,
    report_date: str,
    cfg: dict,
    mode: str = "full",
) -> None:
    """将今日 top3 追加到 trade_review.csv（幂等：同一天已存在则跳过）。"""
    df = _read_csv()
    if df is None:
        df = pd.DataFrame(columns=COLUMNS)
    df = _ensure_columns(df)

    def _sr(v, digits=3):
        f = _gf(v)
        return str(round(f, digits)) if f is not None else ""

    # ── V1.6 计划加载（一次性，整批候选共用）──
    # 计划缺失/日期不匹配 → plan=None → _apply_v16_plan_to_candidate 会自动 fallback
    _v16_flags = _load_v16_flags()
    _v16_plan  = _load_v16_plan_for_report_date(report_date, _v16_flags)
    if _v16_flags.get("enabled") and _v16_flags.get("plan_filter_enabled"):
        if _v16_plan is None:
            logger.warning(
                f"[v16] 明日计划缺失或日期不匹配（report_date={report_date}），"
                f"本批 {mode} 推荐按 V1.4/V1.5 运行"
            )
        else:
            logger.info(
                f"[v16] 加载明日计划：plan_date={_v16_plan.get('report_date')} "
                f"trade_permission={_v16_plan.get('trade_permission')!r} "
                f"allowed_themes={len(_v16_plan['_allowed_themes_set'])} "
                f"focus_stocks={len(_v16_plan['_focus_codes_set'])}"
            )

    new_rows = []
    for rank_idx, item in enumerate(top3, 1):
        code = item["code"]
        _mode_col = (
            df["mode"].astype(str)
            if "mode" in df.columns
            else pd.Series(["full"] * len(df), index=df.index)
        )
        dup = df[
            (df["report_date"].astype(str) == str(report_date)) &
            (df["stock_code"].astype(str) == str(code).zfill(6)) &
            (_mode_col == mode)
        ]
        if len(dup) > 0:
            continue

        scores = item["scores"]
        ind    = item["ind"]

        row = {col: "" for col in COLUMNS}
        row.update({
            "report_date":        report_date,
            "data_date":          data_date,
            "rank":               str(rank_idx),
            "mode":               mode,
            "theme_name":         item.get("theme_name",   ""),
            "theme_strength":     str(item.get("theme_strength", "")) if mode == "theme_auto" else "",
            "theme_bonus":        str(item.get("theme_bonus",    "")) if mode == "theme_auto" else "",
            "theme_auto_score":   str(item.get("theme_auto_score", "")) if mode == "theme_auto" else "",
            "theme_source_boards": ",".join(item.get("theme_source_boards", [])) if mode == "theme_auto" else "",
            "stock_code":         str(code).zfill(6),
            "stock_name":              item["name"],
            "total_score":             str(scores["total"]),
            "popularity_score":        str(scores["popularity"]),
            "technical_score":         str(scores["technical"]),
            "space_score":             str(scores["space"]),
            "risk_score":              str(scores["risk"]),
            "market_sentiment":        str(market_data["score"]),
            "recommended_close_price": _sr(ind.get("close"), 3),
            "ma5":                     _sr(ind.get("ma5"), 3),
            "ma10":                    _sr(ind.get("ma10"), 3),
            "ma20":                    _sr(ind.get("ma20"), 3),
            "yesterday_low":           _sr(ind.get("low_today"), 3),
            "yesterday_amount":        str(round(float(ind.get("amount", 0)))),
            "circulating_market_cap":  "",
        })

        # ── 🆕 V1.6 打标：每只候选股按明日计划打 10 个标签 ──
        # plan=None 时 helper 自动 fallback；不会抛异常
        v16_audit = _apply_v16_plan_to_candidate(
            stock_code=str(code).zfill(6),
            theme_name=str(item.get("theme_name", "") or ""),
            plan=_v16_plan,
            flags=_v16_flags,
        )
        row.update(v16_audit)

        new_rows.append(row)

    if new_rows:
        df = pd.concat(
            [df, pd.DataFrame(new_rows, columns=COLUMNS)],
            ignore_index=True,
        )
        df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        cn_display.generate_cn_csv()
        logger.info(f"trade_review.csv 追加 {len(new_rows)} 行（{report_date}）")
    else:
        logger.info(f"trade_review.csv 已有 {report_date} 数据，跳过追加")


# =================== 9:35 模拟买入检查 ===================

def _v14_active(report_date: str, cfg: dict) -> bool:
    """V1.4 是否在 report_date 当天启用。早于切换日期沿用 V1.3。"""
    eff = str(cfg.get("buy_rules", {}).get("version_effective_from", "")).strip()
    if not eff or not eff.isdigit() or len(eff) != 8:
        return False
    try:
        return str(report_date) >= eff
    except Exception:
        return False


def _v14_pregate_main_reason(row: pd.Series, mode: str, cfg: dict) -> Optional[str]:
    """
    V1.4「有效推荐」预闸：返回主因代码或 None（通过）。
    theme_auto: theme_strength 必须达标
    full:       total_score / popularity_score / technical_score 同时达标
    """
    v14 = cfg.get("buy_rules", {}).get("v1_4", {})
    if mode == "theme_auto":
        ts_min = float(v14.get("theme_strength_min", 50))
        ts     = _gf(row.get("theme_strength"))
        if ts is None or ts < ts_min:
            return "theme_strength_too_low"
        return None
    # full
    tot_min = float(v14.get("full_total_score_min", 78))
    pop_min = float(v14.get("full_popularity_min",  22))
    tec_min = float(v14.get("full_technical_min",   20))
    tot = _gf(row.get("total_score"))
    pop = _gf(row.get("popularity_score"))
    tec = _gf(row.get("technical_score"))
    if (tot is None or tot < tot_min) or \
       (pop is None or pop < pop_min) or \
       (tec is None or tec < tec_min):
        return "full_score_not_strong_enough"
    return None


def _classify_open_change_v14(open_chg: float, cfg: dict) -> tuple:
    """
    V1.4 开盘涨幅分级，返回 (hard_reason|None, soft_reason|None)。
    < hard_low      → hard: open_change_too_low_hard
    [hard_low, soft_low) → soft: open_change_weak_watch
    > hard_high     → hard: open_change_too_high
    else            → (None, None)
    """
    v14 = cfg.get("buy_rules", {}).get("v1_4", {})
    hl = float(v14.get("open_change_hard_low",  -3.0))
    sl = float(v14.get("open_change_soft_low",  -1.0))
    hh = float(v14.get("open_change_hard_high",  4.0))
    if open_chg < hl:
        return ("open_change_too_low_hard", None)
    if open_chg > hh:
        return ("open_change_too_high", None)
    if open_chg < sl:
        return (None, "open_change_weak_watch")
    return (None, None)


def _build_buy_reasons_v14(
    row: pd.Series, mode: str, theme_name: str, theme_strength: Optional[float],
    open_chg: float, cur_price: float, open_p: float, ma5: Optional[float],
    unable_to_buy: bool,
) -> dict:
    """
    构造买入四因（逻辑 / 资金 / 买点 / 风险）的中文文案。
    仅在 buy_signal=True 时调用。
    """
    tot = _gf(row.get("total_score"))
    pop = _gf(row.get("popularity_score"))
    amt = _gf(row.get("yesterday_amount"))
    amt_yi = (amt / 1e8) if amt else None    # 亿

    # 逻辑
    if mode == "theme_auto":
        ts_txt = f"{theme_strength:.0f}/100" if theme_strength is not None else "—"
        logic_txt = f"属于强主题「{theme_name or '—'}」，主题强度 {ts_txt}（≥50）"
    else:
        tot_txt = f"{tot:.1f}" if tot is not None else "—"
        logic_txt = f"全A高分强势票，系统总分 {tot_txt}（≥78）"

    # 资金
    pop_txt = f"{pop:.1f}" if pop is not None else "—"
    amt_txt = f"{amt_yi:.1f}亿" if amt_yi is not None else "—"
    funds_txt = f"人气分 {pop_txt}（≥22）｜昨日成交额 {amt_txt}"

    # 买点
    ma5_txt = f"{ma5:.2f}" if ma5 is not None else "—"
    entry_txt = (
        f"9:36价 {cur_price:.2f} ≥ 开盘价 {open_p:.2f}，"
        f"且 ≥ 5日均线 {ma5_txt}"
    )

    # 风险
    risk_txt = (
        f"开盘涨幅 {open_chg:+.2f}% 在 [-3%, +4%] 内，"
        f"{'非' if not unable_to_buy else ''}一字涨停可成交"
    )

    return {
        "logic": logic_txt,
        "funds": funds_txt,
        "entry": entry_txt,
        "risk":  risk_txt,
    }


def check_buy(cfg: dict) -> list:
    """
    读取当天 report_date 的推荐票，获取实时行情，判断9:35模拟买入条件。
    只更新空字段，不覆盖用户手动填写的数据。
    返回结果列表（供 notifier 格式化推送）。

    V1.4（report_date >= buy_rules.version_effective_from 生效）：
      - 「有效推荐」预闸：theme_auto 需 theme_strength≥50；full 需总分≥78 且 人气≥22 且 技术≥20
      - 开盘涨幅 < -3% 直接否决（open_change_too_low_hard，主因）
      - 开盘涨幅 [-3%, -1%) 视为「低开观察」（open_change_weak_watch，辅助原因，不否决）
      - 其余 9:36 条件保持原样
      - 买入时输出「逻辑 / 资金 / 买点 / 风险」四因
    """
    from data_fetcher import fetch_realtime_spot, calc_dates

    _, report_date = calc_dates()
    v14_on = _v14_active(report_date, cfg)
    logger.info(
        f"[check_buy] report_date={report_date}  "
        f"buy_rules_version={'V1.4' if v14_on else 'V1.3'}  "
        f"(effective_from={cfg.get('buy_rules', {}).get('version_effective_from', '')})"
    )

    df = _read_csv()
    if df is None or len(df) == 0:
        logger.warning("[check_buy] trade_review.csv 为空，无可处理记录")
        return []
    df = _ensure_columns(df)

    today_mask = df["report_date"].astype(str) == str(report_date)
    if not today_mask.any():
        logger.warning(f"[check_buy] 未找到 {report_date} 的记录，请先运行 python run.py")
        return []

    codes = [str(c).zfill(6) for c in df.loc[today_mask, "stock_code"].tolist()]
    rt_df = fetch_realtime_spot(codes)
    rt_map = {str(r["code"]).zfill(6): r for _, r in rt_df.iterrows()}

    def _empty(val) -> bool:
        return str(val).strip() == ""

    updated = 0
    results = []

    # ── V1.5-beta 资金条件预处理（仅 check_buy 内部使用，绝不影响推荐池）──
    # 1) 加载配置（缺文件/异常 → 安全默认，等同 V1.4 行为）
    # 2) 资金源整批健康预检：若主+备源都死 + fallback=true → 整批走 fallback_to_v14
    # 3) 这个 v15_flags 字典传给每只票的判定
    v15_flags = _load_v15_flags()
    if v15_flags.get("enabled", False):
        try:
            import money_flow as _mf_mod
            sys_health = _mf_mod.check_money_flow_system_health()
            if sys_health.get("active_source") == "unavailable" \
               and v15_flags.get("fallback_to_v14_when_money_unavailable", True):
                logger.warning(
                    "[v15] 资金源全死（push2his + ths_simple 均不可用），"
                    "本日 check_buy 回退 V1.4 五条规则（fallback_to_v14_when_money_unavailable=true）"
                )
                # 用浅拷贝 + 覆盖 mode 字段，传给每只票的判定
                v15_flags = {**v15_flags, "check_buy_mode": "fallback_to_v14", "_fallback_active": True}
        except Exception as e:
            logger.warning(f"[v15] 资金源健康预检失败，按现有 mode 走: {type(e).__name__}: {e}")
    logger.info(
        f"[v15] check_buy 模式: enabled={v15_flags.get('enabled')} "
        f"mode={v15_flags.get('check_buy_mode')}"
    )

    # ── V1.6 前置门加载（候选资格层；不修改 V1.4 公式本身）──
    # 仅当 v16.enabled + plan_filter_enabled + affect_check_buy 全为 true 时拦截
    _v16_check_buy_flags = _load_v16_flags()
    _v16_affect_check_buy = (
        _v16_check_buy_flags.get("enabled", False)
        and _v16_check_buy_flags.get("plan_filter_enabled", False)
        and _v16_check_buy_flags.get("affect_check_buy", False)
    )
    if _v16_affect_check_buy:
        logger.info(
            f"[v16] check_buy 前置门已启用："
            f"v16_only_observe=True 的候选将跳过 V1.4 五条 + V1.5 第六条"
        )

    for idx in df.index[today_mask]:
        row  = df.loc[idx]
        code = str(row["stock_code"]).zfill(6)
        name = str(row["stock_name"])
        mode = str(row.get("mode", "full")).strip() or "full"

        # ── 🆕 V1.6 前置门：候选资格层（用户原话：不是修改买入条件公式）──
        # 仅在 affect_check_buy=true 时生效。v16_only_observe=True 的候选股：
        #   - buy_signal_0935=False
        #   - notes 追加 "v16_plan_only_observe"
        #   - 跳过 V1.4 五条 + V1.5 第六条判定
        if _v16_affect_check_buy and _gb(row.get("v16_only_observe")) is True:
            v16_reason = str(row.get("v16_plan_reason", "")).strip() or "v16_plan_only_observe"
            v16_action = str(row.get("v16_plan_action", "")).strip() or "只观察"
            logger.info(
                f"[v16][check_buy] {code} {name} 计划标记仅观察 → 跳过 V1.4/V1.5 判定"
                f" (action={v16_action})"
            )
            # 强制覆盖买入字段
            df.at[idx, "buy_signal_0935"]    = "false"
            df.at[idx, "buy_price"]          = ""
            df.at[idx, "adjusted_buy_price"] = ""
            df.at[idx, "stop_price"]         = ""
            # notes 追加（保留既有内容）
            notes_existing = str(row.get("notes", "")).strip()
            v16_note = "v16_plan_only_observe"
            if v16_note not in notes_existing:
                df.at[idx, "notes"] = (notes_existing + ";" + v16_note) if notes_existing else v16_note
            updated += 1
            results.append({
                "code":              code,
                "name":              name,
                "rank":              str(row.get("rank", "?")),
                "mode":               mode,
                "theme_name":        str(row.get("theme_name", "")).strip(),
                "theme_strength":    _gf(row.get("theme_strength")),
                "market_sentiment":  _gf(row.get("market_sentiment")),
                "ma5":               _gf(row.get("ma5")),
                "open_price":        None,
                "unable_to_buy":     False,
                "open_chg":          None,
                "price_0935":        None,
                "buy_signal":        False,
                "fail_reasons":      [v16_note],
                "hard_fail_reasons": [v16_note],
                "soft_fail_reasons": [],
                "buy_reasons":       None,
                "buy_price":         None,
                "unable_reason":     "",
                "effective_version": "V1.6+V1.4",
                "v16_only_observe":  True,
                "v16_plan_action":   v16_action,
                "v16_plan_reason":   v16_reason,
                "pregate_failed":    False,
            })
            continue

        # ── V1.4「有效推荐」预闸 ─────────────────────────────────────
        # 不满足预闸的票直接观察，不抓实时行情、不写入买点/止损
        pregate_reason: Optional[str] = None
        if v14_on:
            pregate_reason = _v14_pregate_main_reason(row, mode, cfg)
        if pregate_reason:
            logger.info(
                f"[check_buy] {code} {name} V1.4 预闸未通过: {pregate_reason}"
            )
            # 强制覆盖买入字段，避免遗留脏数据
            df.at[idx, "buy_signal_0935"]    = "false"
            df.at[idx, "buy_price"]          = ""
            df.at[idx, "adjusted_buy_price"] = ""
            df.at[idx, "stop_price"]         = ""
            # 不写 open_price / price_0935（无意义，且未拉行情）
            note_val = pregate_reason
            if _empty(row.get("notes", "")):
                df.at[idx, "notes"] = note_val
            updated += 1
            results.append({
                "code":              code,
                "name":              name,
                "rank":              str(row.get("rank", "?")),
                "mode":              mode,
                "theme_name":        str(row.get("theme_name", "")).strip(),
                "theme_strength":    _gf(row.get("theme_strength")),
                "market_sentiment":  _gf(row.get("market_sentiment")),
                "ma5":               _gf(row.get("ma5")),
                "open_price":        None,
                "unable_to_buy":     False,
                "open_chg":          None,
                "price_0935":        None,
                "buy_signal":        False,
                "fail_reasons":      [pregate_reason],          # 仅含主因
                "hard_fail_reasons": [pregate_reason],
                "soft_fail_reasons": [],
                "buy_reasons":       None,
                "buy_price":         None,
                "unable_reason":     "",
                "effective_version": "V1.4",
                "pregate_failed":    True,
            })
            continue

        rt = rt_map.get(code)
        if rt is None:
            logger.warning(f"[check_buy] {code} 实时行情缺失")
            results.append({"code": code, "name": name, "error": True,
                            "reason": "实时行情获取失败",
                            "effective_version": "V1.4" if v14_on else "V1.3"})
            continue

        open_p     = float(rt["open"])
        prev_close = float(rt["prev_close"])
        cur_price  = float(rt["close"])
        vol_lots   = float(rt.get("volume", 0))

        if prev_close <= 0 or open_p <= 0 or cur_price <= 0:
            logger.warning(f"[check_buy] {code} 价格数据无效（停牌或尚未开盘）")
            results.append({"code": code, "name": name, "error": True,
                            "reason": "价格数据无效，可能停牌或未开盘",
                            "effective_version": "V1.4" if v14_on else "V1.3"})
            continue

        open_chg = (open_p / prev_close - 1) * 100

        # 一字涨停板检测
        limit_r      = 0.20 if code.startswith(("300", "301", "688")) else 0.10
        at_limit_open = open_chg >= limit_r * 100 - 0.5
        price_frozen  = abs(cur_price - open_p) < 0.01

        unable_to_buy = False
        unable_reason = ""
        if at_limit_open and price_frozen:
            if vol_lots < 1000:
                unable_to_buy = True
                unable_reason = "limit_up_one_char"
            else:
                unable_reason = "possible_limit_up_unable_to_buy"

        ms  = _gf(row.get("market_sentiment"))
        ma5 = _gf(row.get("ma5"))

        # ── 买入条件 ────────────────────────────────────────────────
        hard_fail: list = []
        soft_fail: list = []

        # 大盘情绪（共有，主因）
        if ms is not None and ms < 5:
            hard_fail.append("market_sentiment_below_5")

        # 开盘涨幅
        if v14_on:
            hr, sr = _classify_open_change_v14(open_chg, cfg)
            if hr:
                hard_fail.append(hr)
            if sr:
                soft_fail.append(sr)
        else:
            # V1.3：保留旧行为
            if open_chg < -1:
                hard_fail.append("open_change_too_low")
            if open_chg > 4:
                hard_fail.append("open_change_too_high")

        # 9:36 价格关
        if cur_price < open_p:
            hard_fail.append("price_below_open")
        if ma5 is not None and cur_price < ma5:
            hard_fail.append("price_below_ma5")
        if unable_to_buy:
            hard_fail.append("unable_to_buy_limit_up")

        # ── 🆕 V1.5-beta 第六条规则：资金条件 ─────────────────────────
        # 仅在 mode=block_buy 且资金不通过且数据可信时才往 hard_fail 加。
        # observe_only / mark_only 模式：只记录 v15_* 审计字段，绝不影响 buy_signal_0935。
        # 资金源全死 + fallback_to_v14=True：mode=fallback_to_v14，v15 完全跳过。
        v15_audit = _evaluate_v15_money_for_check_buy(code, v15_flags)
        if v15_audit.get("should_block"):
            hard_fail.append("money_flow_not_healthy")

        fail_reasons = hard_fail + soft_fail   # 旧字段：保留全部
        buy_signal   = len(hard_fail) == 0     # 软警告不否决

        # ── 写回 CSV（只写空字段，强制字段强制覆盖）────────────────
        changed = False
        def _set(field, value):
            nonlocal changed
            if _empty(row.get(field, "")):
                df.at[idx, field] = value
                changed = True

        _set("open_price",      str(round(open_p,    3)))
        _set("open_change_pct", str(round(open_chg,  2)))
        _set("price_0935",      str(round(cur_price, 3)))
        df.at[idx, "buy_signal_0935"] = "true" if buy_signal else "false"
        df.at[idx, "buy_price"]       = str(round(cur_price, 3)) if buy_signal else ""

        slip = cfg.get("review", {}).get("slippage_rate", 0.001)
        if buy_signal:
            adj = round(cur_price * (1 + slip), 4)
            df.at[idx, "adjusted_buy_price"] = str(adj)
            df.at[idx, "stop_price"]         = str(round(adj * 0.97, 4))
        else:
            df.at[idx, "adjusted_buy_price"] = ""
            df.at[idx, "stop_price"]         = ""
        changed = True
        _set("unable_to_buy", "true" if unable_to_buy else "false")
        if unable_reason:
            _set("unable_to_buy_reason", unable_reason)

        # notes：主因 + 辅助 + possible_limit_up（用 ";" 分隔，cn_display 翻译）
        note_parts = list(fail_reasons)
        if (not note_parts and unable_reason == "possible_limit_up_unable_to_buy"):
            note_parts.append(unable_reason)
        if note_parts:
            _set("notes", ";".join(note_parts))

        # ── 🆕 V1.5-beta 审计字段写回（强制覆盖；这 5 列 update_review 永不读）──
        df.at[idx, "v15_gate_mode"]      = str(v15_audit["v15_gate_mode"])
        df.at[idx, "v15_money_decision"] = str(v15_audit["v15_money_decision"])
        df.at[idx, "v15_money_source"]   = str(v15_audit["v15_money_source"])
        df.at[idx, "v15_money_reason"]   = str(v15_audit["v15_money_reason"])
        df.at[idx, "v15_blocks_buy"]     = "true" if v15_audit["v15_blocks_buy"] else "false"
        changed = True

        if changed:
            updated += 1

        # ── 构造结果（含 V1.4 四因）─────────────────────────────────
        buy_reasons = None
        if buy_signal and v14_on:
            buy_reasons = _build_buy_reasons_v14(
                row, mode,
                theme_name     = str(row.get("theme_name", "")).strip(),
                theme_strength = _gf(row.get("theme_strength")),
                open_chg       = open_chg,
                cur_price      = cur_price,
                open_p         = open_p,
                ma5            = ma5,
                unable_to_buy  = unable_to_buy,
            )

        results.append({
            "code":              code,
            "name":              name,
            "rank":              str(row.get("rank", "?")),
            "mode":              mode,
            "theme_name":        str(row.get("theme_name", "")).strip(),
            "theme_strength":    _gf(row.get("theme_strength")),
            "market_sentiment":  ms,
            "ma5":               ma5,
            "open_price":        round(open_p, 3),
            "unable_to_buy":     unable_to_buy,
            "open_chg":          round(open_chg,  2),
            "price_0935":        round(cur_price, 3),
            "buy_signal":        buy_signal,
            "fail_reasons":      fail_reasons,
            "hard_fail_reasons": hard_fail,
            "soft_fail_reasons": soft_fail,
            "buy_reasons":       buy_reasons,
            "buy_price":         round(cur_price, 3) if buy_signal else None,
            "unable_reason":     unable_reason,
            "effective_version": "V1.4" if v14_on else "V1.3",
            "pregate_failed":    False,
        })

    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    cn_display.generate_cn_csv()
    logger.info(
        f"[check_buy] 更新 {updated} 条记录（report_date={report_date}, "
        f"version={'V1.4' if v14_on else 'V1.3'}）"
    )
    return results


# =================== 10:00 二次确认观察（实验性，仅观察不买入） ===================

def second_check(cfg: dict) -> list:
    """
    10:00 二次确认观察：
      - 仅处理当天已完成9:36检查（price_0935 有值）且 buy_signal_0935=false 的票
      - 只处理失败原因属于「可观察白名单」（price_below_open / price_below_ma5 /
        open_change_weak_watch）且未含任何「不可观察」失败原因的样本
      - 通过条件：10:00价 ≥ 开盘价 且 ≥ 5日线 且 > 9:36价 且 非一字涨停
      - 仅写入 second_check_* 字段（含 price_1000），**不动** buy_signal_0935 / buy_price /
        adjusted_buy_price / stop_price，不参与正式收益与止损
    用于月底对照：9:36没买但10:00重新走强的票，后续表现如何。
    """
    from data_fetcher import fetch_realtime_spot, calc_dates
    from datetime import datetime as _dt

    _, report_date = calc_dates()
    logger.info(f"[second_check] report_date={report_date}（二次确认观察，仅记录不买入）")

    df = _read_csv()
    if df is None or len(df) == 0:
        logger.warning("[second_check] trade_review.csv 为空，无可处理记录")
        return []

    df = _ensure_columns(df)

    today_mask = df["report_date"].astype(str) == str(report_date)
    if not today_mask.any():
        logger.warning(f"[second_check] 未找到 {report_date} 的记录")
        return []

    def _empty(v) -> bool:
        return str(v).strip() == ""

    def _parse_reasons(notes_val) -> list:
        s = str(notes_val).strip()
        if not s:
            return []
        return [p.strip() for p in s.split(";") if p.strip()]

    def _is_observable(reasons: list) -> bool:
        # 必须至少有一条白名单原因；不允许出现任何黑名单原因
        if not reasons:
            return False
        if any(r in SECOND_CHECK_INELIGIBLE_REASONS for r in reasons):
            return False
        return any(r in SECOND_CHECK_ELIGIBLE_REASONS for r in reasons)

    # ── 选出候选 ──
    candidate_indices: list = []
    skipped_summary = {
        "already_bought":      0,
        "no_0935_check":       0,
        "already_observed":    0,
        "reason_not_eligible": 0,
    }

    for idx in df.index[today_mask]:
        row = df.loc[idx]

        # 9:36 已买入：不需要二次观察
        if str(row.get("buy_signal_0935", "")).strip().lower() == "true":
            skipped_summary["already_bought"] += 1
            continue
        # 9:36 检查还没跑：跳过
        if _empty(row.get("price_0935", "")):
            skipped_summary["no_0935_check"] += 1
            continue
        # 今天已经做过二次观察：幂等
        if not _empty(row.get("second_check_time", "")):
            skipped_summary["already_observed"] += 1
            continue
        # 失败原因白/黑名单
        reasons = _parse_reasons(row.get("notes", ""))
        if not _is_observable(reasons):
            skipped_summary["reason_not_eligible"] += 1
            continue

        candidate_indices.append(idx)

    logger.info(
        f"[second_check] 跳过统计: 已买入 {skipped_summary['already_bought']} / "
        f"9:36未跑 {skipped_summary['no_0935_check']} / "
        f"已观察 {skipped_summary['already_observed']} / "
        f"原因不在白名单 {skipped_summary['reason_not_eligible']}"
    )

    if not candidate_indices:
        logger.info("[second_check] 今日无可观察样本")
        return []

    codes = [str(df.at[idx, "stock_code"]).zfill(6) for idx in candidate_indices]
    logger.info(f"[second_check] 候选观察样本 {len(codes)} 只: {codes}")

    rt_df  = fetch_realtime_spot(codes)
    rt_map = {str(r["code"]).zfill(6): r for _, r in rt_df.iterrows()}

    now_str = _dt.now().strftime("%H:%M:%S")
    results = []
    updated = 0

    # 10:00 二次观察失败原因码（与正式 notes 完全独立的命名空间）
    REASON_PASSED         = "passed"
    REASON_BELOW_OPEN     = "second_check_below_open"
    REASON_BELOW_MA5      = "second_check_below_ma5"
    REASON_NOT_ABOVE_0935 = "second_check_not_above_0935"
    REASON_LIMIT_UP       = "second_check_unable_limit_up"
    REASON_RT_MISSING     = "realtime_data_missing"
    REASON_RT_INVALID     = "realtime_price_invalid"

    for idx in candidate_indices:
        row  = df.loc[idx]
        code = str(row["stock_code"]).zfill(6)
        name = str(row["stock_name"])
        mode = str(row.get("mode", "full")).strip() or "full"

        rt = rt_map.get(code)
        if rt is None:
            logger.warning(f"[second_check] {code} 实时行情缺失")
            df.at[idx, "second_check_time"]   = now_str
            df.at[idx, "second_check_passed"] = "false"
            df.at[idx, "second_check_reason"] = REASON_RT_MISSING
            updated += 1
            results.append({
                "code": code, "name": name, "mode": mode,
                "theme_name": str(row.get("theme_name", "")).strip(),
                "error": True, "reason": REASON_RT_MISSING,
                "original_fail_reasons": _parse_reasons(row.get("notes", "")),
            })
            continue

        cur_price  = float(rt["close"])
        open_p_rt  = float(rt["open"])
        prev_close = float(rt["prev_close"])
        vol_lots   = float(rt.get("volume", 0))

        if cur_price <= 0 or open_p_rt <= 0 or prev_close <= 0:
            logger.warning(f"[second_check] {code} 价格无效（停牌或未开盘）")
            df.at[idx, "second_check_time"]   = now_str
            df.at[idx, "second_check_passed"] = "false"
            df.at[idx, "second_check_reason"] = REASON_RT_INVALID
            df.at[idx, "price_1000"]          = str(round(cur_price, 3))
            updated += 1
            results.append({
                "code": code, "name": name, "mode": mode,
                "theme_name": str(row.get("theme_name", "")).strip(),
                "error": True, "reason": REASON_RT_INVALID,
                "original_fail_reasons": _parse_reasons(row.get("notes", "")),
            })
            continue

        # 使用 trade_review.csv 里已存的 open_price / price_0935 / ma5（与 9:36 同源，避免漂移）
        open_p     = _gf(row.get("open_price"))      or open_p_rt
        price_0935 = _gf(row.get("price_0935"))
        ma5        = _gf(row.get("ma5"))

        # 一字涨停（用实时数据再判一次，盘中已成交也算可买）
        limit_r       = 0.20 if code.startswith(("300", "301", "688")) else 0.10
        open_chg_rt   = (open_p_rt / prev_close - 1) * 100
        at_limit_open = open_chg_rt >= limit_r * 100 - 0.5
        price_frozen  = abs(cur_price - open_p_rt) < 0.01
        unable_to_buy = at_limit_open and price_frozen and vol_lots < 1000

        # ── 二次确认通过条件 ──
        fail_codes: list = []
        if cur_price < open_p:
            fail_codes.append(REASON_BELOW_OPEN)
        if ma5 is not None and cur_price < ma5:
            fail_codes.append(REASON_BELOW_MA5)
        if price_0935 is not None and cur_price <= price_0935:
            fail_codes.append(REASON_NOT_ABOVE_0935)
        if unable_to_buy:
            fail_codes.append(REASON_LIMIT_UP)

        passed = len(fail_codes) == 0
        reason_field = REASON_PASSED if passed else ";".join(fail_codes)

        # ── 写入 CSV（仅二次观察字段；不动 buy_signal_0935 / buy_price / stop_price）──
        df.at[idx, "second_check_time"]          = now_str
        df.at[idx, "price_1000"]                 = str(round(cur_price, 3))
        df.at[idx, "second_check_passed"]        = "true" if passed else "false"
        df.at[idx, "second_check_reason"]        = reason_field
        df.at[idx, "second_check_observe_price"] = str(round(cur_price, 3)) if passed else ""
        updated += 1

        results.append({
            "code":                  code,
            "name":                  name,
            "rank":                  str(row.get("rank", "?")),
            "mode":                  mode,
            "theme_name":            str(row.get("theme_name", "")).strip(),
            "open_price":            round(open_p, 3),
            "price_0935":            round(price_0935, 3) if price_0935 is not None else None,
            "ma5":                   round(ma5, 3) if ma5 is not None else None,
            "price_1000":            round(cur_price, 3),
            "second_check_passed":   passed,
            "second_check_reason":   reason_field,
            "fail_reasons":          fail_codes,
            "original_fail_reasons": _parse_reasons(row.get("notes", "")),
            "observe_price":         round(cur_price, 3) if passed else None,
        })

    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    cn_display.generate_cn_csv()
    n_pass = sum(1 for r in results if r.get("second_check_passed"))
    logger.info(
        f"[second_check] 观察 {len(results)} 只，通过 {n_pass} 只，"
        f"未通过 {len(results) - n_pass} 只（仅记录，不计入正式收益）"
    )
    return results


# =================== T+1 自动补全 ===================

def update_review(cfg: dict) -> dict:
    """
    补全已触发模拟买入记录的 T+1 结果。
    处理条件：buy_signal_0935=true，buy_price 有值，t1_open 为空。
    只在 T+1 收盘后（当天15:00后，或 T+1 已过）才处理。
    """
    from data_fetcher import fetch_stock_history, next_trading_date
    from datetime import datetime as _dt

    df = _read_csv()
    if df is None or len(df) == 0:
        logger.info("[update_review] trade_review.csv 为空，无需更新")
        return {"updated": 0, "skipped": 0, "failed": 0}

    slip       = cfg.get("review", {}).get("slippage_rate", 0.001)
    apply_sell = cfg.get("review", {}).get("apply_sell_slippage", False)
    today_str  = _date.today().strftime("%Y%m%d")  # date imported as _date at module top
    now_hour   = _dt.now().hour

    updated = skipped = failed = 0
    updated_row_data = []

    for idx, row in df.iterrows():
        if _gb(row.get("buy_signal_0935")) is not True:
            continue
        if not _gf(row.get("buy_price")):
            continue
        if str(row.get("t1_open", "")).strip():  # 已填，跳过
            skipped += 1
            continue

        report_date = str(row.get("report_date", "")).strip()
        code        = str(row.get("stock_code", "")).zfill(6)

        if not report_date or not code:
            failed += 1
            continue

        t1_date = next_trading_date(report_date)

        # T+1 数据就绪检查
        if t1_date > today_str:
            logger.debug(f"[update_review] {code} T+1={t1_date} 未到来，跳过")
            skipped += 1
            continue
        if t1_date == today_str and now_hour < 15:
            logger.info(f"[update_review] {code} T+1={t1_date} 今日尚未收盘，跳过")
            skipped += 1
            continue

        hist = fetch_stock_history(code, days=10, trade_date=t1_date, cfg=cfg)
        if hist is None or hist.empty:
            logger.warning(f"[update_review] {code} T+1={t1_date} 历史数据为空，跳过")
            skipped += 1
            continue

        # 查找 T+1 对应行（date 列是 datetime 类型）
        t1_date_fmt = f"{t1_date[:4]}-{t1_date[4:6]}-{t1_date[6:8]}"
        t1_rows = hist[hist["date"].dt.strftime("%Y-%m-%d") == t1_date_fmt]
        if t1_rows.empty:
            logger.warning(f"[update_review] {code} 历史K线中未找到 {t1_date_fmt}（可能是节假日），跳过")
            skipped += 1
            continue

        t1 = t1_rows.iloc[0]
        df.at[idx, "t1_open"]  = str(round(float(t1["open"]),  3))
        df.at[idx, "t1_high"]  = str(round(float(t1["high"]),  3))
        df.at[idx, "t1_low"]   = str(round(float(t1["low"]),   3))
        df.at[idx, "t1_close"] = str(round(float(t1["close"]), 3))

        df.loc[idx] = _calc_row(df.loc[idx], slip, apply_sell)
        updated += 1
        logger.info(f"[update_review] {code} T+1={t1_date_fmt} 已填入并计算")

        updated_row = df.loc[idx]
        updated_row_data.append({
            "code":                   code,
            "name":                   str(row.get("stock_name", "")),
            "report_date":            report_date,
            "buy_price":              _gf(row.get("buy_price")),
            "adjusted_buy_price":     _gf(updated_row.get("adjusted_buy_price")),
            "stop_price":             _gf(updated_row.get("stop_price")),
            "t1_open":                _gf(updated_row.get("t1_open")),
            "t1_high":                _gf(updated_row.get("t1_high")),
            "t1_low":                 _gf(updated_row.get("t1_low")),
            "t1_close":               _gf(updated_row.get("t1_close")),
            "stop_loss_triggered":    _gb(updated_row.get("stop_loss_triggered")),
            "simulated_sell_price":   _gf(updated_row.get("simulated_sell_price")),
            "simulated_trade_return": _gf(updated_row.get("simulated_trade_return")),
            "t1_max_return":          _gf(updated_row.get("t1_max_return")),
            "max_drawdown":           _gf(updated_row.get("max_drawdown")),
            "is_active_success":      _gb(updated_row.get("is_active_success")),
            "risk_adjusted_success":  _gb(updated_row.get("risk_adjusted_success")),
            "ambiguous_path":         _gb(updated_row.get("ambiguous_path")),
            "not_bought_tracking":    False,
        })

    # 未买入票 T+1 观察追踪（not_bought_tracking）
    # 目的：验证 9:36 买入规则是否过严，观察放弃后是否大涨。不计入模拟收益。
    nb_row_data = []
    for idx, row in df.iterrows():
        if _gb(row.get("buy_signal_0935")) is not False:
            continue
        if str(row.get("not_bought_tracking", "")).strip() == "true":
            continue
        if str(row.get("t1_open", "")).strip():  # 已有 T+1 数据，跳过
            continue

        report_date = str(row.get("report_date", "")).strip()
        code        = str(row.get("stock_code", "")).zfill(6)
        if not report_date or not code:
            continue

        t1_date = next_trading_date(report_date)
        if t1_date > today_str:
            continue
        if t1_date == today_str and now_hour < 15:
            continue

        hist = fetch_stock_history(code, days=10, trade_date=t1_date, cfg=cfg)
        if hist is None or hist.empty:
            continue

        t1_date_fmt = f"{t1_date[:4]}-{t1_date[4:6]}-{t1_date[6:8]}"
        t1_rows = hist[hist["date"].dt.strftime("%Y-%m-%d") == t1_date_fmt]
        if t1_rows.empty:
            continue

        t1 = t1_rows.iloc[0]
        t1_o = round(float(t1["open"]),  3)
        t1_h = round(float(t1["high"]),  3)
        t1_l = round(float(t1["low"]),   3)
        t1_c = round(float(t1["close"]), 3)
        df.at[idx, "t1_open"]            = str(t1_o)
        df.at[idx, "t1_high"]            = str(t1_h)
        df.at[idx, "t1_low"]             = str(t1_l)
        df.at[idx, "t1_close"]           = str(t1_c)
        df.at[idx, "not_bought_tracking"] = "true"
        logger.info(f"[update_review] {code} 未买入观察 T+1={t1_date_fmt} 已填入")

        nb_row_data.append({
            "code":                str(row.get("stock_code", "")).zfill(6),
            "name":                str(row.get("stock_name", "")),
            "report_date":         report_date,
            "t1_open":             t1_o,
            "t1_high":             t1_h,
            "t1_low":              t1_l,
            "t1_close":            t1_c,
            "not_bought_tracking": True,
        })

    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    cn_display.generate_cn_csv()
    logger.info(f"[update_review] 更新{updated}条，跳过{skipped}条，失败{failed}条")
    return {
        "updated": updated,
        "skipped": skipped,
        "failed":  failed,
        "rows":    updated_row_data + nb_row_data,
    }


# =================== 汇总统计 ===================

def _compute_group_stats(df_group: pd.DataFrame) -> dict:
    """计算一组行的复盘统计，返回 stats 字典。"""
    total = len(df_group)

    valid_mask = df_group.apply(
        lambda r: _gf(r.get("open_price")) is not None and _gf(r.get("price_0935")) is not None,
        axis=1,
    )
    valid_df    = df_group[valid_mask]
    n_valid     = len(valid_df)
    triggered_df = valid_df[valid_df.apply(
        lambda r: _gb(r.get("required_conditions_passed")) is True, axis=1
    )]
    n_triggered = len(triggered_df)
    bsr         = n_triggered / n_valid if n_valid > 0 else None
    n_unable    = int(triggered_df.apply(lambda r: _gb(r.get("unable_to_buy")) is True, axis=1).sum())
    n_ambig     = int(df_group.apply(lambda r: _gb(r.get("ambiguous_path")) is True, axis=1).sum())

    def _is_traded(r):
        return (
            _gb(r.get("buy_signal_0935")) is True
            and _gb(r.get("unable_to_buy")) is not True
            and _gf(r.get("buy_price")) is not None
            and _gf(r.get("t1_close")) is not None
        )
    traded_df = df_group[df_group.apply(_is_traded, axis=1)]
    n_traded  = len(traded_df)

    def _bools(col):
        return [v for v in (traded_df[col].apply(_gb) if col in traded_df.columns else []) if v is not None]
    def _floats(col):
        return [v for v in (traded_df[col].apply(_gf) if col in traded_df.columns else []) if v is not None]
    def _rate(bs):
        return (sum(bs) / len(bs), len(bs)) if bs else (None, 0)

    stop_rate,   n_stop   = _rate(_bools("stop_loss_triggered"))
    active_rate, n_active = _rate(_bools("is_active_success"))
    surge_rate,  n_surge  = _rate(_bools("is_strong_surge"))
    close_rate,  n_close  = _rate(_bools("is_close_success"))
    risk_rate,   n_risk   = _rate(_bools("risk_adjusted_success"))

    returns  = _floats("simulated_trade_return")
    gains    = [r for r in returns if r > 0]
    losses   = [r for r in returns if r <= 0]
    avg_gain = sum(gains)  / len(gains)  if gains  else None
    avg_loss = sum(losses) / len(losses) if losses else None
    wl_ratio = abs(avg_gain / avg_loss)  if avg_gain and avg_loss else None

    mkt_caps = [_gf(v) for v in (traded_df["circulating_market_cap"]
                if "circulating_market_cap" in traded_df.columns else [])]
    mkt_caps = [v for v in mkt_caps if v is not None]

    return {
        "total": total, "n_valid": n_valid, "n_triggered": n_triggered,
        "bsr": bsr, "n_unable": n_unable, "n_ambig": n_ambig, "n_traded": n_traded,
        "stop_rate": stop_rate, "n_stop": n_stop,
        "active_rate": active_rate, "n_active": n_active,
        "surge_rate": surge_rate, "n_surge": n_surge,
        "close_rate": close_rate, "n_close": n_close,
        "risk_rate": risk_rate, "n_risk": n_risk,
        "gains": gains, "losses": losses, "avg_gain": avg_gain,
        "avg_loss": avg_loss, "wl_ratio": wl_ratio,
        "mkt_caps": mkt_caps, "valid_df": valid_df,
    }


def _print_group_stats(s: dict) -> None:
    """输出单个模式的复盘统计（中文格式）。"""
    bsr_str = f"{s['bsr']*100:.1f}%" if s['bsr'] is not None else "N/A"
    print(f"  * 样本数：        {s['total']}（有效回测 {s['n_valid']}）")
    print(f"  * 买入触发率：    {bsr_str}（触发 {s['n_triggered']} / 有效 {s['n_valid']}）")

    if s["n_traded"] == 0:
        print("  * （尚无含 T+1 数据的已交易样本）")
        return

    print(f"  * 风险调整后成功率：{_pct(s['risk_rate'])}"
          f"  （冲高≥3%且未先触止损，N={s['n_risk']}）")
    print(f"  * 冲高3%比例：    {_pct(s['active_rate'])}  （N={s['n_active']}）")
    print(f"  * 冲高5%比例：    {_pct(s['surge_rate'])}  （N={s['n_surge']}）")
    print(f"  * 收盘胜率：      {_pct(s['close_rate'])}  （次日收盘高于买入价，N={s['n_close']}）")
    print(f"  * 止损率：        {_pct(s['stop_rate'])}  （N={s['n_stop']}）")
    print()
    gain_str = f"+{s['avg_gain']*100:.2f}%（N={len(s['gains'])}）" if s['avg_gain'] is not None else "N/A"
    loss_str = f"{s['avg_loss']*100:.2f}%（N={len(s['losses'])}）"  if s['avg_loss'] is not None else "N/A"
    wl_str   = f"{s['wl_ratio']:.2f}" if s['wl_ratio'] is not None else "N/A"
    print(f"  * 平均盈利：      {gain_str}")
    print(f"  * 平均亏损：      {loss_str}")
    print(f"  * 盈亏比：        {wl_str}")


def print_summary(cfg: dict) -> None:
    """重算自动字段，输出按 mode 分组的复盘统计。"""
    df = _read_csv()
    if df is None or len(df) == 0:
        print("trade_review.csv 为空或不存在，暂无统计数据。")
        return

    slip       = cfg.get("review", {}).get("slippage_rate", 0.001)
    apply_sell = cfg.get("review", {}).get("apply_sell_slippage", False)

    df = df.apply(lambda r: _calc_row(r, slip, apply_sell), axis=1)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    cn_display.generate_cn_csv()

    def _get_mode_df(mode: str) -> pd.DataFrame:
        if "mode" not in df.columns:
            return df if mode == "full" else df.iloc[0:0]
        return df[df["mode"].apply(lambda v: (str(v).strip() or "full") == mode)]

    has_theme = (
        "mode" in df.columns
        and df["mode"].apply(lambda v: str(v).strip() == "theme_auto").any()
    )
    modes = ["full", "theme_auto"] if has_theme else ["full"]

    # ── 全局汇总 ──────────────────────────────────────────────────
    all_stats = _compute_group_stats(df)
    W = 55
    print()
    print("=" * W)
    print("  【朱哥短线雷达｜模拟盘统计】")
    print(f"  截至 {_date.today()}，共 {len(df)} 条记录")
    print("=" * W)
    bsr_all = f"{all_stats['bsr']*100:.1f}%" if all_stats['bsr'] is not None else "N/A"
    print(f"总推荐样本数：      {all_stats['total']}")
    print(f"触发模拟买入数：    {all_stats['n_triggered']}  （买入触发率 {bsr_all}）")
    print(f"无法买入样本数：    {all_stats['n_unable']}")
    print(f"路径不确定样本数：  {all_stats['n_ambig']}")

    # ── 按模式分组 ────────────────────────────────────────────────
    print()
    print("  按模式统计：")

    for i, mode in enumerate(modes, 1):
        label = "全A模式" if mode == "full" else "主题龙头模式"
        mode_df = _get_mode_df(mode)
        print()
        print(f"  {i}. {label}")
        print(f"  {'─' * (W - 4)}")
        if mode_df.empty:
            print("  （暂无数据）")
            continue
        s = _compute_group_stats(mode_df)
        _print_group_stats(s)
        if mode == "full":
            _warn_consecutive(s["valid_df"])

    print()
    print("=" * W)
    print()


def _warn_consecutive(valid_df: pd.DataFrame) -> None:
    """检查连续5天 buy_signal_rate 并输出预警。"""
    if len(valid_df) == 0:
        return

    days: dict = {}
    for _, row in valid_df.iterrows():
        rd = str(row.get("report_date", "")).strip()
        if not rd:
            continue
        if rd not in days:
            days[rd] = {"total": 0, "triggered": 0}
        days[rd]["total"] += 1
        if _gb(row.get("required_conditions_passed")) is True:
            days[rd]["triggered"] += 1

    sorted_days = sorted(days.keys())
    if len(sorted_days) < 5:
        return

    last5 = sorted_days[-5:]
    rates = [
        days[d]["triggered"] / days[d]["total"] if days[d]["total"] > 0 else 0.0
        for d in last5
    ]

    print()
    if all(r < 0.20 for r in rates):
        print("⚠️  连续5天 buy_signal_rate < 20%，买入条件可能过严，建议观察是否需要放宽。")
    elif all(r > 0.70 for r in rates):
        print("⚠️  连续5天 buy_signal_rate > 70%，买入条件可能过松，建议加强过滤。")
