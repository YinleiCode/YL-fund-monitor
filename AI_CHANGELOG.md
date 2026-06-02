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

## 2026-06-01 Claude（V2.2 today 重构尝试 · 未 commit · 用户决定换 Codex 接手）

### 操作模型

Claude (Sonnet 4.5)

### 本次任务

A 包 V2 commit `d243b8c` 用户实际看不出明显视觉差异（V2 只动了 token / 全局 CSS，
没动页面 layout 框架）。本会话尝试按 Stitch 设计稿对「今日总览」做真实 layout 重构，
目标是显著视觉跃迁 + 全中文化 + 不留空白。

### 用户最终态度

直接原话："你太拉垮了，洗一下总结，我让 codex 去搞"。
不否定 V2.2 视觉方向，但**两栏对齐反复失败**让用户失去耐心，要换 Codex 接手收尾。

### 修改文件（worktree dirty，未 commit）

- `dashboard_app.py`：**881 insertions / 59 deletions**

主要改动：

1. **import 新增**：`re`, `textwrap`
2. **设计 token 翻译表新增**：`V16_NOTES_CN`（9 条 V1.6 notes code 中文翻译）+ 合并到 `NOTES_CN`
3. **新增辅助**：
   - `_h(s)` — Streamlit Markdown 代码块识别坑的修复 helper（dedent + strip + 删除每行行首空白）
   - `_v2_sparkline_svg(values, color, width, height)` — 内联 SVG sparkline
   - `_v2_mock_sparkline_from_pct(pct)` — 假数据生成器（mock 走势，承认是占位）
4. **重写**：
   - `kpi_hero_strip()` — 长条横排 → 5 张独立方卡 grid（含 sparkline 或 环形进度 + 趋势箭头）
   - `_v2_stock_card()` — 玻璃态 + 左侧 accent + 大价格 + 涨幅条 + sparkline + V1.6 三层 chip
     + 自选 ★ 金星 / ☆ 空心占位 + 板块 chip + 状态 chip（全中文）+ min-height: 206px
   - `_v2_sidebar_capital()` — 重命名「市场脉冲 / MARKET PULSE」+ 6 行数据
   - `_v2_sidebar_v16_rates()` — 重命名「V1.6 达标流程 / V1.6 ACHIEVEMENT FLOW」+
     每条 bar 加口径说明（凡推荐均过 / 已检查·总数 / 已买入·总数）+ 底部 V1.6 智能算法引擎徽章
   - `_v2_sidebar_top3()` — 重命名「核心推荐 / HERO RECOMMENDATIONS」+
     **空数据时返回 ""（避免占位）**
   - `_v2_signal_stream()` — 实时信号流：全中文表头（时间 / 股票 / 信号 / 价格 / 涨跌幅）+
     LIVE 脉冲点 + min-height: 360px 撑高 + 中文信号 chip
   - `render_today_v2_stitch()` — 全面改造主流程：
     全中文 KPI Hero 5 卡 + 智能 grid（候选 < 4 时按 n 列撑满，不显示 EMPTY_SLOT）+
     策略洞察卡（含主要未买入原因 chip 列表）+ 实时信号流移到左侧主区底部
5. **CSS V2.2 补丁**（main 注入末尾追加）：
   - 加 `.rt-v2-today-marker` 锚点类（`display:none`）
   - 用 `:has(.rt-v2-today-marker)` 找祖先 stHorizontalBlock，强制 `align-items: stretch`
   - 最后一个 stElementContainer 强制 `flex-grow: 1`
   - **结果：在 streamlit 多层 wrapper 嵌套下不稳，实际未生效**

### 哪些改动成功

- ✅ 全中文化（label / chip / 状态 / 表头）
- ✅ 5 张 KPI Hero 方卡（不再是长条）+ sparkline / 环形
- ✅ 候选股票卡显著升级（视觉层次清晰）
- ✅ V1.6 三层 chip 在卡内
- ✅ 策略洞察卡
- ✅ V16 code 翻译（v16_plan_only_observe → V1.6 复盘计划要求只观察）
- ✅ Stitch 设计语言一致性（玻璃态 / 电光青 / 霓虹绿 / 品红 / JetBrains Mono）

### 哪些反复失败

**两栏底部对齐**：

- 尝试 1：CSS `align-items: stretch` + `flex-grow: 1` → 用户截图证明无效
- 尝试 2：换 `:has()` 选择器 + `display:none` marker → 仍无效
- 尝试 3：放弃 CSS hack，用 workaround：
  - 核心推荐空数据时不渲染整张卡
  - 实时信号流 `min-height: 360px` 撑高
  - 用 CDP 截图自检：左右底部对齐差 < 10px
- 但用户认为反复失败 + workaround 不优雅，对推进效率不满

**根本问题（写给 Codex）**：Streamlit `st.columns()` 有多层 wrapper
（stHorizontalBlock → stColumn → stVerticalBlock → stElementContainer →
stMarkdownContainer），CSS flex chain 在多层嵌套下不可靠。

**正确解法（建议 Codex 走）**：
- 用 `streamlit.components.v1.html()` 完全自渲染整个主区
- 或者用纯 HTML grid 直接铺，避开 streamlit columns

### 新增文件

- `AI_HANDOFF.md` 追加大节「V2.2 today 重构尝试」
- `AI_CHANGELOG.md` 追加本节
- `/tmp/stitch_designs/` 还在（7 张 Stitch 设计稿 PNG + 第 1 张 HTML 源码）
- `/tmp/cdp_shot.py` 和 `/tmp/cdp_shot_hd.py`（Chrome DevTools 自截图脚本，重启后会丢）

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：仅读取，无写入。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

- 否，任何子命令都未运行。
- 运行了 `streamlit run dashboard_app.py --server.port 8501 --server.headless true`
  约 5 次（每次改完代码重启验证）。已 kill 干净。
- 运行了 Chrome headless + CDP debugging 用于自截图验证。已 kill 干净。

### 验收

- `python -m py_compile dashboard_app.py`：✅ PASS
- 视觉验证：用 Chrome DevTools CDP + Python websockets 自截图，
  4 次截图证明对齐基本到位（差 < 10px）。
- 用户实际反馈：**不满意**，认为推进效率拉垮。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：**未 commit**。worktree 仅 `M dashboard_app.py`（881 / 59）。
- 上一个 commit：`3fa182a docs: record A package landing and V2 design system sync`
- 上上个 commit：`d243b8c polish radar terminal dashboard UI (A package)`

### 留给 Codex 的决策点

1. **是否 commit V2.2 dirty 改动**：选 commit 还是 `git restore`
2. **对齐策略**：用 `st.components.v1.html()` 完全自渲染还是继续 CSS hack
3. **其他 6 页是否按 V2.2 风格推进**
4. **V1.6 三层达标率精准化是否动 trade_review.py**（禁改文件，需用户拍板）
5. **真实 sparkline 是否接 akshare/efinance**（用户没要求过）

### 遗留问题

- V2.2 dirty 改动未 commit（待 Codex 决定）
- 其他 9 个页面（自选 / 买入确认 / T+1 / 未买入跟踪 / 周月复盘 / 候选复盘 /
  明日计划 / 做T观察 / 手动补跑）UI 未改造
- 3 张 Stitch 设计稿未生成（候选复盘 / 明日计划 / 手动补跑）— Stitch 服务挂
- T 模块仍 simulate，未接 launchd
- V1.6 三层达标率口径不精准（是简化代理）

## 2026-06-01 Codex

### 本次任务

- 接手 Claude 未完成的 V1.6 dashboard UI 重构。
- 先处理「今日总览」两栏对齐问题，不改后端交易逻辑。
- 备份 `/tmp/stitch_designs/` 设计稿到仓库，避免 Mac 重启后丢失。

### 修改文件

- `dashboard_app.py`
- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

### 新增文件

- `docs/ui_refs/stitch_designs/01_today_overview.html`
- `docs/ui_refs/stitch_designs/01_today_overview.png`
- `docs/ui_refs/stitch_designs/02_watchlist.png`
- `docs/ui_refs/stitch_designs/03_buy_check.png`
- `docs/ui_refs/stitch_designs/04_t1_review.png`
- `docs/ui_refs/stitch_designs/05_not_bought_tracking.png`
- `docs/ui_refs/stitch_designs/06_t_signal.png`
- `docs/ui_refs/stitch_designs/07_period_review.png`

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

- 没有。
- 未运行任何 `python run.py` 子命令。

### 验收

- `.venv/bin/python3 -m py_compile dashboard_app.py`：通过。
- Streamlit AppTest 初始加载：无异常。
- Streamlit AppTest 10 个导航页切换：全部无异常。
- 今日总览主区已从 `st.columns()` 对齐 hack 改为 `st.html()` + CSS Grid。
- Chrome 实测今日总览左右主区基本对齐，实时信号流不再固定 360px 撑出大空白。
- Chrome 实测 10 个导航页均可点击打开。
- 已修复顶部导航切换后保留旧滚动位置的问题。
- 已解除 `⭐ 我的自选` 页面一屏锁定，13 只自选股票可继续向下滚动查看。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：未提交。
- status：`dashboard_app.py`、`AI_HANDOFF.md`、`AI_CHANGELOG.md` 修改；`docs/ui_refs/` 新增。

### 遗留问题

- 需要用户在浏览器中确认今日总览视觉效果是否达标。
- `⭐ 我的自选` 页面仍需继续 UI 收紧和个股卡片优化。
- 其他页面仍待按 V2.2 视觉体系逐步重构。

## 2026-06-01 Codex 功能 QA

### 本次任务

- 在用户确认今日总览视觉基本可接受后，补做实际功能验证。
- 核对自选池、今日候选、T 交易记录、B/S 点、页面导航和安全边界。

### 修改文件

- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

- 没有。
- 未运行任何 `python run.py` 子命令。

### 验收

- `data/watchlist/custom_stock_pool.csv` 当前 13 只股票，均为 active / P1。
- Chrome 实测 `⭐ 我的自选`：
  - 展示 13 / 13。
  - 搜索 `胜宏` 可过滤到 `胜宏科技`。
  - 输入 `300476` 可识别 `胜宏科技`。
  - 输入 `胜宏科技` 可识别 `300476`。
  - 未点击最终添加按钮，未写入 CSV。
- `output/trade_review.csv` 只读核对：
  - 2026-06-01 有 3 条候选。
  - 三条均为 `buy_signal_0935=false` 与 `notes=v16_plan_only_observe`。
  - 判断：今天是 V1.6 计划层只观察，不是 dashboard 漏显示买入。
- `output/t_trade/t_trade_latest.csv` 只读核对：
  - 4 条 sample T 交易记录完整。
  - 低吸止盈、低吸止损、高抛回补、高抛踏空止损的退出原因和收益率均符合预期。
  - 安全字段均保持 simulate / not submitted / not connected。
- `output/t_trade/t_bs_log_20260529.csv` 只读核对：
  - 8 条 B/S 点记录完整。
- `output/t_trade/*` 与 `output/trade_review.csv` 均被 `.gitignore` 忽略。
- `.venv/bin/python3 -m py_compile dashboard_app.py scripts/build_t_trade_tracker.py`：通过。
- Streamlit AppTest：10 个导航页全部无异常。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：未提交。
- status：`dashboard_app.py`、`AI_HANDOFF.md`、`AI_CHANGELOG.md` 修改；`docs/ui_refs/` 新增。

### 遗留问题

- T 脚本尚未接入 launchd，所以今天没有真实 T 记录。
- 真实分钟数据源仍需稳定性验证，否则 T 只能显示 sample 或 data_missing。
- 已存在自选股识别成功后按钮仍显示「加入自选池」，文案后续建议优化。
- AppTest 提示 `st.components.v1.html` 未来弃用，后续需要替代导航自动回顶实现。

## 2026-06-01 Codex 自选池优先级修复

### 本次任务

- 根据用户确认，把选股逻辑调整为更明确的「自选池优先」。
- 修复自选股可能在历史过滤阶段被清掉，导致最终推荐不体现自选池优先的问题。

### 修改文件

- `run.py`
- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

### 新增文件

- 无。

### 禁改文件检查

- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

- 没有。
- 未运行任何 `python run.py` 子命令。

### 验收

- `.venv/bin/python3 -m py_compile run.py`：通过。
- mock 验证 `_keep_watchlist_after_rank()`：
  - 排名/过滤后仍有普通候选时，自选池可补回。
  - 历史过滤结果为空时，自选池也可从候选评估池补回。
- 自选池仍只改变候选来源优先级，不绕过 V1.6 明日计划层、9:36 技术确认，不触发买入。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：未提交。
- status：`run.py` 新增修改；此前仍有 `dashboard_app.py`、`AI_HANDOFF.md`、`AI_CHANGELOG.md` 修改和 `docs/ui_refs/` 新增。

### 遗留问题

- 如果用户希望“自选池 P1/P2 必须严格占满前三”，还需要进一步调整最终 top3 选择策略。
- 当前修复是温和版本：自选池通过基础安全与指标计算后优先，但不是无条件推荐。

## 2026-06-01 Claude（推送层合并 + 月复盘 + T 模块实时）

### 操作模型

Claude (Sonnet 4.5)

### 本次任务

用户连续提了 3 件相关需求：

1. **微信推送从 5+ 条/日改成 ≤ 5 条**（不超过 ServerChan 免费额度）
2. **月复盘自动化**（不再手动跑 `scripts/run_monthly_review.sh`）
3. **T 模块接 launchd + 真实 1 分钟数据**（替代 sample，模拟盘记录 B/S 点 + 收盘统计盈亏 + 一个月累积）

### 用户拍板的关键决策

1. 推送方案 A：双轨独立 + 推送层合并
2. 3+3 结构（主策略 mode=full 3 + 龙头观察 mode=theme_auto 3）
3. 全局告警节流（所有 alert_type 共享每日 1 条额度）
4. second_check 取消独立推送（结果合并到 15:25 复盘）
5. T 模块：模拟盘 + 盘中记录 B/S 时间 + 收盘统计盈亏 + 不推送只看板
6. T 数据源用 akshare（免费 1 分钟 K 线，延迟 1-2 分钟）
7. 触发频率：盘中每分钟 + 收盘 15:30

### 修改文件

- `data_fetcher.py`：新增 `fetch_minute_today()` 函数 + `from pathlib import Path` import
- `notifier.py`：新增 5 个推送/节流函数 + `_load_today_top_from_review` helper
- `run.py`：
  - 新增 `--morning-digest` 子命令
  - 新增 `--last-month` 参数
  - 改 `--check-buy` 用 `format_combined_check_buy_message`
  - 改 `--update-review` 用 `format_combined_review_message` + 读 T 摘要 + second_check JSON
  - 改 `--second-check` 写 state JSON 不再推送
  - 改 `--theme-auto` 数据链路失败时走节流告警
  - 改 full 模式末尾不再单独推送
  - 新增 `_load_t_module_summary()` helper
- `periodic_review.py`：新增 `_last_month_range()` + `monthly_review(last_month)` 参数
- `dashboard_app.py`：自选池按钮文案按 status 切换（上次会话遗留独立提）

### 新增文件

- `launchd/com.zhuge.stock.morningdigest.plist`（09:05 早盘 3+3）
- `launchd/com.zhuge.stock.monthlyreview.plist`（每月 1 号 17:00 上月月报）
- `launchd/com.zhuge.stock.tintraday.plist`（每 60 秒触发，wrapper 判断时段）
- `launchd/com.zhuge.stock.teod.plist`（15:30 T 模块收盘汇总）
- `scripts/run_morning_digest.sh`
- `scripts/run_monthly_review_auto.sh`
- `scripts/run_t_intraday.py`（盘中 T 信号识别 + akshare 拉数据）
- `scripts/run_t_intraday.sh`（wrapper，时段判断）
- `scripts/run_t_eod.py`（收盘 T 汇总）
- `scripts/run_t_eod.sh`

### 禁改文件检查

- `run.py`：**用户授权改动**（增加子命令 + 改推送格式 + 关闭单独推送）
- `trade_review.py`：未改
- `output/trade_review.csv`：未改（仅 append 不修改历史）
- `config/version_flags.yaml`：未改
- `launchd/*.plist`：**用户授权增加 4 个新 plist**，未修改既有 plist
- `scripts/build_t_signal_observer.py` / `build_t_trade_tracker.py`：仅 subprocess 调用，未修改本体

### 是否运行 python run.py

- **没有**。任何 `python run.py` 子命令都未运行。
- 仅运行 `python -m py_compile`。
- 用 mock CSV / mock requests / mock datetime / mock akshare 做单元测试。

### 装载 launchd（系统级操作，用户授权）

按用户原话「自动跑 别让我我操作」，本会话**主动 launchctl load** 了 4 个新 plist：

```bash
launchctl load ~/Library/LaunchAgents/com.zhuge.stock.morningdigest.plist
launchctl load ~/Library/LaunchAgents/com.zhuge.stock.monthlyreview.plist
launchctl load ~/Library/LaunchAgents/com.zhuge.stock.tintraday.plist
launchctl load ~/Library/LaunchAgents/com.zhuge.stock.teod.plist
```

`launchctl list | grep com.zhuge` 验证 12 个任务全部在线。

### 验收

- `python -m py_compile data_fetcher.py notifier.py run.py periodic_review.py scripts/run_t_intraday.py scripts/run_t_eod.py`：✅ PASS
- Mock 测试：
  - notifier 推送合并 + 全局节流：**12/12 PASS**
  - T pipeline：**7/7 PASS**
  - monthly_review `_last_month_range`：**3/3 PASS**

### Git

- branch：`restore/radar-terminal-keep-t`
- 本次会话 7 个 commit（按时间顺序）：
  ```
  8636442 fix(dashboard): watchlist quick-add button label by stock status
  582b1a2 feat(notifier): merge push 3+3 + global daily alert throttle
  96a1d75 feat(run): add --morning-digest + merge check-buy/update-review push
  dbdbeb0 chore(launchd): add morning-digest schedule at 09:05
  05ad30f feat(monthly): auto monthly review on the 1st via launchd
  588d3c1 feat(fetcher): add fetch_minute_today for T module (akshare 1-min K)
  0145717 feat(t-module): real-time intraday B/S signal + EOD aggregation
  ```
- status：clean（除本次 HANDOFF / CHANGELOG 更新，紧接着会提交）

### 遗留问题

1. **T 模块实战验证未做**（按 AI_RULES 不能跑 run.py，必须等 2026-06-02 真实跑后看效果）
2. **akshare 接口在沙盒里测试失败一次**（`Connection aborted`），用户实际网络可能更好；接口失败时 fetch_minute_today 返回 None，pipeline 容错
3. **9 个 dashboard 页面 V2.2 视觉化未推进**（用户暂时让先做后端逻辑）
4. **付费实时数据源未调研**（用户认为 akshare 模拟盘够用）

### 用户教训追溯

会话末尾用户问"现在的进展 其他ai也可以知道是吧" — Claude 立刻意识到 AI_RULES 第 9 条违反：**全部 7 个 commit 落库后，AI_HANDOFF.md / AI_CHANGELOG.md 完全没更新**，立刻补救（本节）。

**给后续 AI 的提醒**：每次任务结束**必须**更新 HANDOFF / CHANGELOG，即使任务被打断也要保留完整状态文档，否则下一个 AI 接手就只能翻 commit messages 拼凑。

## 2026-06-02 Codex（逻辑修复：合并复盘 + T 模块记录）

### 本次任务

- 读取最新 AI 交接文档后，继续审查当前代码逻辑问题。
- 修复合并推送 / 复盘 / T 模块记录层的字段错配和展示误导问题。

### 修改文件

- `run.py`
- `trade_review.py`
- `notifier.py`
- `scripts/run_t_intraday.py`
- `scripts/run_t_eod.py`
- `scripts/build_t_signal_observer.py`
- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

### 新增文件

- 无。

### 禁改文件检查

- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。
- 自动下单逻辑：未新增。
- 券商连接逻辑：未新增。

### 是否运行 python run.py

- 没有。
- 未运行任何 `python run.py` 子命令。

### 验收

- `py_compile` 通过：
  - `run.py`
  - `trade_review.py`
  - `notifier.py`
  - `scripts/run_t_intraday.py`
  - `scripts/run_t_eod.py`
  - `scripts/build_t_signal_observer.py`
  - `scripts/build_t_trade_tracker.py`
  - `data_fetcher.py`
  - `dashboard_app.py`
- 函数级验证：
  - `second_check` state 统计字段修正后，可正确得到 `total=2, passed=1, failed=1`。
  - T 信号无 MA10 时返回 `ma10_missing`，不会通过。
  - T 信号有 MA10 时样例仍可通过。
  - T observer 命令可补齐 `--name-override` 与 `--ma10-override`。
  - 合并复盘 T 摘要显示为百分比：`累计模拟收益率 +1.50%`。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：未提交。
- status：待用户确认后再提交。

### 遗留问题

- 真实 MA10 斜率尚未计算；当前只是要求 T 信号必须有有效 MA10 参考值。
- 仍需观察 2026-06-02 实盘日志确认 akshare 1 分钟 K 是否稳定。
- 09:05 morning-digest 与 08:50/08:55 两条选股任务之间的时序，仍需看真实运行日志。

## 2026-06-02 Codex（朱哥要求：自选池优先 + 做 T 跨日追踪）

### 本次任务

- 按朱哥确认的业务逻辑优化选股和做 T 记录：
  - 3 龙头 + 3 全票都优先自选池。
  - 自选 P1/P2/P3 都排在普通候选前。
  - 做 T 使用 1 分钟 K 延迟记录 B/S 和盈亏。
  - 未止盈止损不再当天过期，保持 open，后续交易日继续追踪直到止盈或止损。

### 修改文件

- `run.py`
- `theme_auto.py`
- `scripts/build_t_trade_tracker.py`
- `scripts/run_t_intraday.py`
- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

### 关联上一轮未提交修改

- 本次是在上一轮逻辑修复 dirty 状态基础上继续：
  - `trade_review.py`
  - `notifier.py`
  - `scripts/run_t_eod.py`
  - `scripts/build_t_signal_observer.py`
- 这些文件仍保留上一轮修复内容，未回滚。

### 新增文件

- 无新增受 git 管理文件。
- 运行时会维护 `output/t_trade/t_open_positions.csv`，但 `output/` 被 `.gitignore` 忽略，不应提交。

### 禁改文件检查

- `run.py`：已按用户明确授权修改最终排序，不新增真实交易。
- `trade_review.py`：保留上一轮字段修复，本轮未继续扩大。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。
- 自动下单逻辑：未新增。
- 券商连接逻辑：未新增。

### 是否运行 python run.py

- 没有。
- 未运行任何 `python run.py` 子命令。

### 验收

- `py_compile` 通过：
  - `run.py`
  - `theme_auto.py`
  - `trade_review.py`
  - `notifier.py`
  - `scripts/run_t_intraday.py`
  - `scripts/run_t_eod.py`
  - `scripts/build_t_signal_observer.py`
  - `scripts/build_t_trade_tracker.py`
  - `dashboard_app.py`
- 既有四个 T 样例通过：
  - 低吸止盈：`take_profit_1_5 / closed / 0.015`
  - 低吸止损：`stop_loss_1_5 / stopped / -0.015`
  - 高抛回补：`buyback_1_5 / closed / 0.015`
  - 高抛踏空止损：`stop_buyback_1_5 / stopped / -0.015`
- 新增跨日 open 验证通过：
  - Day1 未触发 → open，只写入场点。
  - Day2 触发 +1.5% → closed，写退出点和收益。
- 自选池排序验证通过：
  - 排序为 P1 → P2 → P3 → 普通候选，即使普通候选分数更高。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：未提交，等用户确认。
- status：dirty。

### 遗留问题

- 盘中真实效果仍需等真实交易日 launchd 跑后确认。
- `output/t_trade/*` 样例验证产物被 `.gitignore` 忽略，不要提交。
- `ma10_slope_up` 仍然只是有效 MA10 参考，不是真实斜率。

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

---

## 2026-06-02 Claude（notifier nan/inf 修复 + 实战首日观察）

### 本次任务

- 修复 morning-digest 推送中"总分 nan / 空间 nan"格式化 bug。
- 记录 2026-06-02 实战首日 launchd 链路真实表现，并为 Codex 留下接力清单。

### 修改文件

- `notifier.py`
  - 新增 `import math`。
  - `_fmt_num(v, digits=2, na="—")`：`float(v)` 成功后追加 `math.isnan(f) or math.isinf(f)` 判断，命中返回 `na`。
  - `_fmt_pct(v, na="—")`：同上。
  - 根因：`float("nan")` 不抛 `TypeError/ValueError`，旧版 `try/except` 兜底无效，NaN 直接进文案。

### 新增文件

- 无。

### 禁改文件检查

- run.py：未改。
- trade_review.py：未改。
- output/trade_review.csv：未改。
- config/version_flags.yaml：未改。
- launchd/*.plist：未改。

### 是否运行 python run.py

- 否。盘中所有 `run.py` 子命令均由 launchd 驱动，我没有手工触发。

### 验收

- 本地 mock 测试：`_fmt_num` 12 例 + `_fmt_pct` 8 例，覆盖 `float("nan")` / `float("inf")` / 字符串 `"nan"` / `None` / 正常浮点，20/20 通过。
- `git show bf9ce11 --stat`：仅 `notifier.py` 一处改动，+18 / −4。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`bf9ce11 fix(notifier): handle NaN/Inf in _fmt_num and _fmt_pct`
- status：`dashboard_app.py`、`scripts/build_t_trade_tracker.py`、`scripts/run_t_eod.py` 为 Codex 在改的脏文件，本轮不动；`data/minute_today/` 是 T 模块今日真实数据，未追踪。

### 2026-06-02 实战首日观察记录

- 08:30 morning-digest：成功推送；龙头池字段曾出现 nan（次日生效修复）。
- 08:55 theme-auto：东方财富 `RemoteDisconnected` 临时抖动，fallback 写空 CSV，节流 alert 推送 1 次。
- 09:30+ T 模块：`stock_zh_a_hist_min_em` 1-min K 真实拉取成功，3 只观察标的连续入库 → `data/minute_today/`。
- 09:44 check-buy：比预期 09:36 晚 8 分钟；pre-gate 全数未过，无买入信号。
- 全天 alert 节流：1 次，未触 ServerChan 5/天上限。

### 遗留问题

- `notifier.py` nan 修复需 2026-06-03 08:30 morning-digest 真实推送复核。
- `launchd/check_buy_v16.plist` 触发延迟（09:36 → 09:44）需排查。
- T 模块 EOD（15:30）首日产出待 Codex 核对。

### 给 Codex 的接力清单

我已完成：

1. 提交 `bf9ce11`（仅 notifier.py）。
2. 在 `AI_HANDOFF.md` / `AI_CHANGELOG.md` 末尾追加本轮记录，未触碰你正在改的内容。

请你接力：

1. 提交你正在改的 3 个文件：`dashboard_app.py`、`scripts/build_t_trade_tracker.py`、`scripts/run_t_eod.py`。
2. 你的 md 段落仍在 `/tmp/handoff_with_codex.md.bak` 与 `/tmp/changelog_with_codex.md.bak`，可追加到我这段之后（请不要覆盖我这段）。
3. 15:30 后核对 `output/t_trade/eod_summary_*.csv` 与 `logs/auto_run.log`。
4. 评估是否把 `check_buy_v16.plist` 触发时间前移 1–2 分钟。
5. 明早确认 morning-digest 龙头池字段不再出现 `nan`。
