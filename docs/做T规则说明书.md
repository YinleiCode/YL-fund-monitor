# 做T（正T低吸）规则说明书

> 版本：2026-06-11
> 状态：实验模块 / 旁路观察
> 核心文件：`scripts/build_t_signal_observer.py` / `scripts/build_t_trade_tracker.py` / `config/strategies/t_positive.yaml`

---

## 一、模块边界

做 T 模块只做实验观察和模拟记录：

- 不接券商
- 不自动下单
- 不写入 `output/trade_review.csv`
- 不影响 9:36 正式买入规则
- 不影响主链路 -3% 止损规则
- 不影响正式模拟收益口径

输出只用于看板、复盘、T 信号追踪和后续人工判断。

---

## 二、买入触发规则

正 T 低吸信号必须全部满足，才输出 B 点信号（`rule_pass=True`）。

| 序号 | 规则 | 当前阈值 / 口径 |
|------|------|----------------|
| 1 | MA5 基础过滤 | 今日 MA5 ≥ 昨日 MA5 × 0.997 |
| 2 | 时间窗口 | 触发 K 必须在 09:33-10:15 |
| 3 | 触发 K 颜色 | 必须是绿 K，`close < open` |
| 4 | 急跌幅度 | 1/2/3 分钟窗口内 `max(high)` 到触发 K `close` 跌幅 ≥ 0.7% |
| 5 | VWAP 偏离 | 触发 K `close` ≤ 当日分时 VWAP × 0.987 |
| 6 | 倍量绿 | 触发 K 成交量 ≥ 前 1-3 根绿 K 中最小量 × 2.0 |
| 7 | 缩量确认 | 下一根 K 成交量 ≤ 触发 K 成交量 × 0.5 |
| 8 | 共振过滤 | 板块/指数跌幅 ≤ 0.4% 或 883404 情绪跌幅 ≤ 0.5%，满足其一 |

### 1. MA5 基础过滤

- 今日 MA5 ≥ 昨日 MA5 × `0.997`
- 向下不超过 0.3% 视为中性偏强。
- 明确走弱则整只股不触发正 T。

### 2. 时间窗口

- 触发 K 必须在 `09:33-10:15`。
- 旧的 6 月内全天扩展扫描已经取消。
- 急跌、VWAP、量能回看使用当日已发生的 1 分钟 K，不只看窗口内 K。这样 09:33 附近可以回看 09:30-09:32。

### 3. 急跌条件

对每一根触发 K，同时检查 1、2、3 分钟窗口：

- 窗口包含触发 K 自身。
- 计算：`trigger_close / max(window_high) - 1`
- 跌幅达到 `-0.7%` 或更深即通过。
- 如果多个窗口通过，记录跌幅最深的窗口。

### 4. VWAP 偏离

- VWAP 按当日 09:30 起累计成交额 / 累计成交股数计算。
- 触发 K 收盘价必须至少比分时 VWAP 低 `1.3%`。
- 公式：`trigger_close <= vwap * (1 - 0.013)`

### 5. 倍量绿

- 触发 K 必须是绿 K。
- 取触发 K 前最近 1-3 根绿 K。
- 以这些前置绿 K 里的最小成交量作为基准。
- 公式：`trigger_volume >= min(previous_green_volumes) * 2.0`

### 6. 缩量确认与 B 点

- 必须等待触发 K 的下一根 1 分钟 K。
- 下一根 K 成交量 ≤ 触发 K 成交量 × `0.5`，才算缩量确认通过。
- B 点入场价 = 缩量确认 K 的收盘价。
- 不再使用缩量确认 K 的最低价。

### 7. 共振过滤

共振窗口使用触发急跌时选出的 1-3 分钟窗口。

满足下面任意一条即可通过：

- 板块/指数窗口跌幅 ≤ `0.4%`
- 同花顺情绪指数 `883404` 窗口跌幅 ≤ `0.5%`

盘中脚本 `scripts/run_t_intraday.py` 和收盘脚本 `scripts/run_t_eod.py` 都会调用 `--resonance-check`，因此盘中和 EOD 做 T 输出口径一致。

---

## 三、卖出规则

### 1. 默认止盈

- 盈利达到 `+1.5%` 后机械止盈。
- 退出原因：`take_profit_1_5`
- 看板显示：默认止盈 1.5%

### 2. 止损

- 亏损达到 `-1.5%` 后机械止损。
- 退出原因：`stop_loss_1_5`

### 3. 延长持有

当前不自动延长持有。

`+2%~+3%` 只作为极强结构的人工观察区间。原因是“继续放量红 K、无明显顶背离、板块情绪仍友好”需要更可靠的结构判断，当前程序不假装自动判断。

配置中保持：

```yaml
extended_hold_enabled: false
```

---

## 四、当前配置

配置文件：`config/strategies/t_positive.yaml`

```yaml
rules:
  time_window_start: "09:33"
  time_window_end: "10:15"
  drop_pct_min: 0.007
  below_vwap_pct: 0.013
  vol_multiple_min: 2.0
  shrink_ratio_max: 0.5
  resonance_sector_drop_max: 0.004
  resonance_emotion_drop_max: 0.005
  entry_price_rule: "B点入场价 = 缩量确认K（下一根）收盘价"

sell_rules:
  take_profit_default_pct: 0.015
  stop_loss_pct: 0.015
  extended_hold_enabled: false
  take_profit_extended_low_pct: 0.02
  take_profit_extended_high_pct: 0.03
```

YAML 读取失败时，代码会使用默认兜底配置，不影响正式任务。

---

## 五、输出文件

| 文件 | 说明 |
|------|------|
| `output/t_signal/t_signal_<日期>.csv` | 当日 T 信号扫描结果 |
| `output/t_signal/t_signal_latest.csv` | 看板读取的最新 T 信号 |
| `output/diagnostics/t_signal_trace_<日期>.csv` | 每根 K 的逐条件诊断 |
| `output/t_trade/t_trade_<日期>.csv` | T 模拟交易记录 |
| `output/t_trade/t_bs_log_<日期>.csv` | B/S 点日志 |
| `output/t_trade/t_open_positions.csv` | 未完成 T 单 |
| `output/t_signal/backtest_<起止>.csv` | T 历史回测输出 |

---

## 六、运行方式

### 盘中自动观察

```bash
python3 scripts/run_t_intraday.py
```

说明：该脚本由 launchd 旁路任务调用，只做 T 信号观察和模拟记录，不运行正式 `run.py` 交易任务。

### 收盘补跑

```bash
python3 scripts/run_t_eod.py
```

### 本地 CSV 测试

```bash
python3 scripts/build_t_signal_observer.py \
  --report-date 20260611 \
  --codes 300433 \
  --input-minute-csv data/minute_today/20260611_300433.csv \
  --ma5-slope-override 300433:1 \
  --resonance-check
```

### 历史回测

```bash
python3 scripts/backtest_t_signal.py \
  --codes 300433,002456 \
  --start-date 20260401 \
  --end-date 20260610
```

回测默认按 `+1.5%` 机械止盈，`+3%` 只统计为触达观察，不作为默认卖出价。

---

## 七、看板位置

Dashboard 页面：`🧪 盘中低吸 / 做T`

页面会展示：

- 做 T 信号
- 为什么触发
- 为什么没触发
- 每条规则是否通过
- B/S 点记录
- 默认止盈价、止损价
- 数据模式和模拟边界
