# AI_HANDOFF.md

本文件是朱哥短线雷达 V1.6 的 AI 协作交接文件。任何模型接手前，必须先阅读：

- `AI_RULES.md`
- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

## 当前项目状态

- 项目名称：朱哥短线雷达 V1.6
- 项目路径：`/Users/yinlei/Desktop/量化/stock_screener`
- 当前分支：`restore/radar-terminal-keep-t`
- 当前系统性质：本地量化观察系统，不自动下单，不接券商。
- 当前自选池数量：13 只。
- 当前自选池定位：优先进入观察/评估，不是只从自选池选，也不是强行推荐或强行买入。

## 最新 10 个 Commit

```text
6cd4939 add AI handoff and project rules docs
71a807a show simulated T trade records in dashboard
d8395b4 add simulated T trade tracker core
315156c fix _score_dist_60d penalizing breakout stocks
d46dd13 fix HTML injection in dashboard and add today hero section
e15d236 migrate data_cache from pickle to JSON to avoid RCE risk
c6580e8 prioritize custom stock pool candidates by tier
e1d0e1f add watchlist feature with quick-add and auto name resolution
b21a643 fix duplicate checkbox in T-signal page
c033102 hide T signal samples by default
```

## 当前工作区

当前工作区不是干净状态。已有未提交改动包括：

```text
M  .streamlit/config.toml
M  dashboard_app.py
M  data/watchlist/custom_stock_pool.csv
M  run.py
M  theme_auto.py
```

这些改动来自前序任务，主要涉及：

- RADAR_TERMINAL 暗黑终端 dashboard UI 恢复和整理；
- 我的自选页面 UI 优化；
- 自选池当前 13 只；
- 自选池优先进入候选评估池；
- theme_auto 数据源 fallback 增强。

后续模型不得误认为这些文件是本次交接文档任务产生的改动。

## 遗留改动处理方案

当前遗留改动应拆成 3 个独立处理包，不要混在一个提交里。

### A. Dashboard / RADAR_TERMINAL UI 包

涉及文件：

- `.streamlit/config.toml`
- `dashboard_app.py`

当前状态：

- 正在恢复和整理 RADAR_TERMINAL 顶部横向导航暗黑终端界面。
- 我的自选页面已做过 UI 优化，但仍需用户视觉确认。
- 该包理论上只应影响前端展示和 dashboard 页面交互。

建议下一步：

1. 运行 `python -m py_compile dashboard_app.py`。
2. 用 Streamlit AppTest 做 dashboard non-crash。
3. 手工看 `http://localhost:8501/` 或 `http://localhost:8502/`。
4. 如果确认只影响前端，再单独提交。

建议提交信息：

```text
polish radar terminal dashboard UI
```

### B. 自选池优先 / theme_auto fallback 逻辑包

涉及文件：

- `run.py`
- `theme_auto.py`

当前状态：

- `run.py` 已加入自选池优先进入候选评估池逻辑。
- 排名截断后会补回已通过前序过滤的自选股，避免被 `top_n` 挤掉。
- `theme_auto.py` 已加入 THS 行业汇总 fallback。
- `theme_auto.py` 成分股获取已从只试 EM 概念，增强为 EM 概念成分股 → EM 行业成分股 → 磁盘缓存 → 自选池观察降级。
- 自选池降级观察不应写入正式 `trade_review.csv`，也不应参与真实买入。

重要边界：

- 这是选股候选来源和数据源 fallback 逻辑，不是自动买入逻辑。
- 不允许运行 `python run.py` 或 `python run.py --theme-auto` 做验证，除非用户单独授权。
- 必须确认没有写 `output/trade_review.csv`。

建议下一步：

1. 运行 `python -m py_compile run.py theme_auto.py`。
2. 用 monkeypatch / 小样例验证自选池并入候选池。
3. 用 monkeypatch 验证 EM 概念失败时会走 EM 行业成分股。
4. 用 monkeypatch 验证 EM 板块失败时会走 THS 行业汇总。
5. 确认不触发 `trade_review.csv` 写入。
6. 验收通过后单独提交。

建议提交信息：

```text
prioritize watchlist candidates and harden theme fallbacks
```

### C. 自选池数据包

涉及文件：

- `data/watchlist/custom_stock_pool.csv`

当前状态：

- 当前自选池是 13 只。
- 用户已确认“现在 13 只”。

建议下一步：

1. 确认这 13 只是否就是用户要保留的当前自选池。
2. 如果是用户主动维护的数据，可以单独提交。
3. 如果只是本地临时数据，则不要提交，保留在工作区或让用户决定。

建议提交信息：

```text
update custom stock watchlist
```

## 推荐提交顺序

1. 先提交 `run.py` + `theme_auto.py`，因为这是业务逻辑修复，但必须先完成安全验证。
2. 再提交 `.streamlit/config.toml` + `dashboard_app.py`，因为这是前端视觉整理。
3. 最后单独决定是否提交 `data/watchlist/custom_stock_pool.csv`。

如果用户只想先稳定交接，不想立刻提交业务/UI改动，可以保持当前 dirty 状态，但所有模型必须按本节拆分处理。

## V1.6 状态

V1.6 当前包含三层：

- 复盘计划层；
- 资金条件层观察模式；
- 9:36 技术确认层。

当前主线已有：

- 数据不足 / 退潮市场只观察；
- 自选股票池 quick-add；
- 股票代码/名称自动识别；
- 自选池 priority 硬分层排序；
- T 信号观察；
- T 交易记录；
- B/S 点记录；
- 止盈止损；
- 盈亏记录；
- dashboard 做 T 展示。

## T 模块状态

T 模块当前仍然只是 simulate：

- `execution_mode=simulate`
- `can_execute_live=False`
- `order_status=not_submitted`
- `broker_status=not_connected`

T 模块不接券商，不自动下单，不写入 `output/trade_review.csv`。

## 已完成功能

- V1.6 计划层和只观察机制。
- 资金条件层观察模式。
- 9:36 技术确认层。
- 自选股票池 quick-add。
- 股票代码/名称自动识别。
- 自选池 priority 硬分层排序。
- 自选池优先进入候选评估池。
- T 信号观察。
- T 交易模拟记录。
- B/S 点记录。
- 止盈止损记录。
- 盈亏记录。
- dashboard 做 T 页面展示。
- T 样例默认隐藏，勾选后显示。
- dashboard HTML injection 修复。
- today hero section。
- `check_buy()` 实时行情失败状态写回（P1，2026-06-01）：`trade_review.csv` 新增 `realtime_data_status` 和 `fail_reason` 两列；行情缺失/价格无效时写回 `buy_signal_0935=false` 并标 `realtime_data_missing` / `realtime_price_invalid`；dashboard 不再显示「9:36 N/A」而是显示具体失败原因。

## 当前风险点

- 2026-06-01 没有 T 记录，因为 T 脚本还没有接入 launchd 定时任务。
- ~~9:36 数据出现 N/A，需要排查实时数据源。~~（2026-06-01 已修：`check_buy()` 失败状态已写回，dashboard 会区分「实时行情缺失/实时价格无效」与真正「尚未运行」）
- dashboard RADAR_TERMINAL 前端界面正在恢复整理。
- 自选池当前是“优先”，不是“只从自选池选”。
- theme_auto 的数据源 fallback 已在前序未提交改动中增强，但尚未通过真实主流程运行验证。
- 当前工作区已有未提交改动，后续提交必须拆清楚，不要混入无关文件。
- `row_status()` 在 `realtime_data_status ∈ {missing, invalid}` 时返回 `STATUS_NOBUY_WAIT = "未买入｜T+1待跟踪"`。卡片内 V1.6 详细面板会显示正确的失败原因，但顶层状态标签语义不准（无买入则无 T+1）。后续可考虑新增 `STATUS_NOBUY_DATA_FAIL`。

## 2026-06-01 代码逻辑审查补充

本轮只读审查了选股、9:36 买入确认、T+1 卖出/复盘、T 信号、T 交易记录和 launchd 调度。

确认正常：

- 未发现自动下单逻辑。
- 未发现券商连接逻辑。
- T 模块字段仍保持 `execution_mode=simulate`、`can_execute_live=False`、`order_status=not_submitted`、`broker_status=not_connected`。
- `trade_review.py` 的 T+1 卖出是模拟卖出记录，写 `simulated_sell_price` / `simulated_trade_return`，不是实盘卖出。
- `scripts/build_t_trade_tracker.py` 只写 `output/t_trade/*`，不写 `output/trade_review.csv`。

重点问题：

- ~~`trade_review.check_buy()` 在实时行情缺失或价格无效时，只把错误放进返回结果，不写回 `trade_review.csv`。这会导致 dashboard 继续显示 9:36 N/A，无法知道是“没跑”还是“数据源失败”。建议写入 `buy_signal_0935=false`、`notes=realtime_data_missing` 或 `realtime_price_invalid`。~~ **（2026-06-01 已修，见下方「P1 修复补充」）**
- T 模块还没有接入 launchd。当前 launchd 只有 pick / themeauto / checkbuy / secondcheck / update / summary，没有 `build_t_signal_observer.py` 和 `build_t_trade_tracker.py`，所以 2026-06-01 没有真实 T 记录是链路未调度，不代表当天没有 T 机会。
- T 信号观察脚本当前第一版需要 `--input-minute-csv` 和显式 `--codes`，还没有真实 1 分钟行情源接入。即使接 launchd，也需要先设计真实分钟数据输入。
- `build_t_trade_tracker.py` 如果没有后续分钟数据，会把通过的 T 信号写成 `data_missing`；这是安全的，但还不是完整实时跟踪。
- 自选池优先逻辑现在较强：`run.py` 会把自选股补进候选评估池，且 priority=1 在最终排序硬提到最前。需要确认这是否符合用户口径；如果只是“优先观察”，建议保留安全过滤和分数下限，避免弱票因自选池直接挤进前三。
- `theme_auto.py` 会把自选池股票加入主题观察池。若部分主题成分股成功、部分失败，自选池股票可能以 top_theme 参与正式 theme_auto 推荐，需要继续明确“自选池观察”是否应写入正式 `trade_review.csv`。
- `append_rows()` 是幂等追加，已有同日同代码同 mode 记录不会刷新 V1.6 plan 标签。因此如果 `tomorrow_plan_latest.csv` 后续被人工确认/更新，旧 `trade_review.csv` 行不会自动同步。
- 主买入/卖出目前没有独立事件流水表，只有 `trade_review.csv` 行字段记录 `buy_signal_0935`、`buy_price`、`simulated_sell_price` 等。T 模块有独立 B/S 点日志。

## 2026-06-01 P1 修复补充：check_buy 实时行情失败写回

落地范围：

- `trade_review.py`：
  - `COLUMNS` 表头新增 `realtime_data_status` 和 `fail_reason` 两列。
  - 新增 `_append_note()` 辅助函数，分号拼接 `notes` 且自动去重。
  - `check_buy()` 在两个失败分支都写回 csv 行：
    - `rt is None` → `buy_signal_0935=false`、`realtime_data_status=missing`、`fail_reason=realtime_data_missing`、`notes` 追加「9:36实时行情缺失」、清空 `buy_price/adjusted_buy_price/stop_price`。
    - 价格非 finite 或 ≤0 → `realtime_data_status=invalid`、`fail_reason=realtime_price_invalid`、同上清空买入相关字段。
  - 成功通过的分支会写 `realtime_data_status=ok` 并清空 `fail_reason`。
  - 两个失败分支都补了 `updated += 1`，保证写回会 flush 到 csv。
- `dashboard_app.py`：
  - `HARD_DROP_REASONS` / `MAIN_REASON_PRIORITY` 增加 `realtime_data_missing` / `realtime_price_invalid` 中文映射。
  - `is_not_checked()`：当 `realtime_data_status` 或 `fail_reason` 非空时返回 False，不再误判为「尚未运行」。
  - `_v16_mf_layer_html()`：根据 `realtime_data_status` 显示「9:36 实时行情缺失，未触发买入」或「9:36 实时价格无效，未触发买入」。
  - `row_status()`：当 `realtime_data_status ∈ {missing, invalid}` 时返回 `STATUS_NOBUY_WAIT`。

边界与安全：

- 未运行 `python run.py` 或任何子命令。
- 未修改 `output/trade_review.csv` 历史数据，只动 schema 与写入逻辑。
- 未引入自动下单、券商连接逻辑；T 模块字段未动。
- 修改了禁改文件 `trade_review.py`，理由是解决 P1 dashboard 9:36 N/A 无法区分失败原因的问题，符合 AI_RULES 第 3 条「先说明再改」流程。

验证：

- `python -m py_compile trade_review.py dashboard_app.py` 通过。
- Mock 验证：实时行情缺失、实时价格无效、开盘涨幅无法计算三种情况，写回字段均符合预期。
- Dashboard helper 验证：
  - `is_not_checked(missing)=False`、`is_not_checked(invalid)=False`、`is_not_checked(not_checked)=True`。
  - `_v16_mf_layer_html` 三种情况文本正确（「9:36 实时行情缺失」/「9:36 实时价格无效」/「9:36 技术确认尚未运行」）。

遗留尾巴：

- `row_status()` 在 missing/invalid 情况下返回 `STATUS_NOBUY_WAIT = "未买入｜T+1待跟踪"`，语义不太准。卡片内详情面板已显示正确原因，但顶层标签建议后续新增 `STATUS_NOBUY_DATA_FAIL` 类别。
- 本轮 P1 改动嵌在 `dashboard_app.py` 3770 行大 diff 里（绝大部分是前序遗留 UI 改动），若要单独提交 P1 包，需要 `git add -p` 挑 hunk。

## 下一步建议

1. 先按“遗留改动处理方案”把当前未提交改动拆成 3 个包分别验收。
2. 如果继续修 theme_auto，优先验证：
   - EM 概念板块；
   - EM 行业板块；
   - THS 行业汇总；
   - 成分股接口 fallback；
   - 自选池降级观察。
3. 如果继续修 T 模块，优先设计 launchd 定时任务，但必须保持 simulate。
4. ~~优先修 `trade_review.check_buy()` 的实时行情失败写回，解决 dashboard 9:36 N/A 无法区分失败原因的问题。~~ **（2026-06-01 已修，见「2026-06-01 P1 修复补充」节）**
5. 可选：新增 `STATUS_NOBUY_DATA_FAIL` 让 row_status 在实时行情失败时的顶层标签语义对齐。
6. 如果继续修 dashboard，优先只改 `dashboard_app.py` 和 `.streamlit/config.toml`。
7. 每次任务结束必须更新 `AI_HANDOFF.md` 和 `AI_CHANGELOG.md`。

## 禁止事项

详细规则见 `AI_RULES.md`。

核心禁止事项：

- 不要运行 `python run.py`。
- 不要运行 `python run.py --check-buy`。
- 不要运行 `python run.py --theme-auto`。
- 不要运行 `python run.py --update-review`。
- 不要运行 `python run.py --second-check`。
- 不要自动下单。
- 不要接券商。
- 不要修改 `output/trade_review.csv` 历史记录。
- 不要随意修改 `run.py`、`trade_review.py`、`config/version_flags.yaml`、`launchd/*.plist`。
