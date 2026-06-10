# 做T（正T/低吸高抛）规则说明书

> 版本：2026-06-10  
> 核心文件：`scripts/build_t_signal_observer.py` / `scripts/run_t_intraday.py`

---

## 一、规则总览

全部规则必须同时满足才输出 B 点信号（`rule_pass=True`）。

| 序号 | 规则 | 关键阈值 |
|------|------|---------|
| 1 | MA5 斜率向上或中性偏强 | MA5今日 ≥ MA5昨日 × 0.997 |
| 2 | 时间窗口 | 09:30~15:00 全天（午休跳过） |
| 3 | 触发K颜色 | 必须是绿K（close < open） |
| 4 | 急跌（两段同时满足） | 跌幅 ≥ 0.7% + 低于VWAP ≥ 1.3% |
| 5 | 倍量绿 | 触发K量 ≥ 前绿K最小量 × 2.0 |
| 条件4 | 共振过滤（满足其一） | 大盘跌幅 ≤ 0.4% 或 情绪指数跌幅 ≤ 0.5% |
| 6 | 缩量确认 | 下一根K量 ≤ 触发K量 × 0.5 |

---

## 二、规则详细说明

### 规则1 — MA5 斜率
- MA5今日 ≥ MA5昨日 × 0.997
- 向下幅度 ≤ 0.3% 视为**中性偏强**，仍通过
- 不满足 → 整只股跳过，不扫后续K线
- 每日开盘前计算一次，缓存到 `data/minute_today/_ma5_slope_<日期>.json`

### 规则2 — 时间窗口
- **月底前（≤ 2026-06-30）**：09:30 ~ 15:00 全天扫描，午休 11:30~13:00 跳过
- **2026-07-01 起**：恢复严格窗口 09:33 ~ 10:15
- 控制常量：`EXPANDED_WINDOW_UNTIL = "20260630"`

### 规则3 — 触发K颜色
- 触发K必须是绿K（`close < open`）
- 红K、平K（doji）不触发

### 规则4 — 急跌（两段同时满足）

**第1段 — 急跌幅度**
- 取触发K往前 1/2/3 根K（含触发K自身）构成时间窗口
- 窗口内 `max(high)` → 触发K `close` 跌幅 **≥ 0.7%**
- 取三个窗口中跌幅最大的那个
- 常量：`DROP_PCT_MIN = 0.007`

**第2段 — 均价线偏离**
- 触发K `close` ≤ 分时 VWAP × (1 - 1.3%)
- VWAP = 从09:30开盘累计成交额 / 累计成交股数（通达信/同花顺同口径）
- 常量：`BELOW_VWAP_PCT = 0.013`

### 规则5 — 倍量绿
- 触发K成交量 ≥ 前 1~3 根绿K中**最小那根**的 2.0 倍
- 比较基准是"最小那根"（只要超过其中一根的翻倍即满足）
- 常量：`VOL_MULTIPLE_MIN = 2.0`

### 条件4 — 共振过滤（满足其一即通过）
- **板块/大盘**：上证综指（沪市）或深证成指（深市）在触发窗口内跌幅 ≤ 0.4%
- **情绪指数**：同花顺情绪指数 883404 在触发窗口内跌幅 ≤ 0.5%
- 两个条件满足任意一个即通过（OR 逻辑）
- 启用方式：`run_t_intraday.py` 调用 observer 时自动传 `--resonance-check`
- 数据源：AKShare 实时指数分钟数据
- 常量：`RESONANCE_SECTOR_DROP_MAX = 0.004`，`RESONANCE_EMOTION_DROP_MAX = 0.005`

### 规则6 — 缩量确认
- 触发K的下一根K成交量 ≤ 触发K成交量 × 0.5
- 常量：`SHRINK_RATIO_MAX = 0.5`

---

## 三、B点入场

- **入场价 = 缩量确认K的最低价（low）**
- 止盈目标：+1.5%（优先）/ +3%（强势拿）
- 止损：-1.5%（严格执行）

---

## 四、运行方式

### 实盘（自动）
```bash
# launchd 每分钟调起，或手动执行
python3 scripts/run_t_intraday.py
```
流程：拉分钟数据 → 共振指数 → 信号检测 → tracker 记录

### 手动测试（本地CSV）
```bash
python3 scripts/build_t_signal_observer.py \
  --report-date 20260610 \
  --codes 300433 \
  --input-minute-csv data/minute_today/20260610_300433.csv \
  --ma5-override 300433:35.2 \
  --ma5-slope-override 300433:1 \
  --resonance-check
```

### 历史回测
```bash
python3 scripts/backtest_t_signal.py \
  --codes 300433,002456 \
  --start-date 20260101 \
  --end-date 20260630

# 不用共振过滤（看原始信号量）
python3 scripts/backtest_t_signal.py \
  --codes 300433 \
  --start-date 20260501 --end-date 20260630 \
  --no-resonance
```

---

## 五、输出文件

| 文件 | 说明 |
|------|------|
| `output/t_signal/t_signal_<日期>.csv` | 当日所有扫描记录（含未通过） |
| `output/t_signal/t_signal_latest.csv` | 最新一次运行结果（看板读取） |
| `output/t_trade/t_trade_<日期>.csv` | T 交易模拟记录（B/S点、盈亏） |
| `output/t_trade/t_open_positions.csv` | 当前持仓状态 |
| `output/t_signal/backtest_<起止>.csv` | 回测结果 |

---

## 六、关键常量速查

```python
# scripts/build_t_signal_observer.py
DROP_PCT_MIN          = 0.007   # 规则4第1段：急跌幅度阈值
BELOW_VWAP_PCT        = 0.013   # 规则4第2段：VWAP偏离阈值
VOL_MULTIPLE_MIN      = 2.0     # 规则5：倍量倍数
SHRINK_RATIO_MAX      = 0.5     # 规则6：缩量比上限
RESONANCE_SECTOR_DROP_MAX  = 0.004  # 条件4：大盘跌幅阈值
RESONANCE_EMOTION_DROP_MAX = 0.005  # 条件4：情绪指数跌幅阈值
EXPANDED_WINDOW_UNTIL = "20260630"  # 全天扫描截止日期
```
