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
71a807a show simulated T trade records in dashboard
d8395b4 add simulated T trade tracker core
315156c fix _score_dist_60d penalizing breakout stocks
d46dd13 fix HTML injection in dashboard and add today hero section
e15d236 migrate data_cache from pickle to JSON to avoid RCE risk
c6580e8 prioritize custom stock pool candidates by tier
e1d0e1f add watchlist feature with quick-add and auto name resolution
b21a643 fix duplicate checkbox in T-signal page
c033102 hide T signal samples by default
30c2f82 add fallback sources for index change
```

## 当前工作区

当前工作区不是干净状态。已有未提交改动包括：

```text
M  .streamlit/config.toml
MM dashboard_app.py
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

## 当前风险点

- 2026-06-01 没有 T 记录，因为 T 脚本还没有接入 launchd 定时任务。
- 9:36 数据出现 N/A，需要排查实时数据源。
- dashboard RADAR_TERMINAL 前端界面正在恢复整理。
- 自选池当前是“优先”，不是“只从自选池选”。
- theme_auto 的数据源 fallback 已在前序未提交改动中增强，但尚未通过真实主流程运行验证。
- 当前工作区已有未提交改动，后续提交必须拆清楚，不要混入无关文件。

## 下一步建议

1. 先确认当前未提交改动是否按任务拆分提交。
2. 如果继续修 theme_auto，优先验证：
   - EM 概念板块；
   - EM 行业板块；
   - THS 行业汇总；
   - 成分股接口 fallback；
   - 自选池降级观察。
3. 如果继续修 T 模块，优先设计 launchd 定时任务，但必须保持 simulate。
4. 如果继续修 dashboard，优先只改 `dashboard_app.py` 和 `.streamlit/config.toml`。
5. 每次任务结束必须更新 `AI_HANDOFF.md` 和 `AI_CHANGELOG.md`。

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

