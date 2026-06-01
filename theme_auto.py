"""
theme_auto.py — 自动主题龙头模式 V1.3
根据 config/theme_keywords.yaml 的关键词自动匹配概念板块，
找出龙头候选股，复用现有评分系统，输出 theme_auto 模式前3名。

不改动选股模型、买入规则、止损规则，只作为并行实验组。
"""
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

BASE_DIR            = Path(__file__).parent
THEME_KEYWORDS_FILE = BASE_DIR / "config" / "theme_keywords.yaml"
OUTPUT_DIR          = BASE_DIR / "output"
CACHE_DIR           = BASE_DIR / "cache"

# 板块成分股内存缓存（同一次运行内去重请求）
_board_cache: Dict[str, List[str]] = {}

# 本次运行的"数据链路状态"，用于区分"数据失败"和"筛选失败"
_run_status: Dict[str, object] = {
    "constituent_total":   0,    # 计划抓取的板块数
    "constituent_ok_api":  0,    # 通过 API 成功
    "constituent_ok_cache": 0,   # 通过磁盘缓存兜底成功
    "constituent_failed":  0,    # 完全失败
    "constituent_used_stale": False,  # 是否使用了过期缓存
    "spot_failed":         False,
    "degraded_watchlist":  False,
    "errors":              [],
}


def get_run_status() -> Dict[str, object]:
    """返回本次 run_theme_auto 的数据链路状态（供调用方判断失败原因）。"""
    return dict(_run_status)


def _reset_run_status() -> None:
    _run_status.update({
        "constituent_total":   0,
        "constituent_ok_api":  0,
        "constituent_ok_cache": 0,
        "constituent_failed":  0,
        "constituent_used_stale": False,
        "spot_failed":         False,
        "degraded_watchlist":  False,
        "errors":              [],
    })


def load_watchlist() -> Tuple[List[dict], List[dict]]:
    """
    加载自选股票池。theme_auto 使用它作为成分股链路失败时的观察型降级池。
    返回 (active/watch rows, all rows)。读取失败不影响主流程。
    """
    wl_path = BASE_DIR / "data" / "watchlist" / "custom_stock_pool.csv"
    if not wl_path.exists():
        return [], []
    try:
        import csv
        with open(wl_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        active = [r for r in rows if str(r.get("status", "")).strip() in ("active", "watch")]
        return active, rows
    except Exception as e:
        logger.warning(f"[theme_auto] 自选池加载失败: {e}")
        return [], []


def _keep_watchlist_after_rank(
    ranked_df: pd.DataFrame,
    source_df: pd.DataFrame,
    wl_codes: List[str],
    stage: str,
) -> pd.DataFrame:
    """theme_auto 排名截断后保留已通过前序过滤的自选股。"""
    if ranked_df.empty or source_df.empty or not wl_codes or "code" not in source_df.columns:
        return ranked_df
    wl_set = {str(c).zfill(6) for c in wl_codes if c}
    current = set(ranked_df["code"].astype(str).str.zfill(6))
    src = source_df.copy()
    src["code"] = src["code"].astype(str).str.zfill(6)
    extras = src[src["code"].isin(wl_set) & ~src["code"].isin(current)].copy()
    if extras.empty:
        return ranked_df
    extras["_watchlist_kept_after_rank"] = stage
    merged = pd.concat([ranked_df, extras], ignore_index=True)
    merged = merged.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    logger.info(f"[theme_auto] {stage} 排名截断后补回自选池 {len(extras)} 只")
    return merged


# ─────────────────── 板块行情磁盘缓存 ────────────────────────────

def _board_cache_path(ds: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR / f"board_df_cache_{ds}.json"


def _save_board_df(df: pd.DataFrame) -> None:
    """把今日板块行情存到磁盘，供 API 失败时 fallback 使用。"""
    ds = date.today().strftime("%Y%m%d")
    try:
        _board_cache_path(ds).write_text(
            df.to_json(orient="records", force_ascii=False), encoding="utf-8"
        )
        logger.info(f"[theme_auto] 板块行情已缓存至磁盘（{ds}）")
    except Exception as e:
        logger.debug(f"[theme_auto] 写磁盘缓存失败（不影响主逻辑）: {e}")


def _load_board_df_from_disk() -> Optional[pd.DataFrame]:
    """
    优先读今日缓存，其次读昨日，再其次读最近7天内任意一天。
    全部失败则返回 None。
    """
    today = date.today()
    for delta in range(0, 8):
        ds = (today.__class__.fromordinal(today.toordinal() - delta)).strftime("%Y%m%d")
        p = _board_cache_path(ds)
        if p.exists():
            try:
                df = pd.read_json(p, orient="records")
                logger.info(f"[theme_auto] 读取磁盘板块缓存（{ds}），共 {len(df)} 条")
                return df
            except Exception:
                continue
    return None


# ─────────────────── 关键词加载 ──────────────────────────────────

def load_theme_keywords() -> Dict[str, List[str]]:
    """读取 config/theme_keywords.yaml，返回 {主题名: [关键词列表]}。"""
    with open(THEME_KEYWORDS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    themes = data.get("themes", {})
    return {name: cfg.get("keywords", []) for name, cfg in themes.items()}


# ─────────────────── 概念板块行情 ────────────────────────────────

def _fetch_concept_boards() -> Optional[pd.DataFrame]:
    """东方财富概念板块行情，失败返回 None。"""
    try:
        import akshare as ak
        df = ak.stock_board_concept_name_em()
        col_map = {"板块名称": "name", "涨跌幅": "pct_chg",
                   "成交额": "amount", "上涨家数": "up_count", "下跌家数": "down_count"}
        df = df.rename(columns=col_map)
        for col in ["pct_chg", "amount", "up_count", "down_count"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        logger.info(f"[theme_auto] 获取到 {len(df)} 个概念板块")
        return df
    except Exception as e:
        logger.warning(f"[theme_auto] 概念板块获取失败: {e}")
        return None


def _fetch_industry_boards() -> Optional[pd.DataFrame]:
    """行业板块 fallback。"""
    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        col_map = {"板块名称": "name", "涨跌幅": "pct_chg",
                   "成交额": "amount", "上涨家数": "up_count", "下跌家数": "down_count"}
        df = df.rename(columns=col_map)
        for col in ["pct_chg", "amount", "up_count", "down_count"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        logger.info(f"[theme_auto] fallback 行业板块: {len(df)} 个")
        return df
    except Exception as e:
        logger.warning(f"[theme_auto] 行业板块 fallback 失败: {e}")
        return None


def _fetch_ths_industry_boards() -> Optional[pd.DataFrame]:
    """
    同花顺行业板块汇总 fallback。

    这个接口不提供概念板块，也不直接提供成分股明细；它的作用是：
    在 EM 概念/行业板块行情都失败时，至少让主题强度和行业方向不断链。
    后续成分股仍会继续尝试 EM 行业/概念成分股接口，失败则走缓存/自选池观察降级。
    """
    try:
        import akshare as ak
        df = ak.stock_board_industry_summary_ths()
        if df is None or df.empty:
            logger.warning("[theme_auto] THS 行业板块 fallback 返回空")
            return None
        col_map = {
            "板块": "name",
            "涨跌幅": "pct_chg",
            "总成交额": "amount",
            "上涨家数": "up_count",
            "下跌家数": "down_count",
        }
        df = df.rename(columns=col_map)
        for col in ["pct_chg", "amount", "up_count", "down_count"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "amount" in df.columns:
            # THS 行业汇总的总成交额单位是"亿"，统一转为元，兼容强度计算口径。
            df["amount"] = df["amount"] * 1e8
        df["source"] = "ths_industry_summary"
        df["data_quality"] = "partial"
        logger.warning(f"[theme_auto] EM 板块接口失败，fallback THS 行业板块: {len(df)} 个")
        return df
    except Exception as e:
        logger.warning(f"[theme_auto] THS 行业板块 fallback 失败: {e}")
        return None


def _get_board_df() -> pd.DataFrame:
    """先尝试 EM 概念，再 EM 行业，再 THS 行业，最后磁盘缓存。"""
    df = _fetch_concept_boards()
    if df is None or df.empty:
        df = _fetch_industry_boards()
    if df is None or df.empty:
        df = _fetch_ths_industry_boards()
    if df is not None and not df.empty:
        _save_board_df(df)
        return df
    cached = _load_board_df_from_disk()
    if cached is not None and not cached.empty:
        logger.warning("[theme_auto] API 全部失败，使用磁盘缓存板块行情（数据可能为前几日）")
        return cached
    logger.warning("[theme_auto] 板块行情获取失败且无磁盘缓存，返回空 DataFrame")
    return pd.DataFrame(columns=["name", "pct_chg", "amount", "up_count", "down_count"])


# ─────────────────── 主题板块匹配 ────────────────────────────────

def match_theme_boards(
    themes: Dict[str, List[str]],
    board_df: pd.DataFrame,
) -> Dict[str, List[str]]:
    """
    关键词子串匹配，返回 {主题名: [匹配板块名列表]}（按 pct_chg 降序排列）。
    """
    all_boards = board_df["name"].dropna().tolist()
    # 带涨跌幅信息方便排序
    pct_map = dict(zip(board_df["name"].tolist(),
                       board_df.get("pct_chg", pd.Series(dtype=float)).tolist()))

    result: Dict[str, List[str]] = {}
    for theme, keywords in themes.items():
        matched = []
        for board in all_boards:
            for kw in keywords:
                if kw in board:
                    matched.append(board)
                    break
        # 按涨跌幅降序排列，让强势板块排前面
        matched.sort(key=lambda b: float(pct_map.get(b, 0) or 0), reverse=True)
        result[theme] = matched
        if matched:
            logger.info(f"[theme_auto] 主题「{theme}」匹配 {len(matched)} 个板块: {matched[:3]}")
        else:
            logger.warning(f"[theme_auto] 主题「{theme}」无匹配板块，将跳过")
    return result


# ─────────────────── 主题强度 ────────────────────────────────────

def calc_theme_strength(board_names: List[str], board_df: pd.DataFrame) -> float:
    """
    theme_strength 0-100。
    涨跌幅分(0-40) + 成交额分(0-30) + 上涨占比分(0-30)，取匹配板块均值。
    """
    if not board_names:
        return 0.0
    rows = board_df[board_df["name"].isin(board_names)]
    if rows.empty:
        return 0.0
    scores = []
    for _, row in rows.iterrows():
        pct_chg    = float(row.get("pct_chg",    0) or 0)
        amount     = float(row.get("amount",      0) or 0)
        up_count   = float(row.get("up_count",    0) or 0)
        down_count = float(row.get("down_count",  0) or 0)
        pct_score    = max(0.0, min(40.0, (pct_chg + 5) / 10 * 40))
        amount_score = max(0.0, min(30.0, (amount / 1e8) / 1000 * 30))
        total_cnt = up_count + down_count
        up_score  = (up_count / total_cnt * 30) if total_cnt > 0 else 15.0
        scores.append(pct_score + amount_score + up_score)
    return round(sum(scores) / len(scores), 1)


# ─────────────────── 成分股获取 ──────────────────────────────────

def _components_cache_path(ds: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"theme_components_{ds}.json"


def _load_components_disk_cache() -> Tuple[Dict[str, List[str]], Optional[str]]:
    """
    从磁盘加载最近 7 天内任意一份 theme_components_YYYYMMDD.json。
    返回 ({board: [codes...]}, cache_date) 或 ({}, None)。
    """
    today = date.today()
    for delta in range(0, 8):
        ds = (today.__class__.fromordinal(today.toordinal() - delta)).strftime("%Y%m%d")
        p  = _components_cache_path(ds)
        if not p.exists():
            continue
        try:
            import json
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                logger.info(
                    f"[theme_auto] 读取成分股磁盘缓存（{ds}），共 {len(data)} 个板块"
                )
                # 规范化：所有 code zfill 到6位
                norm = {
                    k: [str(c).zfill(6) for c in (v or []) if c]
                    for k, v in data.items()
                }
                return norm, ds
        except Exception as e:
            logger.warning(f"[theme_auto] 成分股磁盘缓存读取失败({ds}): {e}")
            continue
    return {}, None


def _save_components_disk_cache(cache_dict: Dict[str, List[str]]) -> None:
    """把本次成功抓到的成分股写入今日缓存，供后续失败时兜底。"""
    if not cache_dict:
        return
    ds = date.today().strftime("%Y%m%d")
    try:
        import json
        # 与今日已有缓存合并
        existing = {}
        p = _components_cache_path(ds)
        if p.exists():
            try:
                existing = json.loads(p.read_text(encoding="utf-8")) or {}
            except Exception:
                existing = {}
        existing.update({k: v for k, v in cache_dict.items() if v})
        p.write_text(
            json.dumps(existing, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
        logger.info(
            f"[theme_auto] 成分股已缓存至磁盘（{ds}），共 {len(existing)} 个板块"
        )
    except Exception as e:
        logger.debug(f"[theme_auto] 写成分股磁盘缓存失败（不影响主逻辑）: {e}")


# 模块级延迟加载的磁盘缓存（避免无意义的反复读盘）
_disk_components_cache: Optional[Dict[str, List[str]]] = None
_disk_components_date:  Optional[str] = None


def _ensure_disk_components_loaded() -> None:
    global _disk_components_cache, _disk_components_date
    if _disk_components_cache is None:
        _disk_components_cache, _disk_components_date = _load_components_disk_cache()


def _fetch_board_constituents(board_name: str) -> List[str]:
    """
    获取单个板块成分股：
      1. 进程内缓存
      2. 实时 API（EM 概念成分股 → EM 行业成分股）
      3. 磁盘 cache/theme_components_YYYYMMDD.json
    任何 API 失败都会用 WARNING 级别记录，便于排查。
    """
    if board_name in _board_cache:
        return _board_cache[board_name]

    # —— 1. 尝试实时 API ——
    api_err: Optional[str] = None
    try:
        import akshare as ak
        api_errors = []
        api_calls = [
            ("EM概念成分股", ak.stock_board_concept_cons_em),
            ("EM行业成分股", ak.stock_board_industry_cons_em),
        ]
        for api_name, api_func in api_calls:
            try:
                df = api_func(symbol=board_name)
                if df is not None and not df.empty and "代码" in df.columns:
                    codes = [str(c).zfill(6) for c in df["代码"].dropna().tolist()]
                    if codes:
                        _board_cache[board_name] = codes
                        _run_status["constituent_ok_api"] = int(_run_status["constituent_ok_api"]) + 1
                        logger.info(
                            f"[theme_auto] 板块「{board_name}」{api_name} 获取 {len(codes)} 只"
                        )
                        time.sleep(0.3)   # 避免接口限流
                        return codes
                    api_errors.append(f"{api_name}: API 返回空成分股列表")
                else:
                    api_errors.append(f"{api_name}: API 返回空 DataFrame 或缺少『代码』列")
            except Exception as e:
                api_errors.append(f"{api_name}: {type(e).__name__}: {e}")
        api_err = "；".join(api_errors) if api_errors else "API 未返回有效结果"
    except Exception as e:
        api_err = f"{type(e).__name__}: {e}"

    logger.warning(
        f"[theme_auto] 板块「{board_name}」成分股 API 获取失败: {api_err}，"
        f"尝试磁盘缓存兜底..."
    )
    _run_status["errors"].append(f"{board_name}: {api_err}")  # type: ignore[attr-defined]

    # —— 2. 尝试磁盘缓存 ——
    _ensure_disk_components_loaded()
    if _disk_components_cache and board_name in _disk_components_cache:
        codes = _disk_components_cache[board_name]
        if codes:
            logger.warning(
                f"[theme_auto] 板块「{board_name}」使用过期成分股缓存"
                f"（{_disk_components_date}，{len(codes)} 只）"
            )
            _board_cache[board_name] = codes
            _run_status["constituent_ok_cache"] = int(_run_status["constituent_ok_cache"]) + 1
            _run_status["constituent_used_stale"] = True
            return codes

    logger.warning(
        f"[theme_auto] 板块「{board_name}」磁盘缓存也无可用成分股，记为失败"
    )
    _board_cache[board_name] = []
    _run_status["constituent_failed"] = int(_run_status["constituent_failed"]) + 1
    return []


def collect_theme_stocks(
    theme_boards: Dict[str, List[str]],
    max_boards_per_theme: int = 3,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    按主题收集成分股，每个主题取强度最高的 max_boards_per_theme 个板块。
    返回:
      code_themes: {股票代码: [所属主题列表]}
      code_boards: {股票代码: [来源板块列表]}
    """
    # 先收集所有需要抓的板块（去重，减少 API 调用）
    all_boards_needed: List[str] = []
    theme_top_boards: Dict[str, List[str]] = {}
    for theme, boards in theme_boards.items():
        top = boards[:max_boards_per_theme]
        theme_top_boards[theme] = top
        for b in top:
            if b not in all_boards_needed:
                all_boards_needed.append(b)

    logger.info(f"[theme_auto] 需获取成分股的板块: {len(all_boards_needed)} 个")
    _run_status["constituent_total"] = len(all_boards_needed)
    for board in all_boards_needed:
        _fetch_board_constituents(board)  # 结果缓存在 _board_cache

    # 把本次拿到的（API 或缓存）写入今日磁盘缓存，下次失败时可兜底
    _save_components_disk_cache(
        {b: codes for b, codes in _board_cache.items() if codes}
    )

    # 汇总数据链路状态日志
    logger.info(
        f"[theme_auto] 成分股数据链路汇总："
        f"计划 {_run_status['constituent_total']} 个板块，"
        f"API成功 {_run_status['constituent_ok_api']}，"
        f"缓存兜底 {_run_status['constituent_ok_cache']}，"
        f"完全失败 {_run_status['constituent_failed']}，"
        f"使用过期缓存={_run_status['constituent_used_stale']}"
    )

    code_themes: Dict[str, List[str]] = {}
    code_boards: Dict[str, List[str]] = {}
    for theme, boards in theme_top_boards.items():
        if not boards:
            continue
        for board in boards:
            for code in _board_cache.get(board, []):
                if theme not in code_themes.get(code, []):
                    code_themes.setdefault(code, []).append(theme)
                if board not in code_boards.get(code, []):
                    code_boards.setdefault(code, []).append(board)

    for theme, boards in theme_top_boards.items():
        cnt = sum(1 for c, ts in code_themes.items() if theme in ts)
        logger.info(f"[theme_auto] 主题「{theme}」收集到 {cnt} 只候选股")

    return code_themes, code_boards


# ─────────────────── theme_bonus ─────────────────────────────────

def calc_theme_bonus(
    theme_strength: float,
    rank_in_theme: int,
    is_top_theme: bool,
) -> float:
    """
    theme_bonus 最高 20 分：
      theme_strength 折算 0-10
      主题内排名       0-6  (1→6, 2→4, 3→3, 其余→1)
      当日最强主题加成 0-4
    """
    strength_score = min(10.0, theme_strength / 10)
    rank_score     = {1: 6, 2: 4, 3: 3}.get(rank_in_theme, 1)
    top_score      = 4 if is_top_theme else 0
    return round(strength_score + rank_score + top_score, 2)


# ─────────────────── 主入口 ──────────────────────────────────────

def run_theme_auto(cfg: dict) -> tuple:
    """
    主题龙头模式主入口。
    返回 (top3, market_data, theme_summary, data_date, report_date)
    top3 与 full 模式格式相同，额外含 theme_name/theme_strength/theme_bonus/
    theme_auto_score/theme_source_boards/theme_other 字段。
    """
    import data_fetcher as fetcher
    import filters
    import indicators as ind_calc
    import scorer
    import market_guard

    data_date, report_date = fetcher.calc_dates()
    fetcher.reset_run_provenance()
    _reset_run_status()

    # ── 主题关键词 ────────────────────────────────────────────────
    try:
        themes = load_theme_keywords()
    except Exception as e:
        logger.error(f"[theme_auto] 读取 theme_keywords.yaml 失败: {e}")
        _run_status["errors"].append(f"load_theme_keywords: {e}")  # type: ignore
        return [], {}, {}, data_date, report_date

    # ── 板块行情 + 匹配 ───────────────────────────────────────────
    board_df      = _get_board_df()
    theme_boards  = match_theme_boards(themes, board_df)
    theme_strengths: Dict[str, float] = {
        t: calc_theme_strength(boards, board_df)
        for t, boards in theme_boards.items()
    }
    theme_summary = dict(
        sorted(theme_strengths.items(), key=lambda x: x[1], reverse=True)
    )
    active_themes = {t: s for t, s in theme_summary.items() if s > 0}
    if not active_themes:
        logger.warning("[theme_auto] 所有主题强度均为0，无法生成推荐")
        return [], {}, theme_summary, data_date, report_date

    top_theme = next(iter(active_themes))
    logger.info(f"[theme_auto] 最强主题：{top_theme}（{active_themes[top_theme]:.1f}/100）")

    # ── 候选股收集 ────────────────────────────────────────────────
    code_themes, code_boards = collect_theme_stocks(theme_boards)
    active_wl, _ = load_watchlist()
    wl_codes = [
        str(r.get("stock_code", "")).strip().zfill(6)
        for r in active_wl
        if str(r.get("stock_code", "")).strip()
    ]

    # 自选池第一优先：即使主题成分股链路正常，也把自选股并入主题观察评估池。
    # 这只是进入观察评估，不绕过后续 quick_filter/history_filter/评分/V1.6/9:36。
    for code in wl_codes:
        code_themes.setdefault(code, [top_theme])
        if "自选池观察" not in code_themes[code]:
            code_themes[code].append("自选池观察")
        code_boards.setdefault(code, [])
        if "custom_stock_pool" not in code_boards[code]:
            code_boards[code].append("custom_stock_pool")

    all_codes = list(code_themes.keys())
    total_constituents = int(_run_status["constituent_total"])
    failed_constituents = int(_run_status["constituent_failed"])
    if total_constituents > 0 and failed_constituents == total_constituents and wl_codes:
        _run_status["degraded_watchlist"] = True
        logger.warning(
            "[theme_auto] 主题成分股链路全部失败，已降级并入自选池观察评估："
            f"{len(wl_codes)} 只。该结果仅供观察，不代表完整主题龙头。"
        )
    if not all_codes:
        # 区分"成分股数据失败"和"主题真的没匹配到候选"
        total  = total_constituents
        failed = failed_constituents
        if total > 0 and failed == total:
            logger.error(
                "[theme_auto] 主题已识别，但板块成分股 API 全部失败、"
                "磁盘缓存也无数据，无法生成候选 —— 这是数据链路失败，"
                "不是策略筛选失败"
            )
            return [], {}, theme_summary, data_date, report_date
        elif total > 0 and failed > 0:
            logger.warning(
                f"[theme_auto] 主题已识别，但 {failed}/{total} 个板块"
                f"成分股获取失败，剩余板块也未匹配到任何代码 —— "
                f"疑似数据链路失败"
            )
            return [], {}, theme_summary, data_date, report_date
        else:
            logger.warning("[theme_auto] 未收集到任何候选股")
            return [], {}, theme_summary, data_date, report_date

    logger.info(f"[theme_auto] 候选股（去重后）: {len(all_codes)} 只")

    # ── 市场快照 + 硬排除/粗筛 ───────────────────────────────────
    spot_df = fetcher.fetch_market_spot(data_date, cfg=cfg)
    if spot_df.empty:
        logger.error("[theme_auto] 市场行情为空 —— 个股行情数据链路失败")
        _run_status["spot_failed"] = True
        return [], {}, theme_summary, data_date, report_date

    spot_prov = fetcher.get_run_provenance()
    if spot_prov.get("is_stale_cache"):
        logger.warning(
            f"[theme_auto] ⚠️ 个股行情使用过期缓存"
            f"（{spot_prov.get('stale_cache_date')}），仅供观察"
        )

    spot_theme = spot_df[spot_df["code"].isin(all_codes)].copy()
    if spot_theme.empty:
        # 候选股代码全部在行情表中找不到 —— 通常是代码格式不一致或行情链路异常
        sample_codes = list(all_codes)[:5]
        sample_spot  = spot_df["code"].astype(str).head(5).tolist() if not spot_df.empty else []
        logger.error(
            f"[theme_auto] 候选股在行情快照中无匹配 —— 疑似数据格式不一致或数据链路问题。"
            f" 候选样例={sample_codes}  行情样例={sample_spot}"
        )
        return [], {}, theme_summary, data_date, report_date

    filtered = filters.quick_filter(spot_theme, cfg)
    if filtered.empty:
        logger.warning("[theme_auto] quick_filter 后候选股为空")
        return [], {}, theme_summary, data_date, report_date

    top_n_hist = cfg["screening"].get("top_n_for_history", 100)
    candidate_df = filters.rank_and_select(filtered, top_n=min(top_n_hist, len(filtered)))
    candidate_df = _keep_watchlist_after_rank(
        candidate_df, filtered, wl_codes, "history_candidate"
    )

    # ── 历史K线 + 精筛 ────────────────────────────────────────────
    hist_map = fetcher.fetch_batch_history(
        candidate_df["code"].tolist(), days=80, trade_date=data_date, cfg=cfg
    )
    deep_filtered = filters.history_filter(candidate_df, hist_map, cfg)
    if deep_filtered.empty:
        logger.warning("[theme_auto] history_filter 后候选股为空")
        return [], {}, theme_summary, data_date, report_date

    top_n_final = cfg["screening"].get("top_n_final", 50)
    scored_pool = filters.rank_and_select(
        deep_filtered, top_n=min(top_n_final, len(deep_filtered))
    )
    scored_pool = _keep_watchlist_after_rank(
        scored_pool, deep_filtered, wl_codes, "scored_pool"
    )

    # ── 打分 + theme_bonus ────────────────────────────────────────
    all_amounts = scored_pool["amount"]
    raw_results = []
    theme_rank_counter: Dict[str, int] = {}

    # 先按系统分排序以确定主题内排名
    pre_scored = []
    for _, row in scored_pool.iterrows():
        code = row["code"]
        hist = hist_map.get(code)
        if hist is None:
            continue
        ind = ind_calc.compute(hist, row, code, cfg)
        if ind is None:
            continue
        scores  = scorer.score_stock(ind, all_amounts, cfg)
        stype   = scorer.classify_type(ind, scores)
        reasons = scorer.generate_reasons(ind, scores, row)
        stock_themes = code_themes.get(code, [])
        main_theme   = max(stock_themes, key=lambda t: theme_strengths.get(t, 0)) \
                       if stock_themes else ""
        pre_scored.append({
            "code": code, "name": row["name"],
            "scores": scores, "ind": ind, "type": stype,
            "reasons": reasons, "spot_row": row,
            "theme_name":   main_theme,
            "theme_other":  [t for t in stock_themes if t != main_theme],
            "theme_strength":      theme_strengths.get(main_theme, 0),
            "theme_source_boards": list(set(code_boards.get(code, []))),
        })

    # 按系统总分排序，统计主题内排名
    pre_scored.sort(key=lambda x: x["scores"]["total"], reverse=True)
    for r in pre_scored:
        t = r["theme_name"]
        theme_rank_counter[t] = theme_rank_counter.get(t, 0) + 1
        r["theme_rank"]  = theme_rank_counter[t]
        r["theme_bonus"] = calc_theme_bonus(
            r["theme_strength"], r["theme_rank"], r["theme_name"] == top_theme
        )
        r["theme_auto_score"] = round(r["scores"]["total"] * 0.8 + r["theme_bonus"], 2)
        raw_results.append(r)

    if not raw_results:
        logger.warning("[theme_auto] 打分后无有效结果")
        return [], {}, theme_summary, data_date, report_date

    # 按 theme_auto_score 全局排序，同一只股票只保留最高分那条
    raw_results.sort(key=lambda x: x["theme_auto_score"], reverse=True)
    seen: set = set()
    deduped = []
    for r in raw_results:
        if r["code"] not in seen:
            seen.add(r["code"])
            deduped.append(r)

    top3 = deduped[:cfg["scoring"].get("output_top_n", 3)]

    for r in top3:
        logger.info(
            f"  {r['code']} {r['name']}  主题:{r['theme_name']}  "
            f"强度:{r['theme_strength']}  系统分:{r['scores']['total']}  "
            f"主题分:{r['theme_auto_score']}"
        )

    # ── 市场情绪 ──────────────────────────────────────────────────
    limit_up_df = fetcher.fetch_limit_up_pool(data_date)
    burst_df    = fetcher.fetch_burst_board_pool(data_date)
    index_chg   = fetcher.fetch_sh_index_change(data_date)
    market_data = market_guard.calc_sentiment(limit_up_df, burst_df, spot_df, index_chg, cfg)

    return top3, market_data, theme_summary, data_date, report_date
