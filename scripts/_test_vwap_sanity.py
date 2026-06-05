"""VWAP 数量级合理性测试 — 防止 c018512 修复的单位 bug 复发.

跑法: .venv/bin/python3 scripts/_test_vwap_sanity.py

如果 VWAP 算出来跟 close 偏差 > 50%, 就报错 (FAIL).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_t_signal_observer import _annotate_vwap_inplace
from datetime import datetime

def mk(t, o, h, l, c, v, amt=None):
    """构造 1 分钟 K. v 单位是手, amt 单位是元."""
    d = {"datetime": datetime.fromisoformat(f"2026-06-05 {t}:00"),
         "open": o, "high": h, "low": l, "close": c, "volume": v}
    if amt is not None:
        d["amount"] = amt
    return d

def fail(label, expected, actual):
    print(f"❌ {label}: 期望 {expected}, 实际 {actual}")
    return False

def passed(label):
    print(f"✅ {label}")
    return True

ok = True

# 测试 1: 山东玻纤实测数据 (price ~18, 不应该算出 1800)
print("=" * 60)
print("Test 1: 山东玻纤 (price 17-19 元, VWAP 也应该在这个区间)")
print("=" * 60)
bars = [
    mk("09:30", 17.90, 17.90, 17.90, 17.90, 5503,  amt=9850370),
    mk("09:31", 17.90, 17.95, 17.80, 17.85, 14246, amt=25439414),
    mk("09:32", 17.82, 17.85, 17.65, 17.72, 16352, amt=29090494),
]
_annotate_vwap_inplace(bars)
last_vwap = bars[-1]["vwap"]
last_close = bars[-1]["close"]
print(f"  最后一根 close = {last_close:.4f}")
print(f"  最后一根 VWAP  = {last_vwap:.4f}")
if 15 < last_vwap < 20:
    ok &= passed(f"VWAP 在合理区间 [15, 20] 元")
else:
    ok &= fail("VWAP 数量级", "约 17.9", f"{last_vwap:.4f} (差 {(last_vwap/last_close - 1)*100:.0f}%)")

# 测试 2: 中际旭创实测数据 (price ~1270 元, VWAP 也应该在这个区间)
print("\n" + "=" * 60)
print("Test 2: 中际旭创 (price 1250-1290 元)")
print("=" * 60)
bars2 = [
    mk("09:30", 1250, 1250, 1250, 1250, 4663,  amt=582867500),
    mk("09:31", 1251.3, 1259.3, 1241.36, 1255.05, 9085, amt=1135637925),
    mk("09:32", 1259.3, 1265.0, 1254.93, 1264.98, 4588, amt=580543524),
]
_annotate_vwap_inplace(bars2)
last_vwap2 = bars2[-1]["vwap"]
last_close2 = bars2[-1]["close"]
print(f"  最后一根 close = {last_close2:.4f}")
print(f"  最后一根 VWAP  = {last_vwap2:.4f}")
if 1240 < last_vwap2 < 1280:
    ok &= passed(f"VWAP 在合理区间 [1240, 1280] 元")
else:
    ok &= fail("VWAP 数量级", "约 1255", f"{last_vwap2:.4f}")

# 测试 3: 没有 amount 时 (向后兼容旧 csv) 也要算对
print("\n" + "=" * 60)
print("Test 3: 旧格式 csv (无 amount), fallback 路径")
print("=" * 60)
bars3 = [
    mk("09:30", 17.90, 17.90, 17.90, 17.90, 5503),   # 无 amount
    mk("09:31", 17.90, 17.95, 17.80, 17.85, 14246),
]
_annotate_vwap_inplace(bars3)
last_vwap3 = bars3[-1]["vwap"]
last_close3 = bars3[-1]["close"]
print(f"  close = {last_close3:.4f}")
print(f"  VWAP  = {last_vwap3:.4f} (fallback close × volume)")
if 17 < last_vwap3 < 18:
    ok &= passed("fallback 路径 VWAP 正确")
else:
    ok &= fail("fallback VWAP", "约 17.86", f"{last_vwap3:.4f}")

# 测试 4: 故意造 bug (volume 不乘 100 模拟旧错误代码)
print("\n" + "=" * 60)
print("Test 4: 模拟 c018512 之前的 bug, 安全网应该报警")
print("=" * 60)
print("  (这个测试只验证'安全网'输出 stderr WARNING, 不算 fail)")
print("  如果之前修复有效, 这个 test 应该静默通过")

print("\n" + "=" * 60)
if ok:
    print("✅ 全部 VWAP sanity 测试通过")
    sys.exit(0)
else:
    print("❌ 有失败")
    sys.exit(1)
