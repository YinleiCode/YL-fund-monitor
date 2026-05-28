"""
scripts/run_money_flow_simulation.py
=====================================
V1.5-alpha 资金预筛模拟器 — 严格只读，绝不接入正式策略

目的：
  回答一个问题——"如果现在加上 V1.5 资金预筛，最近 N 天的推荐票会被
  留下还是被资金过滤？被过滤掉的票后续 T+1 表现如何？"

工作模式：
  1. 只读 output/trade_review.csv 最近 N 个 report_date 的推荐记录
  2. 对每只票调用 money_flow.evaluate_money_flow_health(code)
     - 优先用主源 push2his（含磁盘缓存）
     - 不可用时 fallback 到 ths_simple
     - 都不可用时记 "资金源不可用"
  3. 把结果落地到：
     - output/money_flow_simulation/money_flow_simulation_YYYYMMDD.csv
     - output/money_flow_simulation/money_flow_simulation_YYYYMMDD.md

严格只读保证：
  ✅ 不写 output/trade_review.csv
  ✅ 不调用 run.py / theme_auto.py / scorer.py
  ✅ 不修改任何 launchd 任务
  ✅ 不新增 "启用 V1.5" 按钮
  ✅ money_flow.evaluate_money_flow_health 内部允许写缓存 cache/
     （这是它本来就有的行为，不算"写数据"，只是给后续重跑加速）

用法：
  .venv/bin/python3 scripts/run_money_flow_simulation.py
  .venv/bin/python3 scripts/run_money_flow_simulation.py --days 5
  .venv/bin/python3 scripts/run_money_flow_simulation.py --days 10 --no-cache
  .venv/bin/python3 scripts/run_money_flow_simulation.py --output-date 20260527
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── 路径定位 ───────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pandas as pd  # noqa: E402

import money_flow  # noqa: E402

CSV_PATH = BASE_DIR / "output" / "trade_review.csv"
OUT_DIR  = BASE_DIR / "output" / "money_flow_simulation"


# ── 工具函数 ───────────────────────────────────────────────────────
def _zfill6(x) -> str:
    """trade_review.csv 里 stock_code 是数字（000100 会被存成 100），统一补零到 6 位。"""
    if pd.isna(x):
        return ""
    try:
        return str(int(float(x))).zfill(6)
    except (ValueError, TypeError):
        return str(x).zfill(6)


def _fmt_pct(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    try:
        return f"{float(v) * 100:+.2f}%"
    except (ValueError, TypeError):
        return "—"


def _fmt_yi(v) -> str:
    """元 → 亿元（带符号）。"""
    if v is None or pd.isna(v):
        return "—"
    try:
        return f"{float(v) / 1e8:+.2f}亿"
    except (ValueError, TypeError):
        return "—"


def _safe_bool(v) -> Optional[bool]:
    """trade_review.csv 里 True/False 可能存成 'True' / 'False' / 1 / 0 / NaN。"""
    if v is None or pd.isna(v):
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "1.0", "yes", "y"):  return True
    if s in ("false", "0", "0.0", "no", "n", ""): return False
    return None


def _derive_v15_decision(mf: dict) -> str:
    """
    根据 money_flow.evaluate_money_flow_health 返回的 dict 推导 V1.5 资金预筛决策：
      "保留"      — is_healthy=True（主源 ok 或 备源 ok）
      "过滤"      — 资金源能用但判定不健康
      "资金源不可用" — 主源 + 备源都死
      "数据缺失"   — 接口活但该股票没有 3 日数据（新股 / 停牌 / 退市等）
    """
    data_source = (mf.get("data_source") or "").lower()
    status      = (mf.get("status") or "").lower()
    is_healthy  = bool(mf.get("is_healthy"))

    if data_source in ("", "unavailable") or status == "fetch_failed":
        return "资金源不可用"
    if status == "missing":
        return "数据缺失"
    return "保留" if is_healthy else "过滤"


# ── 读 CSV ──────────────────────────────────────────────────────────
def load_recent_recommendations(days: int) -> pd.DataFrame:
    """
    读最近 N 个 report_date 的全部推荐记录。
    返回标准化后的 DataFrame（stock_code 已 zfill6）。
    """
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"找不到 {CSV_PATH}")

    df = pd.read_csv(CSV_PATH, dtype={"report_date": str, "data_date": str})
    if df.empty:
        return df

    # 标准化代码（000100 在 CSV 里可能是 100）
    df["_code6"] = df["stock_code"].apply(_zfill6)

    # 最近 N 个 report_date
    all_dates = sorted(df["report_date"].dropna().unique())
    if not all_dates:
        return df.iloc[0:0]
    keep_dates = set(all_dates[-days:])
    df = df[df["report_date"].isin(keep_dates)].copy()
    df = df.sort_values(["report_date", "mode", "rank"]).reset_index(drop=True)
    return df


# ── 跑模拟 ──────────────────────────────────────────────────────────
def simulate_one(code: str, use_cache: bool = True) -> dict:
    """对单只票调用 money_flow.evaluate_money_flow_health。"""
    t0 = time.time()
    try:
        mf = money_flow.evaluate_money_flow_health(
            code,
            days=3,
            use_cache=use_cache,
            allow_fallback=True,
        )
        mf["_probe_elapsed_s"] = round(time.time() - t0, 2)
        mf["_probe_error"]     = ""
    except Exception as e:
        mf = {
            "code":             code,
            "data_source":      "unavailable",
            "source_level":     "unavailable",
            "status":           "fetch_failed",
            "is_healthy":       False,
            "reason_code":      "exception",
            "reason_cn":        f"调用异常：{type(e).__name__}: {e}",
            "_probe_elapsed_s": round(time.time() - t0, 2),
            "_probe_error":     f"{type(e).__name__}: {e}",
        }
    return mf


def build_simulation_rows(rec_df: pd.DataFrame, use_cache: bool = True) -> pd.DataFrame:
    """
    对每条推荐记录跑一次资金模拟，组装成宽表。
    一只票一天一个 mode 一行（与 trade_review.csv 行一一对应）。
    """
    rows = []
    n = len(rec_df)
    print(f"\n[simulate] 待模拟 {n} 行（最近 {rec_df['report_date'].nunique()} 个交易日）")

    # 同一只票同一天可能被 full + theme_auto 重复推：缓存避免重复调用
    cache_per_code: dict = {}

    for i, row in rec_df.iterrows():
        code = row["_code6"]
        if not code:
            continue
        if code in cache_per_code:
            mf = cache_per_code[code]
            sym = "·"  # 复用缓存
        else:
            mf = simulate_one(code, use_cache=use_cache)
            cache_per_code[code] = mf
            sym = "✓" if mf.get("is_healthy") else ("?" if mf.get("status") != "ok" else "✗")
        decision = _derive_v15_decision(mf)

        rows.append({
            "report_date":    row.get("report_date", ""),
            "data_date":      row.get("data_date", ""),
            "mode":           row.get("mode", ""),
            "rank":           row.get("rank", ""),
            "stock_code":     code,
            "stock_name":     row.get("stock_name", ""),
            "theme_name":     row.get("theme_name", "") if row.get("mode") == "theme_auto" else "",
            "total_score":    row.get("total_score", ""),

            # 原始结果（来自 trade_review.csv）
            "orig_recommended":  True,     # 进了 CSV 就是被推荐过的
            "orig_buy_signal_0935":   _safe_bool(row.get("buy_signal_0935")),
            "orig_adjusted_buy_price": row.get("adjusted_buy_price", ""),
            "orig_unable_to_buy":      _safe_bool(row.get("unable_to_buy")),
            "orig_stop_loss_triggered":_safe_bool(row.get("stop_loss_triggered")),

            # T+1 表现（如果已复盘）
            "t1_max_return":          row.get("t1_max_return", ""),
            "t1_close_return":        row.get("t1_close_return", ""),
            "simulated_trade_return": row.get("simulated_trade_return", ""),

            # money_flow 探测结果
            "mf_data_source":   mf.get("data_source", ""),
            "mf_source_level":  mf.get("source_level", ""),
            "mf_status":        mf.get("status", ""),
            "mf_is_healthy":    bool(mf.get("is_healthy")),
            # 主源 push2his 专有字段（备源情况下值为 0/None，渲染时按 source 区分展示）
            "mf_inflow_days":   mf.get("main_net_inflow_days"),
            "mf_inflow_total":  mf.get("main_net_inflow_total"),
            "mf_inflow_ratio_avg": mf.get("main_net_inflow_ratio_avg"),
            # 备源 ths_simple 专有字段（主源情况下为 None）
            "mf_ths_net_total":         mf.get("ths_net_total"),
            "mf_ths_period":            mf.get("ths_period", ""),
            "mf_ths_period_pct_change": mf.get("ths_period_pct_change"),

            "mf_reason_code":   mf.get("reason_code", ""),
            "mf_reason_cn":     mf.get("reason_cn", ""),
            "mf_latest_date":   mf.get("latest_date", ""),

            # V1.5 决策
            "v15_decision":     decision,
            "_probe_elapsed_s": mf.get("_probe_elapsed_s", 0.0),
        })

        print(f"  [{i+1:3d}/{n}] {sym} {code} {row.get('stock_name','')[:8]:8s}"
              f"  src={mf.get('data_source',''):11s}"
              f"  status={mf.get('status',''):14s}"
              f"  healthy={'Y' if mf.get('is_healthy') else 'N'}"
              f"  → {decision}")

    return pd.DataFrame(rows)


# ── 汇总统计 ───────────────────────────────────────────────────────
def compute_summary(sim_df: pd.DataFrame) -> dict:
    """
    返回 dict：含全局统计 + 按 mode 拆分 + 反事实对比（被过滤票 vs 通过票的 T+1 表现）
    """
    if sim_df.empty:
        return {"empty": True}

    total = len(sim_df)
    decision_counts = sim_df["v15_decision"].value_counts().to_dict()

    # 按 mode 拆分通过率
    per_mode = {}
    for mode in sorted(sim_df["mode"].dropna().unique()):
        sub = sim_df[sim_df["mode"] == mode]
        sub_total = len(sub)
        if sub_total == 0:
            continue
        pass_n   = int((sub["v15_decision"] == "保留").sum())
        filt_n   = int((sub["v15_decision"] == "过滤").sum())
        miss_n   = int((sub["v15_decision"] == "数据缺失").sum())
        unavl_n  = int((sub["v15_decision"] == "资金源不可用").sum())
        per_mode[mode] = {
            "total":         sub_total,
            "pass":          pass_n,
            "filter":        filt_n,
            "missing":       miss_n,
            "unavailable":   unavl_n,
            "pass_rate":     pass_n / sub_total if sub_total else 0.0,
        }

    # 反事实：被过滤票后续 T+1 是否反而大涨？通过票 T+1 是否更好？
    def _avg_t1(sub: pd.DataFrame, col: str) -> Optional[float]:
        vals = pd.to_numeric(sub[col], errors="coerce").dropna()
        if vals.empty: return None
        return float(vals.mean())

    def _hit_rate(sub: pd.DataFrame, col: str, threshold: float) -> Optional[float]:
        """T+1 收益 > 阈值（如 0.03 = 3%）的比例。"""
        vals = pd.to_numeric(sub[col], errors="coerce").dropna()
        if vals.empty: return None
        return float((vals > threshold).sum() / len(vals))

    kept     = sim_df[sim_df["v15_decision"] == "保留"]
    filtered = sim_df[sim_df["v15_decision"] == "过滤"]

    counterfactual = {
        "kept": {
            "n":                       len(kept),
            "avg_t1_max_return":       _avg_t1(kept, "t1_max_return"),
            "avg_t1_close_return":     _avg_t1(kept, "t1_close_return"),
            "avg_simulated_trade_return": _avg_t1(kept, "simulated_trade_return"),
            "hit_rate_t1max_gt_3pct":  _hit_rate(kept, "t1_max_return", 0.03),
        },
        "filtered": {
            "n":                       len(filtered),
            "avg_t1_max_return":       _avg_t1(filtered, "t1_max_return"),
            "avg_t1_close_return":     _avg_t1(filtered, "t1_close_return"),
            "avg_simulated_trade_return": _avg_t1(filtered, "simulated_trade_return"),
            "hit_rate_t1max_gt_3pct":  _hit_rate(filtered, "t1_max_return", 0.03),
        },
    }

    # 资金源覆盖率
    source_counts = sim_df["mf_data_source"].value_counts().to_dict()

    return {
        "empty":              False,
        "total":              total,
        "decision_counts":    decision_counts,
        "per_mode":           per_mode,
        "counterfactual":     counterfactual,
        "source_counts":      source_counts,
        "date_range":         (sim_df["report_date"].min(), sim_df["report_date"].max()),
        "n_dates":            int(sim_df["report_date"].nunique()),
        "elapsed_total_s":    float(sim_df["_probe_elapsed_s"].sum()),
    }


# ── 输出 ───────────────────────────────────────────────────────────
def render_markdown(sim_df: pd.DataFrame, summary: dict, *,
                    days_req: int, use_cache: bool, ts: str) -> str:
    if summary.get("empty"):
        return f"# 资金预筛模拟报告（{ts}）\n\n⚠️ 没有可模拟的记录。\n"

    lines = []
    lines.append(f"# V1.5-alpha 资金预筛模拟报告")
    lines.append("")
    lines.append(f"- 生成时间：`{ts}`")
    lines.append(f"- 请求窗口：最近 {days_req} 个 `report_date`")
    lines.append(f"- 实际窗口：`{summary['date_range'][0]}` ～ `{summary['date_range'][1]}`（{summary['n_dates']} 个交易日）")
    lines.append(f"- 模拟样本：{summary['total']} 行")
    lines.append(f"- 资金缓存：{'✅ 启用（与每日跑同一份缓存）' if use_cache else '❌ 禁用（强制重新拉）'}")
    lines.append(f"- 探测耗时：{summary['elapsed_total_s']:.1f}s")
    lines.append("")
    lines.append("> ⚠️ **本报告只是 V1.5-alpha 模拟**，不接入今日推荐、不接入 9:36 买入、不写 `trade_review.csv`。")
    lines.append("")

    # ── 1) V1.5 决策分布 ──
    lines.append("## 1. V1.5 预筛决策分布")
    lines.append("")
    lines.append("| 决策 | 数量 | 占比 |")
    lines.append("|---|---:|---:|")
    for k in ["保留", "过滤", "数据缺失", "资金源不可用"]:
        v = summary["decision_counts"].get(k, 0)
        pct = (v / summary["total"] * 100) if summary["total"] else 0
        lines.append(f"| {k} | {v} | {pct:.1f}% |")
    lines.append("")

    # ── 2) 按 mode 拆分 ──
    lines.append("## 2. 按模式拆分")
    lines.append("")
    lines.append("| 模式 | 总数 | 保留 | 过滤 | 数据缺失 | 资金源不可用 | V1.5 通过率 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for mode, st in summary["per_mode"].items():
        lines.append(
            f"| {mode} | {st['total']} | {st['pass']} | {st['filter']} | "
            f"{st['missing']} | {st['unavailable']} | {st['pass_rate']*100:.1f}% |"
        )
    lines.append("")

    # ── 3) 资金源使用分布 ──
    lines.append("## 3. 资金源使用分布")
    lines.append("")
    lines.append("| 数据源 | 次数 |")
    lines.append("|---|---:|")
    for src, n in summary["source_counts"].items():
        lines.append(f"| `{src or '(空)'}` | {n} |")
    lines.append("")

    # ── 4) 反事实对比 ──
    lines.append("## 4. 反事实对比：通过票 vs 被过滤票 的 T+1 实际表现")
    lines.append("")
    cf = summary["counterfactual"]
    def _fmtpct(v):
        return "—" if v is None else f"{v*100:+.2f}%"
    def _fmtrate(v):
        return "—" if v is None else f"{v*100:.1f}%"
    lines.append("| 维度 | 通过票（V1.5 保留）| 被过滤票（V1.5 弃）|")
    lines.append("|---|---:|---:|")
    lines.append(f"| 样本数 | {cf['kept']['n']} | {cf['filtered']['n']} |")
    lines.append(f"| T+1 最高收益均值 | {_fmtpct(cf['kept']['avg_t1_max_return'])} | {_fmtpct(cf['filtered']['avg_t1_max_return'])} |")
    lines.append(f"| T+1 收盘收益均值 | {_fmtpct(cf['kept']['avg_t1_close_return'])} | {_fmtpct(cf['filtered']['avg_t1_close_return'])} |")
    lines.append(f"| 模拟成交收益均值 | {_fmtpct(cf['kept']['avg_simulated_trade_return'])} | {_fmtpct(cf['filtered']['avg_simulated_trade_return'])} |")
    lines.append(f"| T+1 最高 > +3% 命中率 | {_fmtrate(cf['kept']['hit_rate_t1max_gt_3pct'])} | {_fmtrate(cf['filtered']['hit_rate_t1max_gt_3pct'])} |")
    lines.append("")

    # 反事实解读
    kept_avg = cf["kept"].get("avg_t1_max_return")
    filt_avg = cf["filtered"].get("avg_t1_max_return")
    if kept_avg is not None and filt_avg is not None:
        if filt_avg > kept_avg + 0.01:
            lines.append("> ⚠️ **被过滤票 T+1 平均最高收益反而高于通过票**——本窗口样本下，V1.5 资金预筛可能造成误杀。")
        elif kept_avg > filt_avg + 0.01:
            lines.append("> ✅ **通过票 T+1 平均最高收益高于被过滤票**——本窗口样本下，V1.5 资金预筛方向正确。")
        else:
            lines.append("> · 通过票与被过滤票 T+1 平均收益接近——本窗口样本不足以下结论。")
    else:
        lines.append("> · T+1 复盘数据不足，无法判断 V1.5 是否误杀。（请等 T+1 收盘后重跑）")
    lines.append("")

    # ── 5) 明细表 ──
    lines.append("## 5. 模拟明细")
    lines.append("")
    lines.append("> 「资金口径」列按数据源区分展示：")
    lines.append("> · 主源 `push2his` → 显示「主力净流入天数 / 累计 / 占比均值」")
    lines.append("> · 备源 `ths_simple` → 显示「3 日资金净额」（**简化口径，无大单分级**）")
    lines.append("")
    lines.append("| 日期 | 模式 | 代码 | 名称 | 资金源 | 状态 | 健康 | 资金口径 | V1.5 | T+1 最高 |")
    lines.append("|---|---|---|---|---|---|:-:|---|---|---:|")
    for _, r in sim_df.iterrows():
        emoji_dec = {"保留": "✅", "过滤": "❌", "数据缺失": "·", "资金源不可用": "⚠️"}.get(r["v15_decision"], "?")
        emoji_h   = "Y" if r["mf_is_healthy"] else "N"
        src       = r["mf_data_source"]
        # 按数据源区分展示
        if src == "push2his":
            days_str  = "—" if pd.isna(r["mf_inflow_days"])  else str(int(r["mf_inflow_days"]))
            total_str = _fmt_yi(r["mf_inflow_total"])
            ratio_str = "—" if pd.isna(r["mf_inflow_ratio_avg"]) else f"{r['mf_inflow_ratio_avg']:+.2f}%"
            metric = f"流入 {days_str}/3 天 · 累计 {total_str} · 占比均值 {ratio_str}"
        elif src == "ths_simple":
            ths_net  = _fmt_yi(r["mf_ths_net_total"])
            metric = f"3 日资金净额 {ths_net}　<sub>⚠️ 简化口径</sub>"
        else:
            metric = "—"
        t1m = _fmt_pct(r["t1_max_return"])
        lines.append(
            f"| {r['report_date']} | {r['mode']} | {r['stock_code']} | "
            f"{str(r['stock_name'])[:8]} | `{src}` | {r['mf_status']} | {emoji_h} | "
            f"{metric} | {emoji_dec} {r['v15_decision']} | {t1m} |"
        )
    lines.append("")

    # ── 6) 被过滤票详情 ──
    filt_df = sim_df[sim_df["v15_decision"] == "过滤"]
    if not filt_df.empty:
        lines.append(f"## 6. 被过滤票详情（{len(filt_df)} 只）")
        lines.append("")
        lines.append("| 日期 | 模式 | 代码 | 名称 | 过滤原因 | T+1 最高 | T+1 收盘 |")
        lines.append("|---|---|---|---|---|---:|---:|")
        for _, r in filt_df.iterrows():
            t1m = _fmt_pct(r["t1_max_return"])
            t1c = _fmt_pct(r["t1_close_return"])
            lines.append(
                f"| {r['report_date']} | {r['mode']} | {r['stock_code']} | "
                f"{str(r['stock_name'])[:8]} | {r['mf_reason_cn'][:40]} | {t1m} | {t1c} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> 本报告由 `scripts/run_money_flow_simulation.py` 生成，**只读**。")
    lines.append("> 不修改 `trade_review.csv`，不影响今日推荐、不影响 9:36 买入、不影响 launchd 任务。")
    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(
        description="V1.5-alpha 资金预筛模拟器（只读、不接入正式策略）",
    )
    p.add_argument("--days", type=int, default=5,
                   help="模拟最近 N 个 report_date 的推荐记录（默认 5）")
    p.add_argument("--no-cache", action="store_true",
                   help="禁用 money_flow 磁盘缓存，强制重新拉（更慢但更新）")
    p.add_argument("--output-date", type=str, default=None,
                   help="输出文件名用的日期（默认今天，格式 YYYYMMDD）")
    args = p.parse_args()

    use_cache  = not args.no_cache
    today_yyyymmdd = args.output_date or datetime.now().strftime("%Y%m%d")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 70)
    print("V1.5-alpha 资金预筛模拟器（只读）")
    print("=" * 70)
    print(f"CSV 输入：{CSV_PATH}")
    print(f"窗口：    最近 {args.days} 个 report_date")
    print(f"缓存：    {'启用' if use_cache else '禁用'}")
    print(f"输出目录：{OUT_DIR}")
    print()

    # ── 1) 读 ──
    try:
        rec_df = load_recent_recommendations(args.days)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    if rec_df.empty:
        print("⚠️ 没有可模拟的推荐记录。")
        return 0

    # ── 2) 跑 ──
    sim_df = build_simulation_rows(rec_df, use_cache=use_cache)
    summary = compute_summary(sim_df)

    # ── 3) 写 ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"money_flow_simulation_{today_yyyymmdd}.csv"
    md_path  = OUT_DIR / f"money_flow_simulation_{today_yyyymmdd}.md"

    sim_df.to_csv(csv_path, index=False, encoding="utf-8")
    md_text = render_markdown(sim_df, summary, days_req=args.days, use_cache=use_cache, ts=ts)
    md_path.write_text(md_text, encoding="utf-8")

    # ── 4) 终端汇报 ──
    print()
    print("=" * 70)
    print("✅ 模拟完成")
    print("=" * 70)
    print(f"📄 CSV: {csv_path.relative_to(BASE_DIR)}")
    print(f"📄 MD : {md_path.relative_to(BASE_DIR)}")
    print()
    print("─ 决策分布 ─")
    for k, v in summary["decision_counts"].items():
        pct = v / summary["total"] * 100
        print(f"  {k:12s}  {v:>3d}  ({pct:5.1f}%)")
    print()
    print("─ 按模式拆分 ─")
    for mode, st in summary["per_mode"].items():
        print(f"  {mode:12s}  通过率 {st['pass_rate']*100:5.1f}%  "
              f"(保留 {st['pass']} / 过滤 {st['filter']} / "
              f"缺失 {st['missing']} / 不可用 {st['unavailable']})")
    print()
    print("─ 反事实（通过 vs 过滤 的 T+1 最高均值）─")
    cf = summary["counterfactual"]
    def _f(v): return "—" if v is None else f"{v*100:+.2f}%"
    print(f"  通过票  n={cf['kept']['n']:>3d}  T+1 最高均值 = {_f(cf['kept']['avg_t1_max_return'])}")
    print(f"  过滤票  n={cf['filtered']['n']:>3d}  T+1 最高均值 = {_f(cf['filtered']['avg_t1_max_return'])}")
    print()
    print("⚠️ 提醒：本报告只是模拟，不影响今日推荐、不影响 9:36 买入、不写 trade_review.csv。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
