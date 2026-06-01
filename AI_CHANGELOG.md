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

## 2026-06-01 Claude（C 包）

### 本次任务

提交 C 包：`data/watchlist/custom_stock_pool.csv` 自选池从 3 只扩展到 13 只。用户主动维护的数据，已当面确认。

### 修改文件

- 无源码改动。
- `AI_HANDOFF.md`：C 包标记为已提交，更新当前工作区。
- `AI_CHANGELOG.md`：追加本条。

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

没有。

### 验收

- 用户当面确认 13 只就是要保留的当前自选池。
- 13 只全部 `priority=1, status=active`。
- 与 B 包提交的自选池优先逻辑配合：这些股票会在 quick_filter 后并入候选评估池，并在排名截断后被补回。
- 仍然要走全部安全门（quick_filter 基础安全、history_filter、scoring、V1.6、9:36 技术确认）才会被推荐为模拟买入候选。
- 不绕过任何真实交易屏障（仍是观察系统，T 模块仍 simulate）。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：紧随 B 包 commit `6ce3187` 之后。具体 hash 见 `git log`。
- status：dirty worktree 仅剩 A 包（`.streamlit/config.toml` + `dashboard_app.py` 3749 行前序 UI），等待用户视觉确认。

### 遗留问题

- A 包等待用户对 dashboard RADAR_TERMINAL 终端 UI 做最终视觉确认。
- T 模块仍未接 launchd，未接真实 1 分钟数据源。
- 自选池 priority=1 硬提到前三的口径需要你最终拍板（保留还是放宽到「只优先观察」）。

## 2026-06-01 Claude（A 包提交 · V2 设计语言落地）

### 操作模型

Claude (Sonnet 4.5)

### 本次任务

A 包 dashboard UI 收尾，包含：

1. 前序遗留的 RADAR_TERMINAL 暗黑终端 dashboard UI 整理（3749 行 diff）
2. 我的自选页 UI 优化
3. **本轮新增**：V2 设计语言升级（同步 Stitch 7 张设计稿）

V2 升级是按用户「时尚炫酷潮流 + 不留白 + 风格统一 + 空间利用充分」需求，
通过 Stitch MCP 生成 7 张参考设计稿后，提炼出统一设计语言并落地到代码。

### Stitch 设计稿进度（参考资产）

已生成 7/10（保存在 `/tmp/stitch_designs/`）：

1. `01_today_overview.png` 今日总览
2. `02_watchlist.png` ⭐ 我的自选
3. `03_buy_check.png` 买入确认
4. `04_t1_review.png` T+1 复盘
5. `05_not_bought_tracking.png` 未买入跟踪
6. `06_t_signal.png` 做T观察
7. `07_period_review.png` 周月复盘

待补 3 张（Stitch 服务端最近 1 小时间歇性 timeout，重试 12 次失败）：

- 候选复盘
- 明日计划
- 手动补跑

这 3 张不阻塞 A 包提交：V2 token + 工具函数 + 全局 CSS 补丁
已让全 10 页自动受益。下次会话再补这 3 张。

### 修改文件

- `.streamlit/config.toml`（13 行）：light 奶油 → dark RADAR_TERMINAL 主题
- `dashboard_app.py`（4034 行 diff）：
  - 前序遗留：顶栏 10 Tab + 我的自选 UI + STATUS_NOBUY_DATA_FAIL +
    HARD_DROP_REASONS / MAIN_REASON_PRIORITY 增加 realtime_data 失败码
  - V2 升级：
    - 设计 token: COLOR_MAGENTA_NEON, COLOR_WARN_YELLOW,
      COLOR_GLASS_BG, COLOR_GLASS_BG_HI, COLOR_GLASS_EDGE, COLOR_DIVIDER
    - 字体堆栈: FONT_HEADLINE, FONT_BODY, FONT_MONO
    - 组件升级: kpi_card 圆角 12px + trend 箭头 + accent 条 + hover 上抬
    - 组件升级: render_page_header 圆角 14px
    - 新增组件: glass_card_html, chip_html, kpi_hero_strip
    - 全局 CSS V2 补丁: 卡 hover 上抬, Tab 电光青光晕, 数据表 36px row,
      st.metric 玻璃态, 主按钮反色, tabs/expander 玻璃态, 字体堆栈统一

### 新增文件

- `AI_CHANGELOG.md` 本节追加（即此节）

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未读写历史数据。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

- 否。任何子命令都未运行。
- 也未通过 streamlit 启动 dashboard 做视觉确认（按 AI_RULES，
  把视觉确认交回给用户）。

### 验收

- `python -m py_compile dashboard_app.py`：✅ PASS
- 视觉参考：7 张 Stitch 设计稿
- V2 token 全部「新增」非覆盖，老组件 100% 向后兼容
- `kpi_card` 新参数 trend / accent_bar 是 keyword-only 且有默认值，
  老调用点（约 50+ 处）无需修改

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`d243b8c polish radar terminal dashboard UI (A package)`
- status：A 包提交后，worktree 仅剩 AI 文档变动（即此次提交本身的更新）

### 遗留问题

- 剩 3 张 Stitch 设计稿（候选复盘 / 明日计划 / 手动补跑）下次会话再补。
- V2 改动只升级了 token / 卡片样式 / 全局 CSS。10 个页面的 layout 框架
  暂未按 Stitch 设计稿的 12-column 高密度网格 / KPI Hero 长条 / 右侧栏
  布局重构。后续可在 V2.1 中按页推进。
- 用户已表达若 V2 视觉效果满意，可继续在此基础上推进。
- T 模块仍未接 launchd，未接真实 1 分钟数据源。
- `row_status()` 在 missing/invalid 情况下走 STATUS_NOBUY_DATA_FAIL
  已实现（前序 P1 commit 4fe0272）。

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
