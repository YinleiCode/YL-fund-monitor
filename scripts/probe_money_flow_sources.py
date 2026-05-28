"""
scripts/probe_money_flow_sources.py
====================================
V1.5-alpha 备用资金源调研 — 只读探测，不接入主流程

调研目标：在 Eastmoney push2his 不稳定时，找一个稳定的备用资金源。

测试的源：
  1. AKShare → push2his.eastmoney.com (现用主源，不稳)
  2. AKShare → 同花顺 (10jqka) 系列 → ⭐ 重点
  3. AKShare → 直连 (raw_get) (主源的二进制底层)
  4. efinance / tushare / pytdx — 只检查是否可用，不联网

严格只读：
  - 不写 trade_review.csv
  - 不写 cache/（只读现有缓存）
  - 不调 run.py 任何子命令

用法：
  .venv/bin/python3 scripts/probe_money_flow_sources.py
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime

TEST_CODES = ["688322", "300502", "600000", "000001", "600519"]
SLEEP_BETWEEN = 0.5


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def safe_test(label: str, fn, *args, **kwargs):
    """统一封装：跑一次接口，捕获所有异常，返回 (ok, df_or_data, elapsed, err)。"""
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.time() - t0
        if result is None:
            return False, None, elapsed, "返回 None"
        if hasattr(result, "empty") and result.empty:
            return False, result, elapsed, "返回空 DataFrame"
        if isinstance(result, (list, dict)) and len(result) == 0:
            return False, result, elapsed, "返回空容器"
        return True, result, elapsed, None
    except Exception as e:
        elapsed = time.time() - t0
        return False, None, elapsed, f"{type(e).__name__}: {str(e)[:160]}"


# ─── 1. 包可用性检查 ───────────────────────────────────────────────────

def check_packages() -> dict:
    banner("0. 备选源包可用性")
    info = {}
    for name in ["akshare", "efinance", "tushare", "pytdx", "mootdx"]:
        try:
            m = __import__(name)
            ver = getattr(m, "__version__", "?")
            print(f"  ✓ {name:12s} {ver}")
            info[name] = ver
        except ImportError:
            print(f"  ✗ {name:12s} 未安装")
            info[name] = None
    return info


# ─── 2. AKShare 东方财富路径（push2his 主源 + rank 备选）──────────

def test_akshare_eastmoney(code: str) -> None:
    import akshare as ak

    market = "sh" if code.startswith(("60", "68", "90")) else "sz"

    print(f"\n  ── {code} ({market}) ──")

    # (A) stock_individual_fund_flow → push2his.eastmoney.com
    ok, df, t, err = safe_test(
        f"  [A] ak.stock_individual_fund_flow",
        ak.stock_individual_fund_flow, stock=code, market=market,
    )
    if ok:
        print(f"  [A] stock_individual_fund_flow              ✓ {t:.2f}s  共 {len(df)} 行")
        if hasattr(df, "columns"):
            print(f"      列名: {list(df.columns)}")
            print(f"      末 2 行:")
            for line in df.tail(2).to_string(index=False).splitlines():
                print(f"        {line}")
    else:
        print(f"  [A] stock_individual_fund_flow              ✗ {t:.2f}s  {err}")
    time.sleep(SLEEP_BETWEEN)


def test_akshare_em_rank() -> None:
    import akshare as ak
    print()
    # (B) stock_individual_fund_flow_rank → 全市场排名快照
    ok, df, t, err = safe_test(
        "stock_individual_fund_flow_rank",
        ak.stock_individual_fund_flow_rank, indicator="今日",
    )
    if ok:
        print(f"  [B] stock_individual_fund_flow_rank(今日)     ✓ {t:.2f}s  共 {len(df)} 行")
        print(f"      列名: {list(df.columns)[:8]}...")
        print(f"      前 3 行:")
        for line in df.head(3).to_string(index=False).splitlines():
            print(f"        {line[:160]}")
    else:
        print(f"  [B] stock_individual_fund_flow_rank(今日)     ✗ {t:.2f}s  {err}")

    time.sleep(SLEEP_BETWEEN)

    # (C) stock_main_fund_flow → 主力资金排名
    ok, df, t, err = safe_test(
        "stock_main_fund_flow",
        ak.stock_main_fund_flow, symbol="全部股票",
    )
    if ok:
        print(f"  [C] stock_main_fund_flow                     ✓ {t:.2f}s  共 {len(df)} 行")
        print(f"      列名: {list(df.columns)[:8]}...")
    else:
        print(f"  [C] stock_main_fund_flow                     ✗ {t:.2f}s  {err}")

    time.sleep(SLEEP_BETWEEN)

    # (D) stock_market_fund_flow → 大盘资金流
    ok, df, t, err = safe_test(
        "stock_market_fund_flow",
        ak.stock_market_fund_flow,
    )
    if ok:
        print(f"  [D] stock_market_fund_flow                   ✓ {t:.2f}s  共 {len(df)} 行")
        print(f"      列名: {list(df.columns)[:8]}...")
    else:
        print(f"  [D] stock_market_fund_flow                   ✗ {t:.2f}s  {err}")


# ─── 3. AKShare 同花顺路径（备用主源候选）────────────────────────

def test_akshare_ths_individual(code: str) -> None:
    """同花顺个股资金流 — 独立于 eastmoney"""
    import akshare as ak

    print(f"\n  ── {code} （同花顺）──")

    # stock_fund_flow_individual — 同花顺-个股资金流
    ok, df, t, err = safe_test(
        "stock_fund_flow_individual",
        ak.stock_fund_flow_individual, symbol="即时",
    )
    if ok:
        print(f"  [E] stock_fund_flow_individual(即时全市场)    ✓ {t:.2f}s  共 {len(df)} 行")
        print(f"      列名: {list(df.columns)}")
        # 看能否定位到目标股票
        for col_guess in ["代码", "股票代码", "code"]:
            if col_guess in df.columns:
                hit = df[df[col_guess].astype(str).str.zfill(6) == code]
                if not hit.empty:
                    print(f"      → {code} 在表里 ({len(hit)} 行):")
                    for line in hit.head(1).to_string(index=False).splitlines():
                        print(f"        {line[:200]}")
                else:
                    print(f"      → {code} 不在表里（可能因为今日交易未活跃或停牌）")
                break
        else:
            print(f"      列里找不到代码列，无法定位 {code}")
    else:
        print(f"  [E] stock_fund_flow_individual(即时)         ✗ {t:.2f}s  {err}")


def test_akshare_ths_ranking() -> None:
    """同花顺各种排名维度"""
    import akshare as ak

    print()
    # 同花顺也支持按时段：即时 / 3日排行 / 5日排行 / 10日排行 / 20日排行
    for symbol in ["即时", "3日排行", "5日排行", "10日排行"]:
        ok, df, t, err = safe_test(
            f"stock_fund_flow_individual(symbol={symbol})",
            ak.stock_fund_flow_individual, symbol=symbol,
        )
        if ok:
            print(f"  [F] stock_fund_flow_individual({symbol:7s})  ✓ {t:.2f}s  {len(df)} 行")
            print(f"      列名: {list(df.columns)}")
            print(f"      首行示例:")
            for line in df.head(1).to_string(index=False).splitlines():
                print(f"        {line[:200]}")
        else:
            print(f"  [F] stock_fund_flow_individual({symbol:7s})  ✗ {t:.2f}s  {err}")
        time.sleep(SLEEP_BETWEEN)


# ─── 4. AKShare 概念/板块（参考） ──────────────────────────────────

def test_akshare_concept_industry() -> None:
    import akshare as ak
    print()
    ok, df, t, err = safe_test(
        "stock_fund_flow_concept",
        ak.stock_fund_flow_concept, symbol="即时",
    )
    if ok:
        print(f"  [G] stock_fund_flow_concept(即时)            ✓ {t:.2f}s  {len(df)} 行")
        print(f"      列名: {list(df.columns)}")
    else:
        print(f"  [G] stock_fund_flow_concept(即时)            ✗ {t:.2f}s  {err}")

    time.sleep(SLEEP_BETWEEN)

    ok, df, t, err = safe_test(
        "stock_fund_flow_industry",
        ak.stock_fund_flow_industry, symbol="即时",
    )
    if ok:
        print(f"  [H] stock_fund_flow_industry(即时)           ✓ {t:.2f}s  {len(df)} 行")
        print(f"      列名: {list(df.columns)}")
    else:
        print(f"  [H] stock_fund_flow_industry(即时)           ✗ {t:.2f}s  {err}")


# ─── 5. 项目自带 _raw_get 直连 push2his（对照）────────────────

def test_raw_socket_push2his(code: str) -> None:
    """复用项目内 _raw_get，绕过 requests，看 push2his 当前是否可达"""
    import sys
    sys.path.insert(0, ".")
    from data_fetcher import _raw_get, _build_query

    market_prefix = 1 if code.startswith(("60", "68", "90")) else 0
    params = {
        "lmt": "0", "klt": "101",
        "secid": f"{market_prefix}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut":      "b2884a393a59ad64002292a3e90d46a5",
        "_":       int(time.time() * 1000),
    }
    path = "/api/qt/stock/fflow/daykline/get?" + _build_query(params)

    t0 = time.time()
    try:
        raw = _raw_get("push2his.eastmoney.com", path, timeout=15)
        elapsed = time.time() - t0
        if not raw:
            print(f"  [I] _raw_get push2his {code}                  ✗ {elapsed:.2f}s  空响应")
            return
        d = json.loads(raw)
        klines = (d.get("data") or {}).get("klines") or []
        if klines:
            print(f"  [I] _raw_get push2his {code}                  ✓ {elapsed:.2f}s  {len(klines)} 行")
        else:
            print(f"  [I] _raw_get push2his {code}                  ✗ {elapsed:.2f}s  klines 为空")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [I] _raw_get push2his {code}                  ✗ {elapsed:.2f}s  {type(e).__name__}")


# ─── main ─────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 78)
    print(f"  V1.5-alpha 备用资金源调研  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 78)

    pkgs = check_packages()

    if not pkgs.get("akshare"):
        print("\n✗ akshare 未安装，无法继续探测")
        return

    # 1. AKShare 东方财富主路径（每只股测一次）
    banner("1. AKShare 东方财富 → 个股资金流明细（现行主源，不稳）")
    for c in TEST_CODES:
        test_akshare_eastmoney(c)
        time.sleep(SLEEP_BETWEEN)

    # 2. AKShare 东方财富排名/大盘
    banner("2. AKShare 东方财富 → 排名 / 主力 / 大盘")
    test_akshare_em_rank()

    # 3. AKShare 同花顺路径 ⭐ 备用候选
    banner("3. AKShare 同花顺 → 个股资金流（备用主源候选）")
    # 用第一只股测，因为同花顺接口是全市场快照
    test_akshare_ths_individual(TEST_CODES[0])
    test_akshare_ths_ranking()

    # 4. AKShare 概念/板块
    banner("4. AKShare 同花顺 → 概念 / 行业资金流（参考）")
    test_akshare_concept_industry()

    # 5. 项目自带 _raw_get 直连（对照）
    banner("5. 项目内 _raw_get 直连 push2his（与 [A] 对比）")
    for c in TEST_CODES[:3]:
        test_raw_socket_push2his(c)
        time.sleep(0.3)

    # 6. 备选包的总结
    banner("6. 其它包总结")
    if pkgs.get("efinance"):
        print(f"  ✓ efinance 已装 ({pkgs['efinance']}) — 可立即测试")
    else:
        print(f"  · efinance 未装 — 安装命令：.venv/bin/pip install efinance")
        print(f"    风险评估：efinance 直接走 eastmoney 后端，与 push2his 可能共用基础设施，")
        print(f"             安装它**不一定解决稳定性问题**。先看 akshare 同花顺路径")

    if pkgs.get("tushare"):
        print(f"  ✓ tushare 已装 ({pkgs['tushare']})")
    else:
        print(f"  · tushare 未装 — 需付费 token + 积分门槛，本轮先不联网测")

    if pkgs.get("pytdx"):
        print(f"  ✓ pytdx 已装 ({pkgs['pytdx']})")
    else:
        print(f"  · pytdx 未装 — 通达信协议，只提供行情和K线，**不提供主力资金分流字段**")

    print()
    print("=" * 78)
    print("  探测完成。完全只读，未写任何文件。")
    print("=" * 78)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
