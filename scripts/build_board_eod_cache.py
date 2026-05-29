"""
scripts/build_board_eod_cache.py
=================================
板块 EOD 快照生成脚本（V1.6 复盘配套）

目的：
  收盘后（>= 15:00）调 akshare 拉当天板块行情，落盘到：
    output/board_df_cache_{today}.json       (list[dict]，与现有 _load_board_df_cache 兼容)
    output/board_df_cache_{today}.meta.json  (审计元数据)

  这份"日终板块快照"会被 build_market_daily.py 的新鲜度校验认可：
    - mtime >= report_date 15:00 → sector_data_status=ok
    - 让 V1.6 tomorrow_plan 能生成 allowed_themes

严格设计约束（用户原话照搬）：
  1. 默认只允许 report_date = 今天
  2. 必须当前时间 >= 15:00 才能执行（实时接口在收盘后调 = 收盘数据）
  3. < 15:00 → 拒绝 (exit 3)
  4. report_date > 今天 → 拒绝
  5. report_date < 今天 → 拒绝（禁止用今日实时数据冒充历史 EOD）
  6. 暂不支持历史补跑（除非未来找到真历史日终接口）
  7. 不允许 fallback 到旧 cache
  8. akshare 数据源失败 → 不写文件（让 sector_data_status=missing）
  9. 主文件格式 list[dict]，兼容现有读取器
  10. 旁路 .meta.json 记录审计信息

不动：
  ✅ theme_auto.py（早盘 9:30 调度不变）
  ✅ run.py / trade_review.py / check_buy / V1.4/V1.5/V1.6 买入逻辑
  ✅ build_market_daily.py / build_tomorrow_plan.py
  ✅ launchd
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR   = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"

SCRIPT_VERSION = "v1"

# Exit code 约定（与 dashboard 按钮判定保持一致）
EXIT_OK              = 0
EXIT_GENERIC         = 1
EXIT_BAD_ARGS        = 2
EXIT_TIME_WINDOW     = 3  # 时间窗口校验失败（未到 15:00 / 未来日 / 历史日补跑）
EXIT_DATA_SOURCE     = 4  # akshare 拉数全失败
EXIT_SELF_CHECK      = 6  # 写文件后自检不通过


def _print_retry_hint(source_label: str, err: object) -> None:
    """输出更清晰的数据源失败原因和人工处理建议；不改变失败语义。"""
    err_text = str(err)
    hints = []
    if "NameResolutionError" in err_text or "Failed to resolve" in err_text:
        hints.append("DNS/网络解析失败：先确认当前网络能访问东方财富 push2 接口。")
    if "RemoteDisconnected" in err_text or "closed connection" in err_text:
        hints.append("服务端主动断开：可能是东方财富接口临时不可用、限流或反爬。")
    if "Max retries exceeded" in err_text:
        hints.append("请求已达到重试上限：可稍后重跑本脚本。")
    if not hints:
        hints.append("数据源异常：请查看完整错误，稍后重跑或手工检查 akshare/东方财富接口。")

    print(f"  [hint] {source_label} 失败处理建议：")
    for h in hints:
        print(f"         - {h}")
    print("         - 本脚本不会使用旧 cache 冒充今日盘后快照。")
    print("         - 失败后 build_market_daily 会降级为 sector_data_status=missing。")


# ════════════════════════════════════════════════════════════════════
# 时间窗口校验（用户原话核心规则）
# ════════════════════════════════════════════════════════════════════

def _validate_run_time(report_date: str) -> tuple:
    """
    返回 (is_valid: bool, detail: str)

    规则（全部硬规则，没有 --force 跳过）：
      规则 1: report_date 必须是 YYYYMMDD 格式且能解析
      规则 2: report_date 必须等于今天（不允许过去 / 未来）
      规则 3: 当前时间必须 >= 15:00
    """
    # 规则 1: 格式
    try:
        rd_dt = datetime.strptime(report_date, "%Y%m%d")
    except (ValueError, TypeError):
        return False, f"report_date={report_date!r} 格式错误（应为 YYYYMMDD）"

    now = datetime.now()
    today_str = now.strftime("%Y%m%d")

    # 规则 2: 必须等于今天
    if report_date > today_str:
        return False, f"report_date={report_date} 是未来日期（今天 {today_str}），拒绝执行"
    if report_date < today_str:
        return False, (
            f"report_date={report_date} 是历史日期（今天 {today_str}）；"
            f"本脚本拒绝补跑历史日期 — akshare 实时接口返回的是"
            f"今天的实时数据，会冒充历史 EOD 数据导致语义错位"
        )

    # 规则 3: 必须 >= 15:00
    if now.hour < 15:
        return False, (
            f"当前时间 {now:%H:%M:%S} < 15:00；A 股 15:00 收盘，"
            f"15:00 前拉的 akshare 数据是盘中实时值，不算 EOD 数据"
        )

    return True, f"时间窗口合法（now={now:%Y-%m-%d %H:%M:%S}, report_date={report_date}）"


# ════════════════════════════════════════════════════════════════════
# akshare 数据拉取（与 theme_auto._fetch_concept_boards 同口径）
# ════════════════════════════════════════════════════════════════════

def _fetch_concept_boards() -> Optional[list]:
    """
    调 akshare 概念板块行情；成功返回 list[dict]，失败返回 None。
    输出字段与现有 board_df_cache_*.json 完全兼容。
    """
    try:
        import akshare as ak
    except ImportError as e:
        print(f"  [error] akshare 未安装: {e}")
        return None

    try:
        df = ak.stock_board_concept_name_em()
    except Exception as e:
        print(f"  [error] ak.stock_board_concept_name_em() 失败: {type(e).__name__}: {e}")
        _print_retry_hint("概念板块接口", e)
        return None

    if df is None or len(df) == 0:
        print(f"  [error] akshare 返回空")
        return None

    # 字段重命名（与 theme_auto._fetch_concept_boards 同口径）
    col_map = {
        "板块名称": "name",
        "涨跌幅":   "pct_chg",
        "成交额":   "amount",
        "上涨家数": "up_count",
        "下跌家数": "down_count",
    }
    df = df.rename(columns=col_map)

    # 数值列转 numeric
    import pandas as pd
    for col in ["pct_chg", "amount", "up_count", "down_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 转 list[dict] 序列化
    try:
        records = df.to_dict("records")
    except Exception as e:
        print(f"  [error] DataFrame.to_dict 失败: {e}")
        return None

    print(f"  ✓ akshare 概念板块：{len(records)} 个")
    return records


def _fetch_industry_boards() -> Optional[list]:
    """fallback：调 akshare 行业板块行情。"""
    try:
        import akshare as ak
    except ImportError:
        return None

    try:
        df = ak.stock_board_industry_name_em()
    except Exception as e:
        print(f"  [error] ak.stock_board_industry_name_em() 失败: {type(e).__name__}: {e}")
        _print_retry_hint("行业板块接口", e)
        return None

    if df is None or len(df) == 0:
        return None

    col_map = {
        "板块名称": "name",
        "涨跌幅":   "pct_chg",
        "成交额":   "amount",
        "上涨家数": "up_count",
        "下跌家数": "down_count",
    }
    df = df.rename(columns=col_map)
    import pandas as pd
    for col in ["pct_chg", "amount", "up_count", "down_count"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    try:
        records = df.to_dict("records")
    except Exception:
        return None

    print(f"  ✓ akshare 行业板块（fallback）: {len(records)} 个")
    return records


def _fetch_boards(source: str) -> tuple:
    """
    根据 source 调度：
      'concept'   → 只拉概念
      'industry'  → 只拉行业
      'auto'      → 先概念，失败用行业
    返回 (records, data_source_label) 或 (None, None)
    """
    if source == "concept":
        return (_fetch_concept_boards(), "akshare.stock_board_concept_name_em") \
               if (records := _fetch_concept_boards()) else (None, None)
    if source == "industry":
        return (_fetch_industry_boards(), "akshare.stock_board_industry_name_em") \
               if (records := _fetch_industry_boards()) else (None, None)
    # auto
    records = _fetch_concept_boards()
    if records:
        return records, "akshare.stock_board_concept_name_em"
    records = _fetch_industry_boards()
    if records:
        return records, "akshare.stock_board_industry_name_em (fallback)"
    return None, None


# ════════════════════════════════════════════════════════════════════
# 写盘 + 自检
# ════════════════════════════════════════════════════════════════════

def _write_cache(records: list, report_date: str,
                 data_source: str, run_time_detail: str) -> tuple:
    """
    写 2 个文件：
      board_df_cache_{report_date}.json       (list[dict])
      board_df_cache_{report_date}.meta.json  (审计 dict)
    返回 (success, msg)
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    main_fp = OUTPUT_DIR / f"board_df_cache_{report_date}.json"
    meta_fp = OUTPUT_DIR / f"board_df_cache_{report_date}.meta.json"

    built_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "report_date":      report_date,
        "built_at":         built_at,
        "data_source":      data_source,
        "n_boards":         len(records),
        "script_version":   SCRIPT_VERSION,
        "run_time_check":   run_time_detail,
        "no_fallback":      True,  # 数据源失败时不会 fallback 到旧文件
        "script_path":      "scripts/build_board_eod_cache.py",
    }

    try:
        main_fp.write_text(
            json.dumps(records, ensure_ascii=False),
            encoding="utf-8",
        )
        meta_fp.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        return False, f"写文件异常: {type(e).__name__}: {e}"

    return True, f"写入成功（{main_fp.name} + {meta_fp.name}）"


def _self_check(report_date: str) -> tuple:
    """
    自检：重新读文件 + 校验 mtime >= 15:00 + 校验 n_boards > 0
    返回 (success, msg)
    """
    main_fp = OUTPUT_DIR / f"board_df_cache_{report_date}.json"

    if not main_fp.exists():
        return False, "主文件不存在"

    # 1. mtime 校验
    try:
        from datetime import datetime as _dt
        rd_close = _dt.strptime(report_date + "1500", "%Y%m%d%H%M")
    except Exception as e:
        return False, f"report_date 解析失败: {e}"

    mtime = main_fp.stat().st_mtime
    if mtime < rd_close.timestamp():
        return False, (
            f"自检失败：mtime 早于 {report_date} 15:00，"
            f"build_market_daily 仍会判 stale"
        )

    # 2. n_boards 校验
    try:
        records = json.loads(main_fp.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"重新读 JSON 失败: {e}"
    if not isinstance(records, list) or len(records) == 0:
        return False, f"records 为空（type={type(records).__name__}, len={len(records) if hasattr(records, '__len__') else '?'})"

    # 3. 必备字段校验（任一抽样行含 name + pct_chg 即可）
    sample = records[0]
    if "name" not in sample:
        return False, f"records[0] 缺 name 字段: {list(sample.keys())[:10]}"

    return True, (
        f"自检通过：n_boards={len(records)}, "
        f"mtime={_dt.fromtimestamp(mtime):%Y-%m-%d %H:%M:%S}"
    )


# ════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════

def main() -> int:
    p = argparse.ArgumentParser(
        description="板块 EOD 快照生成（V1.6 复盘配套，严格 15:00 后 + 仅当日）",
    )
    p.add_argument("--report-date", type=str, default=None,
                   help="目标日期 YYYYMMDD（默认今天；不允许过去/未来）")
    p.add_argument("--dry-run", action="store_true",
                   help="不写文件，仅打印数据预览（仍校验时间窗口）")
    p.add_argument("--source", choices=["concept", "industry", "auto"],
                   default="auto", help="数据源（默认 auto = 先概念后行业）")
    p.add_argument("--keep-existing", action="store_true",
                   help="若文件已存在且 mtime >= 15:00 则跳过")
    args = p.parse_args()

    report_date = args.report_date or datetime.now().strftime("%Y%m%d")

    print("=" * 60)
    print(f"build_board_eod_cache.py · report_date={report_date}")
    print("=" * 60)

    # —— Step 1: 时间窗口校验（硬规则，无 --force 跳过）——
    ok, detail = _validate_run_time(report_date)
    print(f"[时间窗口] {'✅' if ok else '❌'} {detail}")
    if not ok:
        return EXIT_TIME_WINDOW

    # —— Step 2: keep-existing 跳过检查 ——
    main_fp = OUTPUT_DIR / f"board_df_cache_{report_date}.json"
    if args.keep_existing and main_fp.exists():
        rd_close = datetime.strptime(report_date + "1500", "%Y%m%d%H%M")
        if main_fp.stat().st_mtime >= rd_close.timestamp():
            print(f"  [skip] {main_fp.name} 已存在且 mtime >= {report_date} 15:00，跳过")
            return EXIT_OK
        else:
            print(f"  [info] {main_fp.name} 存在但 mtime < 15:00（stale），继续重新生成")

    # —— Step 3: 拉数据 ——
    print(f"[拉数据] source={args.source}")
    records, data_source = _fetch_boards(args.source)
    if records is None:
        print(f"  ❌ 数据源全部失败 — 按规则不写文件，不 fallback")
        print(f"  [安全策略] 主线板块不可用；V1.6 明日计划应保持只观察，直到今日盘后快照成功生成。")
        print(f"  [重试建议] 稍后重跑：.venv/bin/python3 scripts/build_board_eod_cache.py")
        print(f"  [重试建议] 若概念板块持续失败，可人工试跑行业源：.venv/bin/python3 scripts/build_board_eod_cache.py --source industry")
        print(f"  [结果] board_df_cache_{report_date}.json 未生成 → "
              f"build_market_daily 会判 sector_data_status=missing")
        return EXIT_DATA_SOURCE

    # —— Step 4: dry-run 分支 ——
    if args.dry_run:
        print()
        print(f"── DRY-RUN：data_source={data_source}, n_boards={len(records)} ──")
        # 显示前 10 个板块（按 pct_chg 倒序）
        sorted_recs = sorted(
            records,
            key=lambda r: r.get("pct_chg", -999) if r.get("pct_chg") is not None else -999,
            reverse=True,
        )
        print(f"Top 10 板块（按 pct_chg 倒序）:")
        for i, r in enumerate(sorted_recs[:10], 1):
            pc  = r.get("pct_chg", "—")
            up  = r.get("up_count", "—")
            ld  = r.get("领涨股票", "—")
            lp  = r.get("领涨股票-涨跌幅", "—")
            print(f"  {i:>2d}. {str(r.get('name', '—')):24s}  pct_chg={pc}%  涨停={up}  领涨={ld}({lp}%)")
        print()
        print(f"  （未写入：{main_fp.name}）")
        return EXIT_OK

    # —— Step 5: 真跑写文件 ——
    ok, msg = _write_cache(records, report_date, data_source, detail)
    print(f"[写文件] {'✅' if ok else '❌'} {msg}")
    if not ok:
        return EXIT_GENERIC

    # —— Step 6: 自检 ——
    ok, msg = _self_check(report_date)
    print(f"[自检] {'✅' if ok else '❌'} {msg}")
    if not ok:
        return EXIT_SELF_CHECK

    print()
    print(f"✅ 完成。下游 build_market_daily.py 现可识别该 cache 为 fresh。")
    print(f"   主文件: output/board_df_cache_{report_date}.json")
    print(f"   元数据: output/board_df_cache_{report_date}.meta.json")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
