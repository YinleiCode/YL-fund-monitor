# AI_CHANGELOG.md

本文件记录 Claude、Codex、DeepSeek 等模型对项目的操作历史。每次任务结束必须追加记录。

## 2026-06-01 初始化

### 操作模型

Codex

### 本次任务

建立 AI 协作交接系统，让不同模型接手时可以通过仓库文件了解当前项目真实状态、已完成事项、风险边界和下一步任务。

### 修改文件

- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`
- `AI_RULES.md`

### 新增文件

- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`
- `AI_RULES.md`

### 禁改文件检查

- `run.py`：本次任务未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

没有。

### 验收

- 文件已创建。
- 内容已写入。
- `git status --short` 已检查。
- `git diff --stat` 已检查。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`6cd4939 add AI handoff and project rules docs`。
- status：当前工作区已有前序未提交改动，本次只应提交 3 个 AI 交接文档。

### 遗留问题

后续每个模型任务结束都必须追加记录。

## 2026-06-01 Codex

### 本次任务

补充遗留改动处理方案，让后续 Claude / Codex / DeepSeek 接手时能明确当前 dirty worktree 的来源、拆分方式、验证路径和下一步计划。

### 修改文件

- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：本次任务未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

没有。

### 验收

- 已把当前遗留改动拆为 3 个处理包：
  - Dashboard / RADAR_TERMINAL UI 包；
  - 自选池优先 / theme_auto fallback 逻辑包；
  - 自选池数据包。
- 已写明每个包涉及文件、当前状态、建议验证方式和建议提交信息。
- 已更新 `AI_HANDOFF.md` 的最新 commit 和当前工作区说明。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：本条记录随下一次 AI handoff 文档提交落库，具体 hash 见 `git log` 最新记录。
- status：仍有前序未提交改动；本次只应提交 `AI_HANDOFF.md` 和 `AI_CHANGELOG.md`。

### 遗留问题

- 仍需按 3 个处理包分别验收并决定是否提交。
- `run.py` 和 `theme_auto.py` 的业务逻辑改动尚未真实主流程运行验证，禁止擅自运行 `python run.py`。
- dashboard UI 仍需用户最终视觉确认。

## 2026-06-01 Codex

### 本次任务

只读审查选股、买入确认、T+1 卖出/复盘、T 信号、T 交易记录和调度链路，判断当前代码逻辑是否存在风险或缺口。

### 修改文件

- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：本次任务只读审查，未改。
- `trade_review.py`：只读审查，未改。
- `output/trade_review.csv`：只读查看，未改。
- `config/version_flags.yaml`：只读查看，未改。
- `launchd/*.plist`：只读查看，未改。

### 是否运行 python run.py

没有。

### 验收

- `python -m py_compile run.py theme_auto.py trade_review.py scripts/build_t_signal_observer.py scripts/build_t_trade_tracker.py` 通过。
- 确认未发现自动下单或券商连接逻辑。
- 确认 T 模块仍是 simulate。
- 确认 2026-06-01 没有 T 记录的主要原因是 T 脚本未接入 launchd，且尚未接真实 1 分钟数据源。
- 发现 `check_buy()` 实时行情失败时不写回失败状态，容易导致 dashboard 9:36 N/A。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：未提交。
- status：仍有前序未提交改动；本次新增交接记录未提交。

### 遗留问题

- 优先修 `trade_review.check_buy()` 实时行情缺失/价格无效写回。
- 设计 T 信号和 T 交易 tracker 的真实分钟数据输入与 launchd 调度。
- 决定自选池 priority=1 是否允许硬提到前三，还是只做优先观察。

## 2026-06-01 Codex

### 本次任务

P1 修复：`trade_review.check_buy()` 在实时行情缺失/价格无效/开盘涨幅无法计算时，写回失败状态到 `trade_review.csv`，dashboard 不再把这些情况显示成「尚未运行 / N/A」，改为显示具体失败原因（实时行情缺失 / 实时价格无效）。

### 修改文件

- `trade_review.py`
  - 表头新增 `realtime_data_status`、`fail_reason` 两列。
  - 新增 `_append_note()` 辅助函数（分号拼接 + 去重）。
  - `check_buy()` 两个失败分支补写 csv 行：`buy_signal_0935=false`、`realtime_data_status=missing/invalid`、`fail_reason=realtime_data_missing/realtime_price_invalid`、`notes` 追加描述，并清空 `buy_price/adjusted_buy_price/stop_price`。失败分支补 `updated += 1`。
  - 价格有效性检查改为 `math.isfinite + > 0`，更严格。
  - 成功通过分支写 `realtime_data_status=ok` 并清空 `fail_reason`。
- `dashboard_app.py`
  - `HARD_DROP_REASONS` / `MAIN_REASON_PRIORITY` 新增 `realtime_data_missing` / `realtime_price_invalid` 中文映射。
  - `is_not_checked()`：当 `realtime_data_status` 或 `fail_reason` 非空时返回 False。
  - `_v16_mf_layer_html()`：根据 `realtime_data_status` 显示「9:36 实时行情缺失，未触发买入」或「9:36 实时价格无效，未触发买入」。
  - `row_status()`：`realtime_data_status ∈ {missing, invalid}` 时返回 `STATUS_NOBUY_WAIT`。
- `AI_HANDOFF.md`、`AI_CHANGELOG.md`：补充本轮修复记录。

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：本次任务未改（diff 中的 152 行是前序遗留改动）。
- `trade_review.py`：**本次修改**。理由：解决 P1 dashboard 9:36 N/A 无法区分失败原因。已说明影响链路、风险、验证方式；不引入真实交易；不改 csv 历史数据；仅扩展 schema 与写入失败状态。符合 AI_RULES 第 3 条「先说明再改」流程。
- `output/trade_review.csv`：未改历史数据。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

没有。

### 验收

- `python -m py_compile trade_review.py dashboard_app.py` 通过。
- Mock 验证三种情况（实时行情缺失 / 实时价格无效 / 开盘涨幅无法计算）写回字段均符合预期。
- Dashboard helper 验证：
  - `is_not_checked(missing) = False`、`is_not_checked(invalid) = False`、`is_not_checked(not_checked) = True`。
  - `_v16_mf_layer_html` 三种情况文本正确。
- 确认未引入自动下单、券商连接逻辑；T 模块字段未动。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：未提交。本轮 P1 改动嵌在 `dashboard_app.py` 3770 行大 diff 中，绝大部分是前序遗留 UI 改动；若要单独提交 P1 包，需要 `git add -p` 挑 hunk。
- status：工作区仍 dirty，含前序遗留改动 + 本轮 P1 修复 + 本轮文档更新。

### 遗留问题

- `row_status()` 在 missing/invalid 情况下返回 `STATUS_NOBUY_WAIT = "未买入｜T+1待跟踪"`，语义不太准（无买入则无 T+1）。卡片内详情面板已显示正确原因，但顶层标签建议后续新增 `STATUS_NOBUY_DATA_FAIL`。
- P1 修复 commit 拆分尚未执行。建议 `git add -p` 把 `trade_review.py` 全收 + `dashboard_app.py` 只挑 P1 相关 5 段 hunk + 两份 AI 文档，单独提交。

## 2026-06-01 Claude（B 包）

### 本次任务

提交 B 包：`run.py` 自选池优先进入候选评估池 + `theme_auto.py` 三级 fallback（EM 概念 → EM 行业 → THS 行业 → 磁盘缓存）+ 成分股 EM 概念→EM 行业 fallback + 全失败时自选池降级观察（确保不写正式 trade_review.csv）。

### 修改文件

- 无新增源码改动。本轮目的是用 monkeypatch 验证前序遗留的 `run.py` / `theme_auto.py` 改动，验收通过后提交。
- `AI_HANDOFF.md`：B 包标记为已提交，更新当前工作区、风险点、落地细节、验证清单。
- `AI_CHANGELOG.md`：追加本条。

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：**本次提交**。理由：
  - 为什么必须改：把自选池股票从「只是 priority 排序硬提到前」扩展到「在候选评估池入口就并入」+「排名截断后补回」，避免自选股被 `top_n` 完全挤掉；同时把 `theme_auto.degraded_watchlist` 接入 main()，避免不完整观察污染正式 `trade_review.csv`。
  - 影响链路：粗筛后候选池构造 + `rank_and_select` 两个阶段的截断补回 + theme_auto 结果写 trade_review.csv 的开关。
  - 风险：自选股理论上可能让弱票绕过 quick_filter 进入评估。
  - 缓解：`_merge_watchlist_candidates` 已加基础安全过滤（非 ST、非停牌、价格达标、非跌停、非一字涨停），且自选股仍要过历史过滤/打分/V1.6/9:36 全部安全门。
  - 验证不触发真实交易：T5b 测试确认 `trade_review.append_rows` 在 `degraded_watchlist=True` 时被 elif 分支跳过。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

没有。

### 验收

- `python -m py_compile run.py theme_auto.py` 通过。
- 18 个 monkeypatch 全部 PASS：
  - T1 (5)：自选池并入候选池含基础安全拦截、标记字段。
  - T2 (2)：排名截断后补回 + `_watchlist_kept_after_rank` 标记。
  - T3 (3) + T3b (1)：EM 概念失败 → EM 行业 fallback 工作；EM 概念成功时不过度调用 industry。
  - T4 (2)：EM 板块全失败 → THS 行业 fallback 工作。
  - T5a (4)：`degraded_watchlist` 触发条件 + `get_run_status()` 暴露 + run.py 含跳过分支与告警文案。
  - T5b (1)：**`trade_review.append_rows` 在 `elif degraded_watchlist:` 分支被跳过**（核心安全）。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：紧随 P1 commit `4fe0272` 之后。具体 hash 见 `git log`。
- status：dirty worktree 剩 A 包（`.streamlit/config.toml` + `dashboard_app.py` 前序 UI）和 C 包（`data/watchlist/custom_stock_pool.csv`）。

### 遗留问题

- A 包等待用户做 dashboard 视觉确认。
- C 包等待用户确认 13 只自选池是否就是要保留的最新版本。
- T 模块仍未接 launchd，未接真实 1 分钟数据源。
- 自选池 priority=1 硬提到前三的口径需要你最终拍板（保留还是放宽到「只优先观察」）。

## 后续记录模板

```markdown
## 日期 模型名

### 本次任务
-

### 修改文件
-

### 新增文件
-

### 禁改文件检查
- run.py：
- trade_review.py：
- output/trade_review.csv：
- config/version_flags.yaml：
- launchd/*.plist：

### 是否运行 python run.py
-

### 验收
-

### Git
- branch：
- commit：
- status：

### 遗留问题
-
```
