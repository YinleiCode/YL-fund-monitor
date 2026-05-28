"""
scripts/probe_money_flow.py
============================
V1.5-alpha 资金流探测脚本（只读 / 一次性）

本脚本目的：
  - 验证 akshare 资金流接口能不能用
  - 输出字段名 / 单位 / 样本值
  - 检查"近3日主力净流入"规则是否可实现
  - 检查稳定性（异常 / 空数据 / 字段变动）

严格只读：
  - 不读 trade_review.csv 之外的项目数据
  - 不写任何文件
  - 不调用 run.py 任何子命令
  - 不接入策略
  - 不依赖项目内的 trade_review / scorer / filters 等模块

用法（手动跑）：
    .venv/bin/python3 scripts/probe_money_flow.py
"""
from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# 受测股票：用户指定 + 最近 trade_review.csv 中的推荐
TEST_CODES_FIXED = ["688322", "300502"]   # 用户明确要求
SAMPLE_FROM_CSV  = 4                       # 再从 CSV 多采样 4 只

# 控制查询数量，避免连击 akshare
SLEEP_BETWEEN_CALLS = 0.8


def banner(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def sample_codes_from_csv() -> list[str]:
    """只读 trade_review.csv，挑最近的非重复推荐票。"""
    try:
        import pandas as pd
        p = Path(__file__).parent.parent / "output" / "trade_review.csv"
        if not p.exists():
            return []
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
        # 取最近的 SAMPLE_FROM_CSV 个不同 stock_code
        recent = df.sort_values("report_date", ascending=False)
        codes = []
        for c in recent["stock_code"]:
            c = str(c).zfill(6)
            if c not in codes:
                codes.append(c)
            if len(codes) >= SAMPLE_FROM_CSV:
                break
        return codes
    except Exception as e:
        print(f"  ⚠️ CSV 采样失败（不影响后续）: {e}")
        return []


def probe_individual_fund_flow(code: str) -> None:
    """
    akshare.stock_individual_fund_flow(stock=, market=)
    单只股票的"近 N 日资金流"明细。一般含：
      日期 / 收盘价 / 涨跌幅 / 主力净流入-净额 / 主力净流入-净占比 /
      超大单净流入-净额 / 超大单净流入-净占比 /
      大单 / 中单 / 小单 ...
    """
    import akshare as ak
    market = "sh" if code.startswith(("60", "68", "11", "5")) else "sz"

    print(f"\n  ── 接口：ak.stock_individual_fund_flow(stock='{code}', market='{market}') ──")
    try:
        t0 = time.time()
        df = ak.stock_individual_fund_flow(stock=code, market=market)
        elapsed = time.time() - t0
        print(f"     耗时: {elapsed:.2f}s  返回 {len(df) if df is not None else 'None'} 行")

        if df is None or df.empty:
            print(f"     ⚠️ 空数据")
            return

        print(f"     列名: {list(df.columns)}")
        print(f"     dtypes:")
        for c, t in df.dtypes.items():
            print(f"       {c:30s} {t}")
        print()
        print(f"     最近 5 行预览:")
        # 显示 tail (假定按日期升序)
        print(df.tail(5).to_string(index=False))
        print()
        # 取末 3 行做主力净流入检查
        sub = df.tail(3)
        cand_cols = [c for c in df.columns if "主力" in str(c) and "净流入" in str(c)]
        print(f"     检测到「主力净流入」字段: {cand_cols}")
        if cand_cols:
            for c in cand_cols:
                vals = sub[c].tolist()
                print(f"       {c}: {vals}")
    except Exception as e:
        print(f"     ❌ 异常: {type(e).__name__}: {e}")


def probe_individual_fund_flow_rank(top_n: int = 3) -> dict:
    """
    akshare.stock_individual_fund_flow_rank(indicator="今日"|"3日"|"5日"|"10日")
    全市场资金流排行快照（指定股票不行，全表后筛）。
    返回 dict {indicator: df_or_None}，给后续比对用。
    """
    import akshare as ak
    out = {}
    for indicator in ("今日", "3日", "5日"):
        print(f"\n  ── 接口：ak.stock_individual_fund_flow_rank(indicator='{indicator}') ──")
        try:
            t0 = time.time()
            df = ak.stock_individual_fund_flow_rank(indicator=indicator)
            elapsed = time.time() - t0
            print(f"     耗时: {elapsed:.2f}s  返回 {len(df) if df is not None else 'None'} 行")
            if df is None or df.empty:
                print(f"     ⚠️ 空数据")
                out[indicator] = None
                continue
            print(f"     列名: {list(df.columns)}")
            print(f"     dtypes:")
            for c, t in df.dtypes.items():
                print(f"       {c:30s} {t}")
            print(f"     前 {top_n} 行预览:")
            print(df.head(top_n).to_string(index=False))
            out[indicator] = df
        except Exception as e:
            print(f"     ❌ 异常: {type(e).__name__}: {e}")
            out[indicator] = None
        time.sleep(SLEEP_BETWEEN_CALLS)
    return out


def probe_rank_lookup(rank_dfs: dict, codes: list[str]) -> None:
    """从 rank 全表里查目标股票当前资金流（只看一眼字段）。"""
    df_today = rank_dfs.get("今日")
    if df_today is None:
        print("  (今日 rank 数据缺失，跳过)")
        return
    # 找代码列
    code_col = None
    for c in df_today.columns:
        if "代码" in str(c) or "代号" in str(c).lower() or str(c).lower() == "code":
            code_col = c; break
    if not code_col:
        print(f"  ⚠️ rank df 未找到代码列。列名: {list(df_today.columns)}")
        return
    print(f"  代码列: {code_col}")
    for code in codes:
        hit = df_today[df_today[code_col].astype(str).str.zfill(6) == code]
        if hit.empty:
            print(f"    {code}: 不在今日排名中（停牌或未交易？）")
            continue
        print(f"    {code}:")
        # 只打印资金/主力相关字段
        for c in df_today.columns:
            cs = str(c)
            if "主力" in cs or "净流入" in cs or "净额" in cs or "净占比" in cs:
                v = hit.iloc[0][c]
                print(f"       {c:30s} = {v}")


def main():
    print("\n" + "=" * 70)
    print(f"  V1.5-alpha 资金流接口探测（只读，不写文件，不改策略）")
    print(f"  时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 70)

    # —— 0. 环境 ——
    banner("0. 环境")
    try:
        import akshare as ak
        print(f"  ✓ akshare {ak.__version__}")
    except Exception as e:
        print(f"  ✗ akshare 不可用: {e}")
        sys.exit(1)

    # —— 1. 采样股票列表 ——
    banner("1. 受测股票（用户指定 + 最近 CSV 采样）")
    csv_codes = sample_codes_from_csv()
    test_codes = list(dict.fromkeys(TEST_CODES_FIXED + csv_codes))  # 去重保序
    print(f"  共 {len(test_codes)} 只: {test_codes}")

    # —— 2. 个股资金流（单查接口）——
    banner("2. ak.stock_individual_fund_flow —— 单股近 N 日资金流明细")
    for c in test_codes:
        probe_individual_fund_flow(c)
        time.sleep(SLEEP_BETWEEN_CALLS)

    # —— 3. 全市场排名（快照接口）——
    banner("3. ak.stock_individual_fund_flow_rank —— 全市场资金流排名快照")
    rank_dfs = probe_individual_fund_flow_rank(top_n=3)

    # —— 4. 反查目标股票在 rank 中的资金流 ——
    banner("4. 目标股票在「今日」rank 中的资金流字段")
    probe_rank_lookup(rank_dfs, test_codes)

    # —— 5. 规则可行性分析 ——
    banner("5. 「近3日主力净流入」规则可行性判定")
    # 用 688322 单股流再查一次取 3 天
    print("  尝试用 ak.stock_individual_fund_flow 取 688322 末 3 行：")
    try:
        df = ak.stock_individual_fund_flow(stock="688322", market="sh")
        if df is None or df.empty:
            print("    ⚠️ 空")
        else:
            sub = df.tail(3)
            print(f"    末 3 行：")
            print(sub.to_string(index=False))
            main_cols = [c for c in sub.columns if "主力" in str(c) and "净流入-净额" in str(c)]
            if main_cols:
                col = main_cols[0]
                vals = sub[col].astype(float).tolist()
                total = sum(vals)
                print(f"\n    判定示例（仅展示，不写入）：")
                print(f"      字段 = {col!r}（推测单位：元）")
                print(f"      末3日主力净流入: {vals}")
                print(f"      累计 = {total:,.2f}")
                if total > 0:
                    print(f"      → 累计为正，'近3日资金健康' 规则可触发")
                else:
                    print(f"      → 累计为负，'近3日资金健康' 规则不触发")
            else:
                print(f"    ⚠️ 未找到「主力净流入-净额」字段，需重命名映射")
    except Exception as e:
        print(f"    ❌ {type(e).__name__}: {e}")

    banner("6. 8:50 盘前可用性预估（仅根据字段日期推断）")
    print("  说明：此探测在收盘后跑，看到的是 T 日完整数据。")
    print("        实际 8:50 跑时，akshare 一般只能取到 T-1（前一交易日）资金流。")
    print("        生产时需在程序内显式取 T-1 那行，不要假设有当日数据。")

    print()
    print("=" * 70)
    print("  探测完成。注意：本脚本未写入任何文件，未改任何策略。")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
