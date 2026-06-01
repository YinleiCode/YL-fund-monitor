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
