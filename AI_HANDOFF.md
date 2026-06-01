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
d243b8c polish radar terminal dashboard UI (A package)   ← A 包 2026-06-01
d0d8462 handoff: add active session state for restart continuity
0cc5779 update custom stock watchlist to 13 names        ← C 包
6ce3187 prioritize watchlist candidates and harden ...   ← B 包
4fe0272 fix(check_buy): write back realtime data ...     ← P1
8ed7261 document handoff plan for pending work
6cd4939 add AI handoff and project rules docs
71a807a show simulated T trade records in dashboard
d8395b4 add simulated T trade tracker core
315156c fix _score_dist_60d penalizing breakout stocks
```

## 当前工作区

**2026-06-01：所有 V1.6 dirty 改动都已 commit 落库。worktree 应该是 clean（除非有新文档更新）。**

```text
P1   4fe0272 fix(check_buy): write back realtime data failure to dashboard
B    6ce3187 prioritize watchlist candidates and harden theme fallbacks
C    0cc5779 update custom stock watchlist to 13 names
A    d243b8c polish radar terminal dashboard UI (A package)  ← 本日完成
```

这些改动覆盖：

- RADAR_TERMINAL 暗黑终端 dashboard UI 恢复和整理（A 包前序部分）；
- 我的自选页面 UI 优化（A 包前序部分）；
- 自选池当前 13 只（C 包）；
- 自选池优先进入候选评估池（B 包）；
- theme_auto 数据源 fallback 增强（B 包）；
- check_buy 实时行情失败状态写回（P1）；
- **V2 设计语言落地**（A 包本日新增，按 Stitch 7 张设计稿）。

## 遗留改动处理方案

**2026-06-01：所有遗留改动（P1 / A / B / C）都已提交落库。本节保留历史记录方便追溯。**

### A. Dashboard / RADAR_TERMINAL UI 包 ✅ 已提交

涉及文件：

- `.streamlit/config.toml`
- `dashboard_app.py`

**状态：2026-06-01 已 commit `d243b8c`。**

落地内容：

前序遗留部分：

- RADAR_TERMINAL 顶部横向 10 Tab 暗黑终端界面。
- `render_shell_topbar`：RADAR_TERMINAL 品牌 + 脉冲信号灯 + 实时时钟 + SYS_ONLINE。
- 我的自选页 UI 整理：卡片网格 + 快速添加 + 优先级标签。
- `STATUS_NOBUY_DATA_FAIL` 新状态分类（配合 P1）。
- `HARD_DROP_REASONS` / `MAIN_REASON_PRIORITY` 加 `realtime_data_missing` /
  `realtime_price_invalid` 中文映射。
- `is_not_checked` / `row_status` 支持 `realtime_data_status` 区分。
- `_v16_mf_layer_html` 显示具体失败原因。

V2 设计语言升级（2026-06-01 Stitch 同步）：

- **设计 token**（全部「新增」非覆盖，向后兼容）：
  `COLOR_MAGENTA_NEON #FF3D8A`（品红霓虹 警告/亏损）
  `COLOR_WARN_YELLOW #FFB627`（黄色警示）
  `COLOR_GLASS_BG / COLOR_GLASS_BG_HI / COLOR_GLASS_EDGE`（玻璃态）
  `COLOR_DIVIDER`（分割线）
- **字体堆栈**：`FONT_HEADLINE`（Space Grotesk）/ `FONT_BODY`（Inter）
  / `FONT_MONO`（JetBrains Mono）
- **组件升级**：
  - `kpi_card` 圆角 2px → 12px + 趋势箭头 ▲▼ + 左侧 accent 条 + hover 上抬；
    新参数 `trend` / `accent_bar` 是 keyword-only 且有默认值，
    50+ 老调用点 100% 向后兼容。
  - `render_page_header` 圆角 2px → 14px。
- **新增组件函数**：
  - `glass_card_html()` 通用玻璃态容器
  - `chip_html()` 状态 chip（黑底 + 主题色描边 + monospace 大写）
  - `kpi_hero_strip()` Hero 长条横排 5-6 列 KPI（Stitch 设计稿同款）
- **全局 CSS V2 补丁**（main 注入末尾，**全 10 页自动收益**）：
  - 玻璃态卡 hover `translateY(-2px)` + 电光青光晕
  - Tab 选中电光青 outline + box-shadow + 文字发光
  - 数据表 36px row + hover 电光青 inset 左边线
  - `st.metric` V2 玻璃态 + 左侧 accent 条 + hover
  - 主按钮反色风格（透明底 + 青文字 → hover 青底黑字）
  - tabs/expander V2 玻璃态描边
  - 字体堆栈全局统一

历史建议（已完成）：

```text
polish radar terminal dashboard UI
```

#### A 包提交记录

- commit hash: `d243b8c`（在 D0d8462 handoff session state 之后）。
- 验证：`python -m py_compile dashboard_app.py` ✅ PASS。
- 视觉参考：7 张 Stitch 设计稿 `/tmp/stitch_designs/01-07*.png`：
  1. 今日总览（KPI Hero 5 卡 + 8 张股票卡 4×2 + 右侧栏 + LIVE_SIGNAL_STREAM）
  2. ⭐ 我的自选（13 张自选卡 4×4 + 分类环形/7日战绩/推荐）
  3. 买入确认（三列等宽 已确认绿/异常黄/不通过红 + KPI 6 + timeline）
  4. T+1 复盘（KPI 6 + 明细卡 2×3 + PNL 热力图/命中率/卖出原因）
  5. 未买入跟踪（KPI 5 + 18 行数据表 + 错过原因环形/TOP3）
  6. 做T观察（SIMULATE 警示 + KPI 6 + T 信号卡 + SIMULATION ONLY 状态）
  7. 周月复盘（KPI 6 大数字 + PNL 曲线 + 30 格热力图 + V1.6 三层归因）

#### A 包待补 Stitch 设计稿（3/10）

下次会话再补，**不阻塞 dashboard 落地**：

- 候选复盘（参考 Stitch 设计语言：候选股生命周期 3×3 timeline 卡片）
- 明日计划（参考：V1.6 三层分段全宽长卡）
- 手动补跑（参考：命令网格 3×2 + 实时执行日志区域）

Stitch 服务在 2026-06-01 后期 1 小时连续 timeout 12 次，
对这 3 个项目限流。下次会话需要时再 retry。

待补项目 IDs：

- `projects/16245954795165166812`（候选复盘）
- `projects/7856275440330438578`（明日计划）
- `projects/2572244624392293286`（手动补跑）
- `projects/12805597988387654895`（候选复盘 V2 备用）

设计系统 asset ID（所有 Stitch 项目共用）：
`assets/7610678417319925520` 「RADAR_TERMINAL V2 · Neon Trading Console」

### B. 自选池优先 / theme_auto fallback 逻辑包 ✅ 已提交

涉及文件：

- `run.py`
- `theme_auto.py`

**状态：2026-06-01 已 commit 落库（见本节末的「B 包提交记录」）。**

落地内容：

- `run.py`：
  - 新增 `_merge_watchlist_candidates()`：自选池股票在 quick_filter 后并入候选评估池，仅施加基础安全过滤（非 ST、非停牌、价格达标、非跌停、非一字涨停）；后续仍走历史过滤/打分/V1.6/9:36，不绕过任何安全门。
  - 新增 `_keep_watchlist_after_rank()`：在 `rank_and_select` 截断后补回已通过前序过滤的自选股，避免被 `top_n` 挤掉。`history_candidate` 和 `scored_pool` 两个阶段都调用。
  - `main()` 加入 `degraded_watchlist` 检测：当 theme_auto 报告该状态时，告警标题加「[自选池降级观察·不参与买入]」，body 加显著警告，**且跳过 `trade_review.append_rows`**（line 471 elif 分支）。
- `theme_auto.py`：
  - `_run_status` 新增 `degraded_watchlist` 字段。
  - 新增 `load_watchlist()`：从 `data/watchlist/custom_stock_pool.csv` 加载 active/watch 自选股。
  - 新增 `_fetch_ths_industry_boards()`：THS 行业板块汇总 fallback，amount 单位由「亿」换算为「元」对齐强度计算口径；`data_quality="partial"`。
  - `_get_board_df()`：链路升级为 EM 概念 → EM 行业 → THS 行业 → 磁盘缓存。
  - `_fetch_board_constituents()`：成分股链路升级为 EM 概念成分股 → EM 行业成分股，单接口失败不影响整体。
  - `run_theme_auto()`：把自选池股票 setdefault 进 `code_themes` / `code_boards`；当所有成分股链路全失败且有自选股时，置 `degraded_watchlist=True` 并 warning。
  - 候选股为空的三种情况（数据链路失败 / 部分失败 / 真无候选）都明确 return 空。

#### B 包提交记录

- commit hash: 见 `git log --oneline` 紧随 P1 commit `4fe0272` 之后。
- monkeypatch 验证 18/18 PASS，覆盖：
  1. 自选池并入候选池（5 项含基础安全拦截、标记字段）
  2. 排名截断后补回（2 项）
  3. EM 概念失败 → EM 行业 fallback（3 项）
  4. EM 概念成功时不调用 industry（1 项，反向断言避免过度调用）
  5. EM 板块全失败 → THS fallback（2 项）
  6. degraded_watchlist 触发条件（2 项）
  7. **run.py main() 中 `trade_review.append_rows` 写入受 `elif degraded_watchlist:` 保护**（2 项关键安全）
  8. `get_run_status()` 暴露 degraded_watchlist（1 项）

历史建议（已完成）：

```text
prioritize watchlist candidates and harden theme fallbacks
```

### C. 自选池数据包 ✅ 已提交

涉及文件：

- `data/watchlist/custom_stock_pool.csv`

**状态：2026-06-01 已 commit 落库。**

落地内容：

- 自选池从 3 只扩展到 13 只，全部 `priority=1, status=active`。
- 前序 3 只保留：300476 胜宏科技 / 600522 中天科技 / 603256 宏和科技。
- 新增 10 只覆盖光模块/CPO（300308 中际旭创、300502 新易盛）、PCB（002463 沪电股份）、智能制造/机器人（688017 绿的谐波、688160 步科股份、002008 大族激光）、汽车智能化（601689 拓普集团）、卫星互联网/电科系（688818 电科蓝天）、算力 IDC（002335 科华数据）、锗/稀有金属（002428 云南锗业）。
- 用户已确认这 13 只就是当前自选池。

历史建议（已完成）：

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
- ~~theme_auto 的数据源 fallback 已在前序未提交改动中增强，但尚未通过真实主流程运行验证。~~（2026-06-01 已通过 monkeypatch 18/18 验证并提交，详见 B 包记录。真实主流程运行验证仍需等用户手动触发，但安全屏障已经验证：自选池降级时 trade_review.csv 不写入）
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

## 当前活跃会话状态（2026-06-01）

### 已完成（本日已 commit 落库）

1. P1 修复 `4fe0272`：`trade_review.check_buy()` 实时行情失败状态写回 + dashboard 区分「实时行情缺失 / 实时价格无效」与「尚未运行」+ `STATUS_NOBUY_DATA_FAIL` 顶层标签。详见「2026-06-01 P1 修复补充」节。
2. B 包 `6ce3187`：`run.py` 自选池优先入候选池 + 排名截断后补回 + `theme_auto.py` 三级 fallback（EM 概念 → EM 行业 → THS 行业 → 缓存）+ 成分股 EM 概念→EM 行业 fallback + `degraded_watchlist` 降级标记 + 跳过 trade_review.csv 写入。18/18 monkeypatch PASS。详见 B 节。
3. C 包 `0cc5779`：自选池从 3 只扩展到 13 只。详见 C 节。
4. **A 包 `d243b8c`（本会话）**：`.streamlit/config.toml` light→dark RADAR_TERMINAL +
   `dashboard_app.py` 前序遗留 UI 整理 + V2 设计语言升级。详见 A 节。

### A 包 V2 升级要点（本会话核心成果）

按用户「时尚炫酷潮流 + 不留白 + 风格统一 + 空间利用充分」需求，
通过 Stitch MCP 生成 7 张参考设计稿，提炼出统一设计语言并落地代码：

**设计参考**（保存在 `/tmp/stitch_designs/`）：

- 7 张已生成：今日总览 / 我的自选 / 买入确认 / T+1 复盘 / 未买入跟踪 / 做T观察 / 周月复盘
- 3 张待补：候选复盘 / 明日计划 / 手动补跑

**代码落地**：

- 设计 token: `COLOR_MAGENTA_NEON`, `COLOR_WARN_YELLOW`, `COLOR_GLASS_*`
- 字体堆栈: `FONT_HEADLINE` (Space Grotesk) / `FONT_BODY` (Inter) / `FONT_MONO` (JetBrains Mono)
- 组件升级: `kpi_card` 12px 圆角 + 趋势箭头 + accent 条 + hover；`render_page_header` 14px
- 新增组件: `glass_card_html`, `chip_html`, `kpi_hero_strip`
- 全局 CSS 补丁: 卡 hover 上抬, Tab 电光青光晕, 数据表 36px row, st.metric 玻璃态,
  主按钮反色, tabs/expander 玻璃态, 字体堆栈统一

### 重启后下一步

1. 用户视觉验收 V2 效果：`streamlit run dashboard_app.py` 看 10 个页面。
2. 如果方向 OK：补 3 张缺失 Stitch 设计稿 + V2.1 按页面 layout 重构（按 Stitch 12-col 网格）。
3. 如果方向需要调：列出具体调整点，再迭代 V2.x。

### Stitch MCP 状态

- ✅ 已加载（`mcp__stitch__*` 全可用）
- 设计系统 asset ID: `assets/7610678417319925520`
- 已生成 7 张稿（项目 `14258134049390400909` + `3055147383678225214` + `8664187696220948756` + `9942816340452486281`）
- 待补 3 张项目 ID 见 A 节
- Stitch 服务在本会话后期 1 小时连续 timeout，对待补 3 个项目限流

### 用户偏好（与协作约定）

- **必须严格遵守 `AI_RULES.md`**：不运行 `python run.py` 或任何子命令；不动 `output/trade_review.csv` 历史；不引入真实交易；改禁改文件必须先说明；任务结束必须更新 `AI_HANDOFF.md` 和 `AI_CHANGELOG.md`。
- **拆 commit 习惯**：每个功能/修复一个独立 commit，不混；commit message 要写清楚 safety、verification、docs。
- **验收方式**：优先 `py_compile` + monkeypatch，禁止跑 `run.py`。
- **dashboard 改 UI 时**：只能改 `dashboard_app.py` 和 `.streamlit/config.toml`，且要说明只影响前端。
- **T 模块**：永远保持 simulate；不能接 launchd 实盘。
- 用户说话风格：简短、直接、口语化；接受中英混排；偶尔有拼音/输入法错字（如「嘎玛」「康熙」「记者」），按上下文还原意思即可。

### 已知待决策项（用户拍板）

- 自选池 `priority=1` 是否硬提到前三（强优先）还是只优先观察（弱优先）。
- T 模块何时接 launchd（保持 simulate 前提下）。
- T 模块真实 1 分钟数据源接入方案。
- ~~A 包 UI 优化的最终方向（等 Stitch 配合）。~~（V2 落地，等用户视觉验收）
- **V2.1 是否按 Stitch 设计稿做页面 layout 重构**（12-col 网格 + KPI Hero + 右侧栏）。
  V2 已经升级了 token / 卡片 / 全局 CSS，但页面 layout 框架还是旧的两列布局。

### 当前 git 状态（A 包提交后）

```
分支：restore/radar-terminal-keep-t
最近 6 个 commit：
  d243b8c polish radar terminal dashboard UI (A package) ← A 包 本会话
  d0d8462 handoff: add active session state ...
  0cc5779 update custom stock watchlist to 13 names      ← C 包
  6ce3187 prioritize watchlist candidates ...            ← B 包
  4fe0272 fix(check_buy): write back realtime data ...   ← P1
  8ed7261 document handoff plan for pending work

worktree 状态：clean（除非本次会话还有 AI 文档追加）
```

V1.6 dirty worktree 4 个包（P1 / A / B / C）至此全部提交落库。

## 2026-06-01 V2.2 today 重构尝试（未 commit，未达预期，等 Codex 接手决策）

### 任务背景

A 包 V2 commit `d243b8c` 用户实际看不出明显视觉差异（V2 只做了 token / 全局 CSS，
没动页面 layout 框架）。用户要求按 Stitch 设计稿做真实重构，**显著**对齐视觉。

用户具体要求（2026-06-01 session 后半段）：

1. 全部英文 → 中文（label / chip / 标题 / 状态文字）
2. 空的地方不要留白（学习 Stitch 排版）
3. 整体功能不变，只改 UI
4. 风格统一

### 我（Claude）做了什么

**仅改了 1 个文件**：`dashboard_app.py`（worktree dirty，881 insertions / 59 deletions）

具体新增 / 重写：

1. **新增辅助**：
   - `_h(s)` HTML dedent helper（处理 Streamlit Markdown 缩进式代码块识别坑）
   - `_v2_sparkline_svg(values, color)` 内联 SVG sparkline 趋势线
   - `_v2_mock_sparkline_from_pct(pct)` 基于涨幅生成 mock 走势（**承认是假数据**）

2. **重写 / 升级**：
   - `kpi_hero_strip()` 长条横排 → **5 张独立方卡 grid**（含 sparkline + 环形进度）
   - `_v2_stock_card()` 升级：全中文 + sparkline + 涨幅条 + V1.6 三层 chip（复盘 / 资金 / 9:36）
   - `_v2_sidebar_capital()` 重命名为「市场脉冲」，6 行数据（北向资金 / 两市成交额 / 涨跌家数 / 涨跌停）
   - `_v2_sidebar_v16_rates()` 重命名为「V1.6 达标流程」，3 条进度条 + 口径说明 + V1.6 智能算法引擎徽章
   - `_v2_sidebar_top3()` 重命名为「核心推荐」，**空数据时返回 ""（不渲染整张卡）**
   - `_v2_signal_stream()` 中文表头 + min-height: 360px + LIVE 脉冲
   - `render_today_v2_stitch()` 全面改造：全中文 KPI + 智能 grid（候选 < 4 时按 n 列撑满）+ 策略洞察卡 + 实时信号流嵌入左侧
3. **数据翻译表**：
   - 新增 `V16_NOTES_CN`（V1.6 相关 notes code → 中文）9 条
   - 加入 `NOTES_CN` 合并，修复 `v16_plan_only_observe` 等英文 code 显示问题
4. **import 新增**：`re`, `textwrap`
5. **CSS 改动**：
   - 新增 V2.2 marker class `.rt-v2-today-marker`（display:none，仅作选择器锚点）
   - 全局 CSS 末尾加 V2.2 两栏对齐补丁（用 `:has()` + flex-grow）

### 哪些成功了

- ✅ 全中文化（label / chip / 标题 / 状态 / 表头 全是中文）
- ✅ 5 张 KPI Hero 方卡（不再是长条）+ sparkline / 环形进度
- ✅ 候选股票卡显著升级（左侧 accent + 大价格 + 涨幅 + 涨幅条 + sparkline + V1.6 三层 chip）
- ✅ 策略洞察卡（含主要未买入原因 chip）
- ✅ 实时信号流移到左侧主区底部
- ✅ V16 code 英文显示问题修复（v16_plan_only_observe → V1.6 复盘计划要求只观察）
- ✅ Stitch 设计稿视觉一致性：玻璃态 + 电光青 / 霓虹绿 / 品红霓虹 + JetBrains Mono
- ✅ 用户视觉确认：「我的自选 / KPI Hero / 候选卡 / 实时信号流」都没问题

### 哪些反复失败 / 用户不满意

**核心矛盾：两栏底部对齐**

- 第 1 次：CSS `align-items: stretch` + `flex-grow: 1` 选择器 → 用户截图证明无效
- 第 2 次：换 `:has()` 选择器 + `display:none` marker → 用户截图证明仍然无效
- 第 3 次：放弃 CSS hack，改 workaround：
  - 「核心推荐」空数据时不渲染整张卡（让右侧从 3 块变 2 块）
  - 「实时信号流」加 `min-height: 360px` 撑高
  - 我用 Chrome DevTools CDP 自检截图，左右底部对齐差 < 10px
  - 用户后续无反馈，但用户认为整体 V2.2 推进效率拉垮，决定换 Codex 接手

**根本问题**：Streamlit 的 `st.columns()` 内部有多层 wrapper（`stHorizontalBlock` →
`stColumn` → `stVerticalBlock` → `stElementContainer` → `stMarkdownContainer` ...），
CSS flex chain 在多层嵌套下不可靠，每次 streamlit 升级版本结构都可能变。

**Workaround 的代价**：

- 「核心推荐」空数据时整张卡消失（视觉信息减少）
- 「实时信号流」min-height: 360px 数据少时底部有视觉空白
- 这些不是根本解，是绷出来对齐的

### 用户对 V2.2 的态度

直接原话："你太拉垮了，洗一下总结，我让 codex 去搞"。

意思：
- 不否定 V2.2 视觉方向（中文化 / 玻璃态 / Hero / 候选卡 / 设计语言都认可）
- 但实施过程反复失败 + 对齐 hack 让用户不耐烦
- 要换 Codex 接手收尾

### Codex 接手时立刻该做什么

#### 第 0 步：确认 git 状态

```bash
git status        # 应当显示 M dashboard_app.py
git log --oneline -5   # 最近 commit 应当是 3fa182a docs ... d243b8c V2 token + CSS ...
git diff --stat   # dashboard_app.py 881 insertions / 59 deletions
```

#### 第 1 步：方向决策（与用户对齐）

**选项 A：基于 V2.2 dirty 继续修**
- 优点：用户认可的视觉元素（中文化 / KPI Hero / 候选卡 / 策略洞察 / 实时信号流）已经在 worktree 里
- 缺点：要解决两栏对齐根本问题（不能再用 CSS hack）
- 推荐方法：用 `streamlit.components.v1.html` 完全自渲染主区（绕过 streamlit 多层 wrapper），用纯 CSS grid 自己控制 layout

**选项 B：git restore，回到 V2.1（commit `d243b8c`）**
- 优点：clean state，全新规划
- 缺点：V2.2 dirty 里有用户认可的视觉元素全部丢弃
- 命令：`git restore dashboard_app.py`

**选项 C：把 V2.2 dirty 当 WIP commit 落库，再决定**
- `git add dashboard_app.py && git commit -m "wip: V2.2 today refactor (alignment unresolved)"`
- 然后基于此 commit 接续工作或 revert

#### 第 2 步：如果选 A 或 C，重点解决对齐

**不要**继续用 CSS `:has()` + flex-grow 这条路（已证明在 streamlit 嵌套下不稳）。

**建议**：用 `st.components.v1.html()` 完全自渲染整个主区
- 单一 HTML 文档，无 streamlit wrapper 干扰
- CSS grid `grid-template-columns: 2fr 1fr` 完全可控
- 缺点：失去 streamlit 反应式（点击 button / hover 等需要回调）—— 但当前 V2.2 主区本来也是纯展示

或者：把整个主区写成一个超大 HTML（不用 columns），用 CSS grid 直接铺。
保留 streamlit columns 只用在「日期选择器」等需要交互的地方。

#### 第 3 步：剩下未做的事

按现有 V2.2 改动后，还有 6 个页面没改造：

1. ⭐ 我的自选（`page_watchlist`）
2. 买入确认（`page_buy_check`）
3. T+1 复盘（`page_t1_review`）
4. 未买入跟踪（`page_not_bought`）
5. 周月复盘（`page_period_review`）
6. 做T观察（`page_t_signal`）
7. 候选复盘（`page_candidate_lifecycle`）
8. 明日计划（`page_tomorrow_plan`）
9. 手动补跑（`page_manual_rerun`）

每页都需要参考 `/tmp/stitch_designs/` 下对应的 Stitch 设计稿来重构。

**Stitch 设计稿位置**：
- `/tmp/stitch_designs/01_today_overview.png` 今日总览 ✅ 已落地（dirty 状态）
- `02_watchlist.png` 我的自选
- `03_buy_check.png` 买入确认
- `04_t1_review.png` T+1 复盘
- `05_not_bought_tracking.png` 未买入跟踪
- `06_t_signal.png` 做T观察
- `07_period_review.png` 周月复盘
- 缺 3 张：候选复盘 / 明日计划 / 手动补跑（Stitch 服务挂了，下次会话再补）

#### 第 4 步：还有 5 个用户问过的「真假」问题

详见用户 session 中段提的 5 问及我的回答（详细记录在本节之前）：

| 问题 | 答案 | 状态 |
|---|---|---|
| 指标真假 | 5 大数字**全真**（CSV / JSON） | ✅ 真 |
| 模拟收入 | T+1 后才有，今天 ¥0 是真实状态 | ⏳ 待 T+1 |
| K 线图 (sparkline) | **mock 假数据**，基于涨跌方向生成 | ⚠️ 需接 akshare/efinance |
| V1.6 达标流程 | 复盘层 ✅真；资金 / 9:36 层是**简化代理** | ⚠️ 需改 trade_review.py 加 `capital_layer_passed` / `confirm_layer_passed` 字段 |
| 大段空白 | 已修（核心推荐空隐藏 + 实时信号流 min-height） | ✅ 已修（但是 workaround） |

**用户没有明确允许改 trade_review.py（禁改文件）来精准化 V1.6 三层达标率。**
**用户没有明确要求做真实 sparkline（接 akshare/efinance）。**
**这两个都需要 Codex 接手时先和用户对齐才做。**

### Codex 接手前的环境清理

- ✅ 已 kill streamlit 进程
- ✅ 已 kill chrome headless 进程
- ✅ 端口 8501 已释放
- ✅ `py_compile dashboard_app.py` PASS

### 关键文件位置

- 主 UI 文件：`dashboard_app.py`（worktree dirty）
- 配置文件：`.streamlit/config.toml`（已 commit，无 worktree 改动）
- Stitch 设计稿：`/tmp/stitch_designs/01-07*.png`（重启后会丢，备份重要）
- 自检脚本：`/tmp/cdp_shot.py` 和 `/tmp/cdp_shot_hd.py`（用 Chrome DevTools 远程调试 + Python websockets 库自截图，绕过 streamlit WebSocket SPA 渲染异步问题）

### 自检截图工具（Codex 可继续用）

```bash
# 启动 chrome headless + CDP debugging
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --no-sandbox \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/cdp_chrome_profile \
  --window-size=1600,1300 \
  about:blank &

# 跑截图脚本
python3 /tmp/cdp_shot.py    # 普通分辨率，约 250KB PNG
python3 /tmp/cdp_shot_hd.py # 2x deviceScaleFactor，约 650KB PNG
```

CDP 截图能等到 `Page.lifecycleEvent: networkIdle` 之后再 sleep 4s 截，确保 streamlit
WebSocket 渲染完毕。这是验证 UI 改动的可靠手段。

## 2026-06-01 Codex 接手 V2.2 today 布局修复

### 本次判断

- 不建议直接 `git restore` 回退 Claude 的 dirty UI 改动，因为其中已经包含 V2.2 today 页面的大量视觉素材和数据卡片函数。
- 不继续在 `st.columns()` 内做 CSS flex 对齐。Claude 反复失败的根因是 Streamlit columns 多层 wrapper 高度链条不可控。
- 已把「今日总览」主展示区改为单个 HTML Grid 结构，通过 `st.html()` 渲染，避开 `st.columns()` 与 `:has(.rt-v2-today-marker)` 对齐 hack。

### 已完成

- 已备份 Stitch 设计稿到仓库内：
  - `docs/ui_refs/stitch_designs/01_today_overview.html`
  - `docs/ui_refs/stitch_designs/01_today_overview.png`
  - `docs/ui_refs/stitch_designs/02_watchlist.png`
  - `docs/ui_refs/stitch_designs/03_buy_check.png`
  - `docs/ui_refs/stitch_designs/04_t1_review.png`
  - `docs/ui_refs/stitch_designs/05_not_bought_tracking.png`
  - `docs/ui_refs/stitch_designs/06_t_signal.png`
  - `docs/ui_refs/stitch_designs/07_period_review.png`
- `dashboard_app.py` 今日总览已从 `st.columns()` 主区改为 `.rt-v22-layout` CSS Grid。
- 今日总览左侧「策略洞察 / 实时信号流」已进一步压紧，Chrome 实测左右主区底部基本对齐。
- 已修复导航切换后保留滚动位置的问题：切换顶部导航时自动把 `stMain` 滚回顶部。
- 已解除 `⭐ 我的自选` 页面的一屏锁定；自选池有 13 只股票，需要允许页面滚动。
- 未修改选股、买入、T 模块、卖出、复盘记录等后端逻辑。

### 验收结果

- `.venv/bin/python3 -m py_compile dashboard_app.py`：通过。
- Streamlit AppTest：10 个导航页全部 non-crash。
- Chrome 实测：今日总览 / 买入确认 / T+1 复盘 / 未买入跟踪 / 周月复盘 / 候选复盘 / 明日计划 / 做T观察 / 我的自选 / 手动补跑 均可切换打开。
- 未运行 `python run.py` 或任何 `run.py` 子命令。

### 下一步建议

1. 用户先看今日总览是否比 Claude 版本更稳、更少空白。
2. 如果今日总览方向确认，再按以下顺序继续页面 UI：
   - `⭐ 我的自选`：用户最敏感，当前布局仍需要收紧和提升个股卡片密度。
   - `买入确认`：交易主流程入口，优先级高。
   - `做T观察`：已具备 T 记录 / B/S 点 / 盈亏统计，适合做成实战监控面板。
   - `明日计划`：用于第二天执行准备。
   - `T+1 复盘`、`未买入跟踪`、`周月复盘`、`候选复盘`、`手动补跑`。

## 2026-06-01 Codex 功能 QA 补充

### 已核对

- 当前工作区未改禁改文件：`run.py`、`trade_review.py`、`output/trade_review.csv`、`config/version_flags.yaml`、`launchd/*.plist` 均无 diff。
- `data/watchlist/custom_stock_pool.csv` 当前有 13 只股票，字段为 `stock_code, stock_name, priority, theme, reason, research_date, status, max_position_pct, note`。
- `⭐ 我的自选` 页面 Chrome 实测：
  - 展示 13 / 13 只股票。
  - 搜索 `胜宏` 后只显示 `胜宏科技`。
  - 输入 `300476` 可识别为 `胜宏科技`。
  - 输入 `胜宏科技` 可识别为 `300476 胜宏科技`。
  - 未点击最终「加入自选池」按钮，因此未写入 CSV。
- `output/trade_review.csv` 当前 2026-06-01 有 3 条候选：
  - `600522 中天科技`
  - `600027 华电国际`
  - `300327 中颖电子`
  - 三条均为 `buy_signal_0935=false`，`notes=v16_plan_only_observe`，说明今天是 V1.6 计划层观察，不是已确认买入。
- `output/t_trade/t_trade_latest.csv` 当前是 2026-05-29 sample 验证记录，共 4 笔：
  - 低吸止盈：`take_profit_1_5`，`closed`，`return_pct=0.015`
  - 低吸止损：`stop_loss_1_5`，`stopped`，`return_pct=-0.015`
  - 高抛回补：`buyback_1_5`，`closed`，`return_pct=0.015`
  - 高抛踏空止损：`stop_buyback_1_5`，`stopped`，`return_pct=-0.015`
- T 记录安全字段保持模拟：
  - `execution_mode=simulate`
  - `can_execute_live=False`
  - `order_status=not_submitted`
  - `broker_status=not_connected`
- `output/t_trade/*` 和 `output/trade_review.csv` 均被 `.gitignore` 的 `output/` 规则忽略。

### 验收结果

- `.venv/bin/python3 -m py_compile dashboard_app.py scripts/build_t_trade_tracker.py`：通过。
- Streamlit AppTest：10 个导航页全部无异常。
- `做T观察` 页面 Chrome 实测：
  - 默认显示「暂无真实 T 数据」，不显示 sample。
  - 勾选「显示样例数据」后展示「今日 T 交易记录」和「B/S 点与盈亏统计」。
  - 页面有「当前为做 T 模拟记录，不构成自动买卖指令」提示。
- 未运行 `python run.py` 或任何 `run.py` 子命令。

### 当前遗留问题

- 今日没有真实 T 记录的主要原因仍是：T 脚本尚未接入 launchd 定时任务，且真实分钟数据源未完成稳定验证。
- 今日候选没有进入买入确认的直接原因是：V1.6 计划层返回 `v16_plan_only_observe`。
- `⭐ 我的自选` 快速识别功能可用，但已存在股票识别后按钮仍显示「加入自选池」，文案容易误解；后续可改成「已在观察池 / 更新为 active」。
- AppTest 会提示 `st.components.v1.html` 未来弃用；当前仅用于导航切换自动回顶 JS，不影响运行，但后续应寻找更长期的替代方案。

## 2026-06-01 Codex 自选池优先级修复

### 背景

用户明确要求「优先自选池选股」。原逻辑已经会把 active/watch 自选股并入候选评估池，并在排名截断后补回，但自选股仍可能在 `history_filter` 阶段被清掉，导致最终推荐没有优先体现自选池。

### 已完成

- 修改 `run.py` 中 `_keep_watchlist_after_rank()`：
  - 不再因为 `ranked_df.empty` 直接返回。
  - 即使历史过滤后为空，也允许从已通过前序安全条件的 `source_df` 中补回自选池股票。
  - 日志改为更通用的「阶段补回自选池」。
- 在 `filters.history_filter()` 之后新增一次自选池补回：
  - `deep_filtered = _keep_watchlist_after_rank(deep_filtered, candidate_df, active_wl, logger, "history_filter")`
- 修复自选池代码匹配细节：
  - `wl_by_code` 统一 `zfill(6)`。
  - `priority` 非法值默认按 3 处理，避免异常中断。

### 安全边界

- 自选池仍不是买入指令。
- 自选股仍必须先进入基础安全过滤和候选评估池。
- 自选股仍必须能拿到历史 K 线、能计算指标和打分。
- 仍会经过 V1.6 明日计划层和 9:36 技术确认。
- 未触发任何真实交易。
- 未运行 `python run.py` 或任何 `run.py` 子命令。

### 验收

- `.venv/bin/python3 -m py_compile run.py`：通过。
- mock 验证：
  - 普通池剩 1 只时，自选池可被补回。
  - 历史过滤结果为空时，自选池也可从候选评估池补回。

### 下一步

- 如需更强版本，可继续改为「自选池 P1/P2 严格占满前三，不足再由全市场补齐」，但那会进一步改变选股策略，应单独确认。

## 2026-06-01 推送层合并 + 月复盘自动化 + T 模块实时（重要里程碑）

### 任务背景

用户提了 3 件相互关联的事：

1. **微信推送过载**：原 5+ 条/日单独推送（pick / themeauto / checkbuy / secondcheck / update），逼近 ServerChan 免费 5 条/日 上限，数据源失败告警还会爆掉。
2. **月复盘缺失**：周复盘 launchd 已装，但月复盘只有 `scripts/run_monthly_review.sh` 注释明确说"手动运行"，没自动调度。
3. **T 模块只是 sample**：`scripts/build_t_signal_observer.py` 和 `build_t_trade_tracker.py` 代码完整，但没接 launchd / 没真实分钟数据源，`output/t_trade/*.csv` 都是 5-29 的 sample 验证记录。

### 用户拍板的决策

1. **推送方案**：方案 A 双轨独立 + 推送层合并（不改主选股逻辑）
2. **3+3 结构**：主策略 3 只（mode=full）+ 龙头观察 3 只（mode=theme_auto）独立写 trade_review.csv，推送时合并展示
3. **告警节流**：所有 alert_type **共享每日 1 条**全局额度（不是 per-alert_type 1 条）
4. **second_check**：取消单独推送，保留 CSV 写入，结果合并到 19:00 复盘
5. **T 模块定位**：模拟盘 + 盘中实时记录 B/S 点 + 收盘统计盈亏 + 一个月累积 + 不推送、只看板看（用户原话："这个是模拟盘 你只需要记录你盘中的bs点 并且记录你bs的时间 收盘统计bs的盈亏"）
6. **数据源**：选项 A akshare 免费（用户原话："接受"）
7. **触发频率**：盘中每分钟跑（StartInterval=60）+ 收盘 15:30 汇总一次

### 7 个落库 commit（按时间顺序）

```text
8636442 fix(dashboard): watchlist quick-add button label by stock status
582b1a2 feat(notifier): merge push 3+3 + global daily alert throttle
96a1d75 feat(run): add --morning-digest + merge check-buy/update-review push
dbdbeb0 chore(launchd): add morning-digest schedule at 09:05
05ad30f feat(monthly): auto monthly review on the 1st via launchd
588d3c1 feat(fetcher): add fetch_minute_today for T module (akshare 1-min K)
0145717 feat(t-module): real-time intraday B/S signal + EOD aggregation
```

### 12 个 launchd 任务（全部装载）

```text
08:50  pick.plist              full 选股 → CSV，不推送
08:55  themeauto.plist         主题龙头 → CSV，不推送
09:05  morningdigest.plist     早盘 3+3 合并推送 ⭐ 本会话新增
09:35-14:55  tintraday.plist   每 60 秒触发，wrapper 判断时段 ⭐ 本会话新增
              （拉 1 分钟 K + 识别 B/S → t_signal_*.csv）
09:36  checkbuy.plist          9:36 合并买入确认推送
10:01  secondcheck.plist       写 state，不推送（合并到 19:00）
15:30  teod.plist              T 模块收盘汇总 ⭐ 本会话新增
              （配对 B/S + 算盈亏 + 写 t_summary JSON）
19:00  update.plist            合并复盘 + T 摘要推送
19:10  summary.plist           仅 Excel
1 号 17:00  monthlyreview.plist   上月月报推送 ⭐ 本会话新增
周末   weeklyreview.plist      周报推送
/      supervisor.plist        监督告警
```

工作日预计：3-4 条主推送 + ≤1 条全局告警 ≤ 5 条/日 ✅

### 每日数据流（明天起按这个跑）

```
08:50  trade_review.csv 写入 mode=full 3 行
08:55  trade_review.csv 写入 mode=theme_auto 3 行
09:05  morning-digest 读 csv → 合并推送 3+3
09:35-14:55  每分钟拉 6 只股 1 分钟 K → 增量识别信号 → t_signal_<date>.csv（盘中实时）
09:36  check-buy → buy_signal_0935 写回 → 合并 3+3 推送
15:30  EOD：重新拉全天 → 配对 B/S → 算盈亏 → t_trade_<date>.csv + t_bs_log_<date>.csv → output/state/t_summary_<date>.json
19:00  update-review → 合并复盘 + T 摘要（从 t_summary JSON 读）→ 推送
```

### 关键技术决策追溯

- 推送合并用 `format_morning_digest_message` / `format_combined_check_buy_message` / `format_combined_review_message` 三个新函数
- 全局告警节流：`output/state/alert_sent_YYYYMMDD_global.flag` 标记
- 月复盘新增 `_last_month_range()`：1 号跑统计上月（跨月/跨年自动处理）
- T 模块用 `ak.stock_zh_a_hist_min_em` 拉 1 分钟 K（中文列名映射成英文）
- T 模块 pipeline：`run_t_intraday.py`（盘中信号）+ `run_t_eod.py`（收盘汇总）
- pipeline 用 subprocess 调用 `build_t_signal_observer.py` / `build_t_trade_tracker.py`，**不修改这两个脚本本体**

### Mock 测试（全 PASS）

- notifier 推送合并 + 全局节流：**12/12**（含跨日期 mock datetime）
- T pipeline：**7/7**（含 _today_codes_from_review、列名映射、容错、aggregation）
- monthly_review `_last_month_range`：**3/3**（跨月 / 跨年 / 30-31 天月份）

### 重要：禁改文件 + 安全边界

本会话**未触碰**：

- ✅ `trade_review.py` — T 模块通过 subprocess 调外部脚本，不修改主买入判断
- ✅ `output/trade_review.csv` 历史数据 — 仅 append，不改已有行
- ✅ `config/version_flags.yaml`
- ✅ 自动下单 / 券商连接 / 止损主逻辑 / T+1 收益主逻辑

本会话**修改了**（用户授权后改动）：

- `run.py`：新增 `--morning-digest` / `--last-month` 子命令 + 改 check-buy/update-review 推送格式
- `launchd/*.plist`：新增 morningdigest / monthlyreview / tintraday / teod 4 个 plist

本会话**新增**：

- `data_fetcher.py` 新增 `fetch_minute_today()` 函数
- `notifier.py` 新增 5 个推送/节流函数
- `periodic_review.py` 新增 `_last_month_range()`
- `scripts/run_t_intraday.py` / `run_t_intraday.sh`
- `scripts/run_t_eod.py` / `run_t_eod.sh`
- `scripts/run_monthly_review_auto.sh`

### T 模块字段安全（未改）

所有 T 模块字段保持 simulate：

```text
execution_mode=simulate
can_execute_live=False
order_status=not_submitted
broker_status=not_connected
```

### 已知局限（写给接手 AI）

1. **akshare 1 分钟 K 接口延迟 1-2 分钟**
   - 不是 Tick 级毫秒数据，是 K 线级
   - 对模拟盘记录场景完全够用（写入的 timestamp 是 K 线真实时间）
   - 真要实战按信号下单会有 1-2 分钟滑点 — 但用户场景是模拟盘 + 看板复盘

2. **akshare 接口稳定性未实测**
   - 沙盒里测试时 `Connection aborted, RemoteDisconnected` 一次
   - 用户实际网络环境可能更好
   - 接口失败时 `fetch_minute_today` 返回 None，pipeline 容错
   - 建议接手 AI 在 2026-06-02 第一次跑后看 `logs/auto_run.log` 验证实战稳定性

3. **morning-digest 09:05 时点**
   - pick 08:50 + themeauto 08:55 → 给 10/15 分钟执行窗口
   - 如果某天 pick / themeauto 超过 10 分钟还没写完 csv，morning-digest 可能拿不到完整数据
   - 实测后若需调整可改 09:10 或 09:15

4. **T 模块跑约 220 次/日（每分钟）**
   - 60 秒 wrapper 启动 + 时段判断
   - 每分钟拉 6 只股 = 6 次 HTTP 请求
   - 全天约 220 × 6 = 1320 次 HTTP 请求到东方财富
   - 如果被限流，可调 plist `StartInterval` 到 120（每 2 分钟）

5. **`docs/ui_refs/stitch_designs/`** 已经在 c550774 commit 备份到仓库内（不会丢）

### 接手 AI 立刻该做什么

#### 第 1 步：确认 git + launchd 状态

```bash
git log --oneline -10            # 应当看到 7 个本会话 commit
git status                       # 应当 clean
launchctl list | grep com.zhuge  # 应当 12 个任务全在
```

#### 第 2 步：检查明天（2026-06-02）实战效果

如果接手 AI 在 2026-06-02 之后启动：

```bash
# 检查 morning-digest 是否真推送了
tail -200 logs/auto_run.log | grep -i "morning_digest"

# 检查 T 模块是否真跑了
tail -500 logs/auto_run.log | grep -i "t_intraday\|t_eod"

# 检查 trade_review.csv 当天数据
awk -F, '$1=="20260602"' output/trade_review.csv | head -10

# 检查 T 模块产出
ls -la output/t_trade/t_*_20260602.csv 2>/dev/null
cat output/state/t_summary_20260602.json 2>/dev/null
```

#### 第 3 步：如果有异常，可能的修复方向

- **morning-digest 没推送**：检查 logs/auto_run.log 是否有 morning_digest 启动日志；trade_review.csv 是否当天有数据
- **T 模块没数据**：akshare 接口失败概率高，看日志里 `fetch_minute_today` warning
- **launchd 任务没跑**：`launchctl list | grep <task>` 看是否有 exit code
- **告警炸 5 条/日**：检查 `output/state/alert_sent_*_global.flag` 标记是否正常工作

### 后续可能的迭代方向（用户尚未拍板）

1. **看板「做 T 观察」页**：现在默认隐藏 sample，real data 第一次出现是 2026-06-02 15:30 之后。可以做月度统计图（一个月 B/S 累积 / 胜率 / 盈亏曲线）
2. **付费实时数据源升级**：如果用户发现 akshare 1-2 分钟延迟影响实战感，升级到同花顺 iFinD（¥3000/年）或自建 push2delay daemon
3. **9 个其他 dashboard 页面 UI 改造**：方案 A 推送层合并完成后，仍剩 9 页待 V2.2 视觉化（我的自选 / 买入确认 / T+1 复盘 / 等）
4. **T 模块 dashboard 月度统计**：现在 page_t_signal 只展示当日，可以加月度 trends 图

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
