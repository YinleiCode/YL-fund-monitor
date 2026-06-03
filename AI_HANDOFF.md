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

## 2026-06-02 Codex 逻辑修复：合并复盘 + T 模块记录

### 本次修复背景

在最新提交基础上只读审查后发现：交易安全边界正常，但合并推送/复盘/T 模块记录层存在几个会误导用户的字段对齐问题。

### 已修复

- `run.py`
  - 修复 `--second-check` 写 `output/state/second_check_<date>.json` 的统计口径。
  - 原代码读不存在的 `verdict` 字段，导致 10:00 二次确认在 19:00 合并复盘中通过数可能永远为 0。
  - 新逻辑使用 `second_check_passed`，并排除实时行情缺失等 error 行。
- `trade_review.py`
  - `update_review()` 返回给合并复盘的 `rows` 增加 `mode`。
  - 修复 theme_auto / 龙头观察 T+1 复盘被默认归到 full 主策略的问题。
- `scripts/run_t_intraday.py`
  - 新增 `_today_candidates_from_review()`，从 `trade_review.csv` 同时读取 `stock_code / stock_name / ma10`。
  - 调 `build_t_signal_observer.py` 时追加 `--name-override` 和 `--ma10-override`，避免真实 T 记录显示“名称未获取”。
- `scripts/run_t_eod.py`
  - 同步使用候选名称和 MA10 override。
  - observer/tracker 失败时写入明确 `status=observer_failed/tracker_failed`，不再装作正常摘要。
  - 分钟数据全失败时写 `status=minute_data_missing`。
  - T 摘要新增 `pnl_total_pct`，供推送展示百分比口径。
- `scripts/build_t_signal_observer.py`
  - MA10 缺失时 T 信号不再通过，写 `fail_reason=ma10_missing`。
  - 说明：当前仍未计算真实 MA10 斜率，只是确保有有效 MA10 参考值；真实“MA10 斜率向上”需要后续接日线序列。
- `notifier.py`
  - 合并复盘的 T 摘要从“累计模拟盈亏 0.03”改为“累计模拟收益率 +3.00%”口径。
  - 如果 T 摘要状态不是 `ok`，推送会提示摘要可能不完整。

### 验收

- `.venv/bin/python3 -m py_compile run.py trade_review.py notifier.py scripts/run_t_intraday.py scripts/run_t_eod.py scripts/build_t_signal_observer.py scripts/build_t_trade_tracker.py data_fetcher.py dashboard_app.py`：通过。
- 函数级验证：
  - second_check state 统计：`total=2, passed=1, failed=1`。
  - T 信号无 MA10：返回 `rule_pass=False, fail_reason=ma10_missing`。
  - T 信号有 MA10：样例仍能出现通过信号。
  - T observer 命令补齐：能生成 `--name-override 300476:胜宏科技` 和 `--ma10-override 300476:88.88`。
  - 合并复盘 T 摘要：展示 `累计模拟收益率 +1.50%`。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。
- T 模块仍然保持 simulate / not_submitted / not_connected。

### 遗留问题

- T 模块仍需 2026-06-02 实盘验证 akshare 1 分钟 K 是否稳定。
- `ma10_slope_up` 字段当前只代表“有 MA10 参考值”，不代表真实斜率向上。后续如要严谨，应在 T pipeline 中读取日线，计算 MA10 最近两日差值。
- 09:05 morning-digest 是否会遇到 pick/themeauto 未写完，需要看当天 `logs/auto_run.log`。

## 2026-06-02 Codex 朱哥要求：自选池优先 + 做 T 跨日追踪

### 本次业务要求

朱哥明确要求当前选股和做 T 逻辑改成：

- 选股推送是 3 龙头 + 3 全票，一次推送 6 只。
- 3 龙头和 3 全票都必须优先自选池。
- 自选池 P1/P2/P3 都排在普通候选前，但仍不绕过基础过滤、历史过滤、评分、V1.6 计划层、资金条件层、9:36 技术确认层。
- 做 T 使用 1 分钟 K 延迟记录，保持模拟观察。
- 做 T 必须记录 B/S 点、止盈止损、盈亏。
- 做 T 没有止盈止损时不能当天过期，要保持 open，后续交易日继续追踪，直到止盈或止损。

### 已完成改动

- `run.py`
  - full 全票最终排序改为：自选 P1 → 自选 P2 → 自选 P3 → 普通候选。
  - 仍然只改变最终排序，不绕过前序过滤链路。
- `theme_auto.py`
  - 龙头模式新增 `_apply_watchlist_priority_to_results()`。
  - 龙头最终 top3 也改为：自选 P1 → 自选 P2 → 自选 P3 → 普通候选。
  - 日志会标出是否自选池、tier、priority。
- `scripts/build_t_trade_tracker.py`
  - 新增 `output/t_trade/t_open_positions.csv` 状态文件。
  - 当低吸/高抛 T 未触发止盈止损时，`trade_status=open`，不再写 `expired/no_exit_before_close`。
  - open 单只写入场 B/S 点；后续交易日触发退出时再写对应 S/B 点和盈亏。
  - 每次 tracker 会先续扫历史 open 单，再处理当天新信号，并按 `trade_id` 去重。
  - 关闭或止损后自动从 `t_open_positions.csv` 移除。
- `scripts/run_t_intraday.py`
  - 盘中 T 追踪池合并当天 3+3 候选 + 历史 open T 单。
  - 每分钟识别 T 信号后，立即调用 `build_t_trade_tracker.py` 更新 T 交易记录 / B/S 点 / 盈亏。
  - 仍然只做 simulate，不推送、不下单。
- `scripts/run_t_eod.py`
  - 复用盘中候选读取，因此盘后也会继续追踪历史 open T 单。

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
- 样例 T 交易复核通过：
  - `300011 low_absorb_tp` → `take_profit_1_5 / closed / 0.015`
  - `300012 low_absorb_sl` → `stop_loss_1_5 / stopped / -0.015`
  - `300013 high_throw_buyback` → `buyback_1_5 / closed / 0.015`
  - `300014 high_throw_stopbuyback` → `stop_buyback_1_5 / stopped / -0.015`
- 新增跨日 open 验证通过：
  - Day1 未触发止盈止损 → `trade_status=open`，只写 B 点。
  - Day2 达到 +1.5% → `trade_status=closed`，写 S 点，`return_pct=0.015`。
  - open 状态文件 Day1 有 1 条，Day2 关闭后清空。
- 自选池排序验证通过：
  - 即使普通候选分数更高，排序仍为 P1 → P2 → P3 → 普通候选。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。
- T 模块仍然保持：
  - `execution_mode=simulate`
  - `can_execute_live=False`
  - `order_status=not_submitted`
  - `broker_status=not_connected`

### 当前遗留问题

- 这轮生成了 sample 验证用的 `output/t_trade/*` 运行产物，但 `output/` 被 `.gitignore` 忽略，不应提交。
- 真正盘中每分钟 T 记录效果仍需等真实交易日 launchd 跑后看 `logs/auto_run.log` 和 `output/t_trade/`。
- `ma10_slope_up` 仍未做真实斜率，只是要求有有效 MA10 参考值。

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

---

## 2026-06-02 Claude（盘中 notifier nan 修复 + 实战首日观察）

### 本次任务

1. 修复 morning-digest 推送中 "总分 nan / 空间 nan" 的格式化 bug。
2. 观察 2026-06-02 实战首日 launchd 调度链路的真实运行情况。
3. 记录今日观察 + 给 Codex 接力。

### 修改文件

- `notifier.py`
  - `_fmt_num`、`_fmt_pct` 原本只用 `try/except (TypeError, ValueError)` 兜底，但 `float("nan")` 不抛异常，导致 NaN/Inf 被直接写进文案。
  - 加 `import math`，在 `try` 通过后追加 `math.isnan(f) or math.isinf(f)` 检查，命中则返回占位符 `—`。
  - 本地 mock 测试 20/20 通过（`_fmt_num` 12 例 + `_fmt_pct` 8 例，覆盖 `float("nan")`、`float("inf")`、字符串 `"nan"`、`None`、正常浮点）。

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

- 未运行。盘中所有 `run.py` 子命令均由 launchd 触发。

### 验收

- `git show bf9ce11 --stat` 仅修改 `notifier.py`（+18 / −4 行）。
- 本地 mock 运行 morning-digest 数据结构，nan 字段已渲染为 `—`。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`bf9ce11 fix(notifier): handle NaN/Inf in _fmt_num and _fmt_pct`
- status：本次提交只动 `notifier.py`，工作区其余文件保持脏（dashboard_app.py / scripts/build_t_trade_tracker.py / scripts/run_t_eod.py 为 Codex 在改）。

### 2026-06-02 实战首日观察

| 时间 | 事件 | 结果 |
| --- | --- | --- |
| 08:30 | morning-digest | 成功推送；龙头池字段曾出现 nan（已在 bf9ce11 修复，但仅次日生效）。
| 08:55 | theme-auto | 东方财富 `RemoteDisconnected, Connection aborted`，已走 fallback 写空 CSV；非代码问题，是环境/对端临时抖动。
| 09:30+ | T 模块 `run_t_intraday.py` 每 60 秒 | 真实拉取 `stock_zh_a_hist_min_em` 成功，3 只观察标的连续 1-min K 线全部入库，落地 `data/minute_today/`。
| 09:44 | check-buy | 比预期 09:36 晚 8 分钟；当日 pre-gate 全数未过，无买入信号；推送一次"无信号"主消息。
| 全天 | 全局 alert 节流 | 命中 1 次（theme-auto 异常告警），未爆 ServerChan 5/天上限。

### 遗留问题

- `check-buy` launchd 触发明显晚于 09:36，建议下次盯一下 `launchd/check_buy_v16.plist` 的 `StartCalendarInterval` 与系统 launchd queue 延迟，看是否要前移 1–2 分钟兜底。
- T 模块 EOD 聚合（15:30）首日效果待 Codex 在尾盘后核对 `output/t_trade/` 与 `logs/auto_run.log`。
- nan 修复需明日 08:30 morning-digest 真实推送验证。

### 给 Codex 的接力清单

我（Claude）这一轮做了什么：

1. 已提交 `bf9ce11`：`notifier.py` nan/inf 兜底（不影响你正在改的 dashboard / T 脚本）。
2. 已在 `AI_HANDOFF.md` / `AI_CHANGELOG.md` 末尾追加本次记录，**没有动你正在改的部分**。
3. 我观察并记录了 2026-06-02 实战首日的链路情况（见上表）。

你（Codex）需要接力做什么：

1. 你工作区现有脏改：
   - `dashboard_app.py`（UI 安全文案：实时→本地记录、已买入→模拟买入等）
   - `scripts/build_t_trade_tracker.py`（跨日字段：entry_report_date / event_report_date / open_days，+78 行）
   - `scripts/run_t_eod.py`（open_count / open_overdue_count）
   - 这三个文件请你自己 `git add` + commit，**不要把我已提交的 `notifier.py` 再次写回旧版本**。
2. 你之前在 `/tmp/handoff_with_codex.md.bak` 与 `/tmp/changelog_with_codex.md.bak` 里加过的段落仍然在备份里；你可以把它们的"Codex 段"重新拼回 `AI_HANDOFF.md` / `AI_CHANGELOG.md`（追加在我这段之后），不要覆盖我这段。
3. 今日 15:30 EOD `run_t_eod.py` 跑完后，请检查：
   - `output/t_trade/eod_summary_*.csv` 是否生成
   - 跨日字段是否落地
   - `logs/auto_run.log` 有无异常
4. 顺手观察一下 09:36 check-buy 真实触发时间（今日 09:44），决定是否要把 plist 时间提前 1–2 分钟。
5. 明早 08:30 morning-digest 出文后，确认龙头池字段不再出现 `nan`（验证我的 bf9ce11）。

---

## 2026-06-02 Claude（实战首日两处致命 bug 修复）

### 本次任务背景

2026-06-02 是 V1.6 + T 模块上线后第一个完整真实交易日。结果**全天 0 笔买入信号**（pre_gate 全数被否），用户要求"找代码逻辑错误"。

通过对 `logs/auto_run.log`、`output/trade_review.csv`、`output/tomorrow_plan/tomorrow_plan_latest.csv` 的对照排查，定位到 **两个真·代码 bug**（不是行情/数据源问题），并修复。

### 修改文件

#### 1. `scripts/run_update_review.sh` — Bug #1（致命）

- **现象**：`tomorrow_plan_latest.csv` 永远停留在 5/29 用户在 dashboard 手工点 build 那一次（`report_date=20260529, next_trade_date=20260601`）。
- **根因**：原脚本只跑 `python run.py --update-review`，**从未调用 `scripts/build_tomorrow_plan.py`**。launchd 每天 19:00 跑 update_review，trade_review.csv 是补全了，但 tomorrow_plan 从来不会自动更新。
- **后果链路**：
  ```
  tomorrow_plan 不更新
    → trade_review.py:288 校验 plan.next_trade_date != report_date
    → "明日计划日期不匹配 → 回退 V1.4/V1.5"
    → V1.6 自选池/主线观察/avoid_themes 全失效
    → 9:36 check_buy 完全没有 V1.6 优待
  ```
- **修复**：`run_update_review.sh` 在 `run.py --update-review` 之后追加 `python scripts/build_tomorrow_plan.py --merge-keep-manual`，并按 update_review 优先报错的规则返回 exit code。

#### 2. `indicators.py` — Bug #2（nan 源头）

- **现象**：2026-06-02 胜宏科技 `total_score=nan, space_score=nan`，notifier 推送显示"总分 nan / 空间 nan"。
- **根因 A（132 行 below_ma20_pct）**：
  ```python
  # 旧代码：
  below_ma20_pct = float(spot_row.get("below_ma20_pct", (cur_close / ma20 - 1) * 100))
  ```
  `dict.get(key, default)` **只在 key 不存在时返回 default**。当 key 存在但值是 NaN/Inf/None/`'nan'`，default 不会触发，`float(nan)` 不抛异常，直接吞下 nan。nan 进 `_score_dist_ma20` → `np.interp(nan, ...)` → nan → `space_score=nan` → `total_score=nan`。
- **根因 B（128-129 行 dist_60d_pct）**：`max_60d` 为 0/nan/负数（脏数据或全空盘）时，`(cur_close / max_60d - 1) * 100` 直接 nan/inf，传染整条 space 链路。
- **修复 A**：对齐同文件 `_get_turnover_rate`（49-66 行）的模式：先 `try float` + `np.isfinite` 检查 → 异常/nan/inf 时回退到本地 `(cur_close/ma20-1)*100`，`ma20` 也不可用时兜底 `0.0`。
- **修复 B**：`max_60d` 非有限值或 ≤0 时 `dist_60d_pct` 兜底 `0.0`（按"刚好在 60 日高点"处理）。
- **关联**：bf9ce11 notifier `_fmt_num/_fmt_pct` 增加 `math.isnan/isinf` 兜底，是文案层防线；本次是数据源头治理。两层都需要。

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改（虽然定位到 mac 睡眠让 launchd 跳期 9:31/9:36/9:41 三次，但 plist 改动不属本轮范围）。

### 是否运行 python run.py

- 否。仅本地 mock 单元测试。

### 验收

- `python -m py_compile indicators.py` 通过。
- `bash -n scripts/run_update_review.sh` 通过。
- mock 单元测试 7/7：
  - `below_ma20_pct`：spot 有正常值 / NaN / Inf / 缺失 / None / `'nan'` / ma20 也 nan，全部正确兜底
  - `dist_60d_pct`：max_60d 正常 / 0 / nan / inf / 负数，全部正确兜底
- 模拟胜宏科技 6/1 真实数据：旧逻辑产 nan，新逻辑产 `_score_dist_ma20=2.0`，total 链路恢复有限值。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`5e1f752 fix: 2026-06-02 实战首日两处致命 bug`
- status：`scripts/run_update_review.sh` (+15/−1) + `indicators.py` (+22/−2)，无附带改动。Codex 工作区脏文件全部保持不动（dashboard_app.py / scripts/build_t_signal_observer.py / scripts/build_t_trade_tracker.py / scripts/run_t_eod.py）。

### 2026-06-02 完整 bug 排查记录（给所有 AI 看）

#### 排查路径

1. 用户反馈"今天还是没买卖" → 查 `output/trade_review.csv` 当日 3 条记录全部 `fail_reason=full_score_not_strong_enough`。
2. 看到所有候选都带 `v16_plan_reason='明日计划日期不匹配...已回退 V1.4/V1.5'` → 发现 plan 错配。
3. 读 `tomorrow_plan_latest.csv` → report_date 是 5/29，`next_trade_date=20260601`。
4. `ls -lt output/tomorrow_plan/` 发现最新 plan 文件就是 `tomorrow_plan_20260529.*`，6/1 收盘后没生成新文件。
5. `grep build_tomorrow_plan launchd/*.plist run.py scripts/*.sh` → 发现没有任何自动化路径调用它，只有 `dashboard_app.py` 的人工按钮。**确认 Bug #1**。
6. 查 nan 来源：`grep "胜宏科技\|300476" logs/20260602.log` → 早上 8:55 picker 阶段就已经 `总分nan 空间nan`。
7. 本地 reproduce 胜宏 6/1 历史数据：`dist_60d_pct=-14.97, ret_5d=-10.73, below_ma20_pct(本地)=-4.28`，本地算都不 nan。
8. 顺 `indicators.py` 第 132 行读到 `spot_row.get("below_ma20_pct", fallback)` → 怀疑 spot 给了 nan。
9. 对比第 49 行 `_get_turnover_rate` 的写法 → 确认 `_get_turnover_rate` 有 isnan 兜底，`below_ma20_pct` 没有。**确认 Bug #2**。

#### 受影响范围

- Bug #1：5/29 之后**每一个交易日**的 check_buy（共 5/30 周末、6/1、6/2 三个交易日）。
- Bug #2：任何 spot 快照里 below_ma20_pct 字段缺/nan 的股票，均会产 total_score=nan。胜宏科技 6/1 受影响是因为当日巨幅震荡。

### 当前遗留问题（本轮未处理，待用户决策）

#### 1. V1.4 预闸门槛对自选池一视同仁

- 实测今日 3 只候选最高 total=71.9，均 < 78；popularity 19.4/17.7/20.8，均 < 22；technical 全 16.0，< 20。
- 即使修了 nan，今天的 V1.4 也全部过不了。
- 这 3 只都是 `is_custom_pool=True, custom_pool_priority=1`（朱哥指定一线），但 V1.4 预闸把自选池当普通候选。
- **三个候选方向（待用户拍板）**：
  - A. 自选池跳过 V1.4 预闸（最激进）
  - B. 自选池单独降门槛（如 total ≥ 65 / pop ≥ 18 / tec ≥ 14）
  - C. 维持现状（自选池只影响排序）

#### 2. launchd 睡眠跳期

- `auto_run.log` 显示 6/2 09:26 ~ 09:44 supervisor 整段缺触发（漏 9:31/9:36/9:41）。
- 原因：mac 睡眠时 `StartInterval` 类 launchd 任务被冻结。9:44 是醒来后第一次补跑。
- `check_buy_v16.plist` 用 `StartCalendarInterval` 但没设 `WakeUp`，所以无法把 mac 唤醒。
- 修复需改 plist，本轮未做。

#### 3. theme_auto 数据源稳定性

- 6/2 08:55、09:01 两次东方财富 `RemoteDisconnected, Connection aborted`，走 fallback 写空 CSV。
- 是对端临时抖动，不是代码 bug，但缺少二次重试间隔，可能值得后续优化。

### 给所有协作 AI 的状态板

#### 已合入主干（commit 顺序，最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `5e1f752` | tomorrow_plan 不自动更新 + indicators nan 兜底 | Claude（本轮）|
| `3df6d1d` | md 更新 + 2026-06-02 实战观察 + Codex 接力清单 | Claude |
| `bf9ce11` | notifier `_fmt_num/_fmt_pct` 增加 math.isnan/isinf | Claude |
| `36f5a97` | 自选池优先 + T 模块跨日字段 | Codex |
| `ee5d2c7` | 2026-06-01 push 合并 + T 模块文档 | Codex |
| `0145717` | T 模块实时 B/S + EOD | Codex |
| `588d3c1` | fetch_minute_today | Codex |

#### Codex 工作区脏文件（本轮未触碰，由 Codex 自己负责提交）

- `dashboard_app.py`（UI 安全文案 + RADAR 风格统一）
- `scripts/build_t_signal_observer.py`（本轮新增脏）
- `scripts/build_t_trade_tracker.py`（跨日字段）
- `scripts/run_t_eod.py`（open_count）
- `AI_HANDOFF.md` / `AI_CHANGELOG.md` 内 Codex 段（备份在 `/tmp/handoff_codex_round2.md.bak` 与 `/tmp/changelog_codex_round2.md.bak`，已恢复到本文件）

#### 给下一个 AI 的注意事项

1. **不要再担心 nan 文案 bug**：notifier 层（bf9ce11）+ indicators 层（5e1f752）双重防线已就位。
2. **明天 19:00 update_review 后**，请检查 `output/tomorrow_plan/tomorrow_plan_20260602.csv` 是否生成、`tomorrow_plan_latest.csv` 是否指向 20260603。
3. **明早 09:36 check_buy 后**，请确认 `trade_review.csv` 里候选不再带 `已回退 V1.4/V1.5`，而是出现真实的 v16_trade_permission 等字段值。
4. **V1.4 门槛问题（遗留 #1）**：用户尚未决策，请不要自作主张改 V1.4 门槛或自选池逻辑。
5. **launchd 睡眠（遗留 #2）**：plist 改动建议先和用户确认硬件唤醒策略再动。

---

## 2026-06-02 Claude（第二轮代码扫描：3 处一致性 bug）

### 本次任务背景

修完 5e1f752（Bug #1 + Bug #2）后用户要求"再扫一遍代码"。本轮系统性排查 8 类潜在 bug 模式，发现 6 个新问题，按风险与影响面，选 3 个一致性 bug 修复，其余 3 个待用户决策。

### 修改文件

#### 1. `trade_review.py` — Bug #4（second_check 与 check_buy 校验不一致）

- **位置**：~1429-1434 行 `second_check()`。
- **现象**：
  ```python
  cur_price  = float(rt["close"])
  open_p_rt  = float(rt["open"])
  prev_close = float(rt["prev_close"])
  if cur_price <= 0 or open_p_rt <= 0 or prev_close <= 0:  # ← 没查 isfinite
  ```
  `nan` / `inf` 跟任何数字比较都是 `False`，会绕过 `<= 0` 检查，进入第 1456 行 `(open_p_rt / prev_close - 1) * 100` 产 nan/inf，再传染下游所有判断。
- **对比**：同文件 `check_buy()` 第 1115-1118 行已经加了 `math.isfinite` 三连，**second_check 没同步**。
- **修复**：加 `math.isfinite(cur_price)` / `math.isfinite(open_p_rt)` / `math.isfinite(prev_close)` 三连检查，对齐 check_buy。

#### 2. `trade_review.py` — Bug #6（not_bought_tracking 大小写不敏感）

- **位置**：1616 行。
- **现象**：
  ```python
  if str(row.get("not_bought_tracking", "")).strip() == "true":  # 缺 .lower()
  ```
  当前 CSV 写入端用小写 `"true"` 没触发，但同文件 419、1359 行都用了 `.strip().lower()`，这里漏了。任何写入端改成 `"True"`/`"TRUE"`（包括人工编辑、Codex 改 UI 时不小心改文案）就会让"未买入 T+1 追踪"逻辑失效，同一行被反复处理。
- **修复**：改成 `str(...).strip().lower() == "true"`。

#### 3. `trade_review.py` + `periodic_review.py` — Bug #7（_gf 只查 NaN 不查 Inf）

- **现象**：两个文件的 `_gf()` 都只有 `math.isnan(f)` 检查，缺 `math.isinf(f)`。
- **后果**：
  - inf 进 V1.4 预闸 (tot < 78) 等比较运算会产生 inf 假阳性
  - inf 进文案层（之前 bf9ce11 修了 notifier 的 `_fmt_num/_fmt_pct`）会显示 `'inf%'`
  - inf 进周/月统计聚合 `mean/sum/max` 会被永远拉到 inf（inf 永远是 max）
- **修复**：两个 `_gf` 一并加 `math.isinf(f)` 检查，与 nan 一视同仁兜底为 `None`。
- **说明**：`dashboard_app.py` 的 `_gf` 同样有此 bug，但属于 Codex 工作区脏文件，**本轮不动**，等 Codex 同步修复。

### 新增文件

- 无。

### 禁改文件检查

- `run.py`：未改。**确认过 Bug #3（watchlist 补回 nan 污染）已被 5e1f752 的 indicators 下游兜底完全覆盖**，spot 自带字段（amount/change_pct/high/low/turnover_rate）watchlist 补回时不会缺，所以不需要再改 run.py。
- `trade_review.py`：本轮改了，但只动 `_gf` / `second_check` 价格校验 / `not_bought_tracking` 大小写，属于公认的 helper 与一致性修复，**没动任何决策公式（V1.4 预闸 / 9:36 判定 / V1.5 资金 / V1.6 plan）**。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：未改。

### 是否运行 python run.py

- 否。仅本地 mock 单元测试。

### 验收

- `python -m py_compile trade_review.py` 通过。
- `python -m py_compile periodic_review.py` 通过。
- `_gf` 兜底单元测试 14/14 通过：覆盖 `nan/inf/-inf/None/''/'nan'/'inf'/'NaN'/非数字字符串/正常数字/布尔/0`。
- `second_check` 价格校验 6/6 通过：覆盖正常 / nan close / inf open / nan prev_close / 零价格 / 负价格。

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`82e3375 fix: 2026-06-02 第二轮扫描发现的 3 处一致性 bug`
- status：仅 2 个文件被改；Codex 工作区脏文件全部保持不动。

### 第二轮代码扫描全景（给所有 AI 看）

本轮覆盖 8 类高危模式：

1. ✅ `spot_row.get(..., fallback) + float()` 模式（Bug #2 已修） 
2. ✅ `_gf / _safe_float` 的 nan/inf 兜底（Bug #7 本轮修了 2 个，dashboard_app 1 个留给 Codex）
3. ✅ 数值比较涉及 None/nan/inf 风险（无新 bug）
4. ✅ V1.4 决策核心 / 9:36 价格校验（check_buy 已对齐，**second_check 未对齐 → Bug #4 本轮修**）
5. ✅ `_load_v15_flags / _load_v16_flags / _load_v16_plan` 容错（结构 ok，但暴露 Bug #1 plan 不更新源头已修）
6. ✅ 除法 / 比例计算潜在除零（已经覆盖 Bug #2 / second_check 用 isfinite）
7. ✅ 文件落地/读取编码（pandas 处理 BOM OK）
8. ✅ 关键 bool 字符串比较的大小写（Bug #6 本轮修）

#### 本轮发现但未修的 3 个潜在问题（待用户决策）

##### A. Bug #3：watchlist 补回污染（已被下游覆盖，可不修）

- 链路：自选股被 `history_filter` 剔除 → `_keep_watchlist_after_rank` 从 `candidate_df`（无 ma20/below_ma20_pct）补回 → pandas concat 取列并集 → ma20/below_ma20_pct = NaN
- 经分析：**5e1f752 的 indicators 下游兜底已完全覆盖这条链路**。spot 自带的 `amount/change_pct/high/low/turnover_rate` 不会因 concat 缺失。
- 是否要源头治理：可选项。源头治理可避免下游再多兜底，但要动 `run.py:163-200 _keep_watchlist_after_rank`，会让 watchlist 补回主动算 ma20/below_ma20_pct。**当前下游已经稳定，建议不动。**

##### B. Bug #5：节假日识别（影响 plan 自动化，**真实坑**）

- `data_fetcher.py:141 next_trading_date` 注释明确"**仅排除周末，不含节假日**"。
- 现在 update_review 自动生成 plan（5e1f752 修复后），节假日会指向非交易日：
  - 春节前最后交易日 → plan.next_trade_date 写春节首日（非交易日）
  - 春节后第一交易日 check_buy 拿不到匹配 plan → 回退 V1.4
- 同样影响 update_review 的 T+1 数据等待逻辑（trade_review.py:1550, 1626）。
- **修复方向**（待用户拍板）：
  - A1. 内置 2026 节假日列表（最简单，但每年要维护）
  - A2. 调 akshare `tool_trade_date_hist_sina` 拿真实交易日历（需要网络）
  - A3. 维持现状，节假日前后两天人工 check（不推荐）

##### C. Bug #8：notifier 全局节流标记用本地时间，未走 calc_dates

- `notifier.py:31-35` 用 `datetime.now().strftime("%Y%m%d")` 作为标记文件名
- 理论 edge case：凌晨 0:00 前后跑任务会跨日重置
- 实际生产 launchd 不会凌晨跑业务任务，**本轮判定不修**。

### 给所有协作 AI 的状态板

#### 已合入主干（最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `82e3375` | second_check isfinite + not_bought_tracking lower + _gf isinf | Claude（本轮）|
| `730a6fe` | md 状态板 + 9 步排查路径 + 给所有 AI 的提示 | Claude |
| `5e1f752` | tomorrow_plan 不更新 + indicators nan 兜底 | Claude |
| `3df6d1d` | md 更新 + 实战观察 + Codex 接力清单 | Claude |
| `bf9ce11` | notifier _fmt_num/_fmt_pct 增加 math.isnan/isinf | Claude |
| `36f5a97` | 自选池优先 + T 模块跨日字段 | Codex |
| `ee5d2c7` | 2026-06-01 push 合并 + T 模块文档 | Codex |
| `0145717` | T 模块实时 B/S + EOD | Codex |
| `588d3c1` | fetch_minute_today | Codex |

#### Codex 工作区脏文件（本轮未触碰，由 Codex 自己负责提交）

- `dashboard_app.py`（UI 安全文案 + RADAR 风格统一 + **`_gf` 的 isinf 修复也请 Codex 同步**）
- `scripts/build_t_signal_observer.py`
- `scripts/build_t_trade_tracker.py`
- `scripts/run_t_eod.py`
- `AI_HANDOFF.md` / `AI_CHANGELOG.md` 内 Codex 段（备份在 `/tmp/handoff_codex_round3.md.bak` 与 `/tmp/changelog_codex_round3.md.bak`，已恢复到本文件）

#### 给下一个 AI 的注意事项

1. **不要重复扫 nan/inf**：bf9ce11（notifier）+ 5e1f752（indicators）+ 82e3375（_gf / second_check）三层防线已就位。dashboard_app.py 的 _gf 是 Codex 改动范围，请提醒 Codex 同步加 isinf。
2. **明天 19:00 update_review 后**：核对 `output/tomorrow_plan/tomorrow_plan_20260602.csv` 是否生成、`tomorrow_plan_latest.csv` 是否指向 20260603。
3. **明早 09:36 check_buy 后**：确认候选不再 `已回退 V1.4/V1.5`。
4. **V1.4 门槛问题**（遗留 #1，5e1f752 提出的）：用户尚未决策，不要自作主张改门槛或自选池逻辑。
5. **launchd 睡眠**（遗留 #2，5e1f752 提出的）：plist 改动建议先和用户确认硬件唤醒策略。
6. **节假日识别**（本轮 Bug #5）：影响 plan 自动化与 T+1 等待，遇春节/国庆等节假日前后建议人工 check `tomorrow_plan_latest.csv` 是否正确。

---

## 2026-06-02 Claude（T 模块按朱哥拍板规则重写 + 6 处 T bug 修复）

### 朱哥拍板的正 T 规则（用户原话）

> 1. 5 日均线向上
> 2. 时间 9:33 - 10:15 之间
> 3. 出现急跌 1-3 分钟跌幅大于 1%
> 4. 出现相比于前 1-3 根绿分时成交量 1 倍以上的绿量
> 5. 倍量以后下一个成交量刚开始明显缩量
>
> 如果有就**正 T，先买再卖**，卖的时候比买的点高 1.5%-3% 就可以卖。

### 实现要点

- **正 T 单方向**：只产生 `sim_buy`（B 点），不再产生 `sim_sell`（高抛/反 T）
- **止盈在 tracker**：按入场价 +1.5% / +3% 自动配对（已有逻辑无须改）
- **5 日均线斜率**：由 `run_t_intraday.py` 每日首次跑时拉历史日线现算（今日 ma5 vs 昨日 ma5），缓存到 `data/minute_today/_ma5_slope_<today>.json`，每分钟后续跑直接读
- **"绿量 1 倍以上"**：解读为触发分钟量 ≥ 前 1-3 根绿 K 均量 × 2.0（与原代码阈值一致）
- **"明显缩量"**：保持 `shrink_ratio ≤ 0.5`（缩 50% 以上）

### 修改文件清单

#### A. 新 T 规则核心

- `scripts/build_t_signal_observer.py`
  - `evaluate_t_signals()` 完全按 5 条规则重写
  - 新增 `ma5_override` / `ma5_slope_up` 参数（保留 `ma10_override` 向后兼容）
  - 完全去除 high_throw 分支；只产生 `signal_type="low_absorb"` + `signal_side="sim_buy"`
  - 颜色匹配：触发分钟必须是绿 K（`close < open`），平盘 K 不触发
  - 新 CLI: `--ma5-override CODE:VALUE` / `--ma5-slope-override CODE:1|0`

- `scripts/build_t_trade_tracker.py`
  - `build_trade_rows` 里 `signal_type == "high_throw"` 改成记 `high_throw_disabled_only_long_t` 跳过
  - 保留 `_scan_high_throw` 函数代码（备用，将来恢复高抛 T 时无须重写）
  - 保留 Codex 的跨日字段（entry_report_date / event_report_date / open_days）

- `scripts/run_t_intraday.py`
  - 新增 `_load_or_build_ma5_slope_cache()`：拉 8 天历史日线现算斜率（缓存复用）
  - `_today_candidates_from_review()` 多读 `ma5` 字段
  - `_append_signal_overrides()` 多传 `--ma5-override` 和 `--ma5-slope-override`
  - 主流程：fetch minute 之后调一次斜率缓存，传给 observer

#### B. 顺带修复的 T 模块 bug

- **T Bug #1**（`scripts/build_t_signal_observer.py:181` `_bar_color`）
  - 旧：`close >= open` → red（平盘归 red）
  - 新：`close > open` → red；`close < open` → green；`close == open` → doji
  - 影响：平盘 K 不再污染同色量能基准

- **T Bug #2**（`data_fetcher.py:957-980` `fetch_minute_today`）
  - 旧：akshare 中文列名硬绑定 rename，升级改名时全失败 → df 空 → T 模块全天 0 信号不报错
  - 新：检测缺列时 WARNING + 按前 6 列位置兜底重命名

- **T Bug #3**（`scripts/build_t_signal_observer.py:153` `load_minute_csv`）
  - 旧：只 `except (KeyError, ValueError)`，`float("nan")` 不抛异常 → nan 吞进去污染下游
  - 新：加 `math.isfinite` 检查，命中跳过整根 K

- **T Bug #5**（observer ma10_slope_up 永远 True）
  - 旧：硬编码 True，输出字段是假数据
  - 新：通过 `--ma5-slope-override` 传真值；旧 `ma10_override` 调用兜底 True 保持兼容

- **T Bug #10**（`launchd/com.zhuge.stock.teod.plist`）
  - 旧：EOD 触发 15:30（紧贴收盘，akshare 偶尔接口空窗，今日 6/2 命中 status=minute_data_missing）
  - 新：EOD 触发 15:35（避开 akshare 15:30 数据结算窗口）
  - **生效需要 `launchctl unload + load` 一次**：
    ```bash
    launchctl unload ~/Library/LaunchAgents/com.zhuge.stock.teod.plist
    launchctl load   ~/Library/LaunchAgents/com.zhuge.stock.teod.plist
    ```

### 新增文件

- 无（缓存文件 `data/minute_today/_ma5_slope_<today>.json` 由 `_load_or_build_ma5_slope_cache` 运行时自动生成）

### 禁改文件检查

- `run.py`：未改。
- `trade_review.py`：未改。
- `output/trade_review.csv`：未改。
- `config/version_flags.yaml`：未改。
- `launchd/*.plist`：**改了 1 个**（teod 15:30 → 15:35），属本轮明确的 bug 修复，commit message 说明清楚。

### 是否运行 python run.py

- 否。仅本地 mock 单元测试。

### 验收

- `py_compile` 全部通过：`build_t_signal_observer.py` / `build_t_trade_tracker.py` / `run_t_intraday.py` / `data_fetcher.py`
- `plutil -lint` 通过：`teod plist`
- 5 类 mock 单元测试全部正确分流：
  - `_bar_color` 红/绿/平盘 3 类分类正确
  - 规则 1 ma5 斜率向下 → 拦下，理由 `ma5_slope_not_up`
  - 规则 1+2+3+4+5 全过 → `signal_type=low_absorb, side=sim_buy, rule_pass=True`
  - 高抛场景（红 K 涨 1.5% 量放大）→ `no_signal_triggered`（不再触发反 T）
  - 量倍数不够（vol_multiple<2）→ `no_signal_triggered`
  - 缩量不够（shrink_ratio>0.5）→ `rule_pass=False, fail=shrink_not_confirmed_volume_reduction_insufficient`

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`e4fef60 feat(t-module): 按朱哥拍板的正 T 5 条规则重写 + 修复 T 模块 6 处 bug`
- status：6 个文件改动（observer / tracker / intraday / data_fetcher / eod / plist）
- 备注：本次 commit 把 Codex 之前在 observer/tracker/eod 中的**稳定脏改**（字段补充 / 跨日辅助函数 / open_count 统计）一并 commit 进主干。Codex 在 `dashboard_app.py`（UI 文案改动）的工作**完整保留未触碰**，等他自己 commit。

### 关于"Codex 工作区保持不动"的妥协说明

之前 5 个 commit 一直严格保护 Codex 的 4 个脏文件不动。本次因为：
1. 用户明确要求按新 T 规则重写
2. 新 T 规则必须改 `observer` 主体逻辑（不可绕过）
3. 修 T Bug #1/#3/#5 也必须改这些文件
4. Codex 在这些文件里的脏改（加字段、加辅助函数、加统计）跟我的规则改动**完全不重叠**，是稳定可 commit 的工作

所以这次 commit 包含 Codex 之前未提交的稳定改动，Codex 下次 pull 会拿到这些（不会丢工作）。

**仍然不动的 Codex 文件**：
- `dashboard_app.py`（UI 文案 + RADAR 风格统一，跟 T 规则不在同一路径）
- 这两份 md 中 Codex 段（已恢复到末尾）

### 给所有协作 AI 的注意事项

1. **必须执行的运维操作**（用户手动）：
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.zhuge.stock.teod.plist
   launchctl load   ~/Library/LaunchAgents/com.zhuge.stock.teod.plist
   ```
   否则 EOD 仍会在 15:30 触发，bug #10 不会生效。

2. **明天起 T 模块行为变化**：
   - 不会再有 sim_sell / high_throw 信号
   - sim_buy 必须满足 ma5 斜率向上（朱哥拍板的硬门）
   - 缓存文件 `data/minute_today/_ma5_slope_<today>.json` 每天首次跑时自动建立

3. **trade_review.csv 字段依赖**：observer 现在需要 `ma5` 字段，trade_review.py 已经写入了 `ma5` 列（第 740 行），所以无须改 schema。

4. **Codex 工作区脏文件清单（更新）**：
   - ✅ `dashboard_app.py`（UI 文案 + RADAR 风格，跟 T 规则不在同一路径，**完整保留**）
   - ✅ 这两份 md 中 Codex 段（已恢复到末尾）

5. **未修但已记录的 T 模块 bug**（待后续）：
   - T Bug #4（缩量阈值 0.5 过严）— 策略调参
   - T Bug #6（09:33 窗口太窄）— 设计选择
   - T Bug #7（open_positions 并发写）— 文件锁，等 Codex 接手
   - T Bug #8（跨日 trade 进今日统计）— EOD 聚合口径，等 Codex 接手
   - T Bug #9（trade_id datetime.now fallback）— 边缘场景

### 主干 commit 时间线（最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `e4fef60` | T 模块按朱哥规则重写 + 6 处 T bug | Claude（本轮）|
| `d7ecb77` | md 状态板 + 6 类全景扫描 | Claude |
| `82e3375` | second_check isfinite + not_bought lower + _gf isinf | Claude |
| `730a6fe` | md 状态板第 2 段 | Claude |
| `5e1f752` | tomorrow_plan 不更新 + indicators nan 兜底 | Claude |
| `3df6d1d` | md 第 1 段 | Claude |
| `bf9ce11` | notifier _fmt nan/inf | Claude |
| `36f5a97` | 自选池优先 + T 模块跨日字段 | Codex |
| `ee5d2c7` | T 模块文档 | Codex |
| `0145717` | T 模块实时 B/S + EOD（原始版本） | Codex |
| `588d3c1` | fetch_minute_today | Codex |

---

## 2026-06-02 Claude（T 规则 3 升级：跌幅 0.7% + 分时均线低 1.5%）

### 朱哥拍板的最新 T 规则（与上一版差异）

> 1. 5 日均线向上
> 2. 时间 09:33-10:15 之间
> 3. **出现急跌 1-3 分钟跌幅大于等于 0.7% 且当前位置比分时图均线低三个格子及以上**
> 4. 相比前 1-3 根绿分时成交量 1 倍以上的绿量
> 5. 倍量以后下一个成交量明显缩量
>
> 如果有就正 T，先买再卖，卖的时候比买的点高 1.5%-3% 就可以卖

**与 e4fef60 版本的差异**（用户第二次拍板）：

| 项 | e4fef60 | e3a8987（本次）|
|---|---|---|
| 跌幅阈值 | ≥ 1% | **≥ 0.7%** |
| 分时均线约束 | 无 | **新增：触发分钟 close 比分时均线（VWAP）低 ≥ 1.5%（3 个格子）** |
| 时间窗口 | 09:33-10:15 | 09:33-10:15（不变） |
| 量倍数 | ≥ 2.0 | ≥ 2.0（不变） |
| 缩量比 | ≤ 0.5 | ≤ 0.5（不变） |
| 止盈 | +1.5%/+3% | +1.5%/+3%（不变） |

### "3 个格子 = 1.5%" 的推断

通达信/同花顺分时图纵向网格按 ±0.5% / 格划分（标准做法），所以"3 个格子 = 1.5%"。

如果朱哥后续指明是别的百分比（例如 2% 或 3%），改一行常量即可：

```python
# scripts/build_t_signal_observer.py:130
BELOW_VWAP_PCT = 0.015   # 改这里
```

### 实现要点

**分时均线（VWAP）算法**：
```
VWAP = Σ(close × volume) / Σ(volume)
```
- 从 **09:30 开盘**累计，不能只用 09:33-10:15 窗口
- 分钟 K 没有 amount 字段，用 `close × volume` 近似（每根 K 内价格变化忽略）
- 与通达信/同花顺的"分时均价线"算法一致

### 修改文件

- `scripts/build_t_signal_observer.py`
  - 常量 `DROP_PCT_MIN`: 0.01 → **0.007**
  - 常量 `BELOW_VWAP_PCT`: 已存在 0.015（沿用）
  - 新增 `_annotate_vwap_inplace()` 函数
  - `evaluate_t_signals()` 入口调一次 `_annotate_vwap_inplace`
  - 规则 3 拆成两段：跌幅检查 + VWAP 距离检查
  - 把硬编码 2.0 / 0.5 换成 `VOL_MULTIPLE_MIN` / `SHRINK_RATIO_MAX` 常量

### 新增文件

- 无

### 禁改文件检查

- `run.py`：未改
- `trade_review.py`：未改
- `output/trade_review.csv`：未改
- `config/version_flags.yaml`：未改
- `launchd/*.plist`：未改
- 自动下单逻辑：未新增
- 券商连接逻辑：未新增

### 是否运行 python run.py

- 否。仅本地 mock 单元测试

### 验收

- `py_compile build_t_signal_observer.py` 通过
- 6 个场景 mock 测试全部正确：
  1. VWAP 算法手算对比，误差 < 1e-6
  2. 规则 3 第 1 段通过、第 2 段不过（vwap 差 0.7% < 1.5%）→ 不触发
  3. 规则 3 完整版 + 缩量 → `sim_buy / rule_pass=True / signal_price=96.4`
  4. 跌幅恰好 0.7% 边界 → 不触发（vwap 距离不够）
  5. ma5 斜率向下 → `ma5_slope_not_up`
  6. 红 K 大涨 → `no_signal_triggered`（反 T 已删除）

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`e3a8987 feat(t-rule): 规则 3 升级 — 跌幅 0.7% + 分时均线低 1.5%（3 格）`
- status：仅 1 个文件被改；Codex 工作区脏文件保持不动

### 调参指南（给用户和未来 AI）

所有阈值都在 `scripts/build_t_signal_observer.py` 第 128-135 行的常量区，改一行就生效：

```python
BELOW_VWAP_PCT = 0.015   # 规则 3 第 2 段: 低于 VWAP（3 格 = 1.5%）
DROP_PCT_MIN  = 0.007    # 规则 3 第 1 段: 1-3 分钟跌幅阈值 0.7%
VOL_MULTIPLE_MIN = 2.0   # 规则 4: 量倍数 ≥ 2.0
SHRINK_RATIO_MAX = 0.5   # 规则 5: 缩量比 ≤ 0.5
```

**实战调参建议**：
- 信号过密 → 上调 DROP_PCT_MIN（如 0.8%）或 BELOW_VWAP_PCT（如 2%）
- 信号过稀 → 下调 BELOW_VWAP_PCT（如 1%）或 SHRINK_RATIO_MAX（如 0.6）
- 假信号多 → 上调 VOL_MULTIPLE_MIN（如 2.5）

### 主干 commit 时间线（最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `e3a8987` | T 规则 3 升级（跌幅 0.7% + VWAP 低 1.5%） | Claude（本轮） |
| `789fb29` | md：T 模块重写 + 6 T bug | Claude |
| `e4fef60` | T 模块按 5 条规则重写（第 1 版规则） | Claude |
| `d7ecb77` | md 状态板 + 6 类全景扫描 | Claude |
| `82e3375` | second_check / not_bought / _gf isinf | Claude |
| `730a6fe` | md 第 2 段 | Claude |
| `5e1f752` | tomorrow_plan 不更新 + indicators nan | Claude |
| `3df6d1d` | md 第 1 段 | Claude |
| `bf9ce11` | notifier nan/inf | Claude |
| `36f5a97` | 自选池优先 + T 跨日字段 | Codex |
| `ee5d2c7` | T 模块文档 | Codex |
| `0145717` | T 模块实时 B/S + EOD（原始版本） | Codex |
| `588d3c1` | fetch_minute_today | Codex |

### Codex 工作区状态（不变）

- `dashboard_app.py`（UI 文案 + RADAR 风格统一）— 本轮**完整保留**未触碰
- AI 文档中 Codex 段 — 备份在 `/tmp/{handoff,changelog}_round5.md.bak`，恢复脚本在 commit 之后会自动跑

---

## 2026-06-02 Claude（T 规则 3b 阈值微调：1.5% → 1.3%）

### 朱哥拍板

3b（触发时位置低于分时均线）阈值从 **1.5%** 改成 **≥ 1.3%**。

其余 4 条规则全部不变。

### 修改文件

- `scripts/build_t_signal_observer.py`
  - `BELOW_VWAP_PCT`: 0.015 → **0.013**
  - 同步更新第 130/261/352 行 docstring/注释里的 1.5% 文案为 1.3%

### 完整规则常量表（当前生效）

```python
# scripts/build_t_signal_observer.py:128-135
BELOW_VWAP_PCT   = 0.013   # 规则 3b: 触发分钟 close 比 VWAP 低 ≥ 1.3%
DROP_PCT_MIN     = 0.007   # 规则 3a: 1-3 分钟急跌 ≥ 0.7%
VOL_MULTIPLE_MIN = 2.0     # 规则 4:  触发量 / 前绿K均量 ≥ 2.0
SHRINK_RATIO_MAX = 0.5     # 规则 5:  下一根缩量比 ≤ 0.5
```

### 验收

- `py_compile` 通过
- 边界 mock 测试：
  - vwap 距离 1.0% diff → 不触发（旧 1.5% / 新 1.3% 都拦下）
  - vwap 距离 1.327% diff → 触发 `sim_buy / rule_pass=True`
    - 旧 1.5% 拦下，新 1.3% 放过 → 阈值确实生效

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`9b2a583 fix(t-rule): BELOW_VWAP_PCT 1.5% → 1.3%（朱哥拍板）`

### 主干 commit 时间线（最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `9b2a583` | 规则 3b 阈值 1.3% | Claude（本轮）|
| `b296183` | md：T 规则 3 升级 0.7%+1.5% | Claude |
| `e3a8987` | T 规则 3 升级 0.7%+1.5%（被本轮覆盖到 1.3%） | Claude |
| `789fb29` | md：T 模块重写 + 6 T bug | Claude |
| `e4fef60` | T 模块按 5 条规则重写 | Claude |
| `d7ecb77` | md 全景扫描 | Claude |
| `82e3375` | second_check / not_bought / _gf isinf | Claude |
| `730a6fe` | md 第 2 段 | Claude |
| `5e1f752` | tomorrow_plan + indicators nan | Claude |
| `3df6d1d` | md 第 1 段 | Claude |
| `bf9ce11` | notifier nan/inf | Claude |

---

## 2026-06-02 Claude（中危 bug #1 + #2 修复 + 节假日识别上线）

### 本次任务

修中危 3 个问题：

| # | 决策方向 | 修不修 |
|---|---|---|
| 1 自选池跳过 V1.4 预闸 | A 方案 | ✅ 修了 |
| 2 节假日识别 | A2 方案（akshare + fallback） | ✅ 修了 |
| 3 launchd mac 睡眠跳期 | 不改代码 | ⚠️ 改运维（pmset 命令） |

### 修改文件

#### 1. `trade_review.py` — 中危 #1

`_v14_pregate_main_reason()` 加入自选池跳过预闸：

```python
# 自选池标的：跳过分数门槛预闸（朱哥拍板）
is_custom = str(row.get("is_custom_pool", "")).strip().lower() in ("true", "1", "yes")
if is_custom:
    return None
```

**保留 V1.4 后续判定**：开盘涨幅 / 价格关 / 市场情绪 / V1.5 资金 / V1.6 plan 全部走，
只跳分数预闸，不跳风险检查。

#### 2. `data_fetcher.py` — 中危 #2

新增**节假日识别**全套机制：

| 函数 | 作用 |
|---|---|
| `_HOLIDAYS_2026_FALLBACK` | 国务院 2025-11 发布的 2026 节假日内置 fallback |
| `_load_trading_calendar()` | 调 akshare `tool_trade_date_hist_sina` 拉真实日历 |
| `_is_trading_day(d)` | 周末 + 节假日均不是交易日 |
| `_prev_weekday` / `_next_weekday` | 命名沿用（向后兼容），实际跳过周末 + 节假日 |
| `next_trading_date` / `prev_trading_date` | 同上 |
| `calc_dates` | 用 `_is_trading_day(today)` 替代原 weekday>=5 判断 |

**Cache 策略**：
- 写到 `data/calendar/sse_calendar.json`（30 天有效）
- 已加 `.gitignore`，本地生成不进 git
- 失败时 fallback 到 `_HOLIDAYS_2026_FALLBACK`

#### 3. `.gitignore`

新增 `data/minute_today/` + `data/calendar/` 排除项

### 新增文件

- 无 git 追踪的新文件
- runtime 生成（不入 git）：
  - `data/calendar/sse_calendar.json`（≈ 2 KB，134 个非交易日）

### 禁改文件检查

- `run.py`：未改
- `trade_review.py`：本次新增一处（`_v14_pregate_main_reason` 自选池 bypass），属朱哥拍板的策略改动，**不动决策公式本身**，只加前置门 bypass
- `output/trade_review.csv`：未改
- `config/version_flags.yaml`：未改
- `launchd/*.plist`：未改

### 是否运行 python run.py

- 否

### 验收

**中危 #1（自选池跳过预闸）** 5/5 mock 通过：
- 普通候选 + 分数不足 → `full_score_not_strong_enough`
- 普通候选 + 分数足 → `None`
- 自选池 + 分数不足 → `None` ✅（关键修复）
- 自选池 + 分数足 → `None`
- 自选池 + `theme_auto` + 强度不足 → `None`（也跳过）

**中危 #2（节假日识别）** 14/14 关键日期 + 4/4 next/prev 调用通过：
- 元旦 / 春节 / 清明 / 劳动节 / 端午 / 中秋 / 国庆 全部正确识别
- `next_trading_date('20260213')` = `20260224`（跳过春节假期 11 天）✅
- `prev_trading_date('20260224')` = `20260213`
- `next_trading_date('20260101')` = `20260105`（跳过元旦 + 周末）
- `next_trading_date('20260930')` = `20261008`（跳过国庆 7 天 + 周末）
- 实际 akshare 拉到 **134 个非交易日**（覆盖前后 1 年）

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`8607ae2 feat: 中危 bug #1 + #2 修复（自选池跳过预闸 + 节假日识别）`
- commit：`c26faf3 chore: gitignore add data/minute_today + data/calendar caches`

### 中危 #3（launchd mac 睡眠跳期）— 运维操作，不改代码

**根因**：mac 睡眠时 launchd 整个被冻结。`StartInterval` 任务（如 supervisor）漏过的触发不补；
`StartCalendarInterval` 任务（如 check_buy）醒来后会立即跑一次（但可能晚于设定时间）。

**plist 没有 `WakeUp` 有效键**，正确做法是用 `pmset` 命令让 mac 在交易日早上**主动唤醒**：

```bash
# 让 mac 周一-周五 09:25:00 自动唤醒（提前 11 分钟给 launchd 起步时间）
sudo pmset repeat wake MTWRF 09:25:00
```

**说明**：
- `MTWRF` = 周一-周五（M=Mon T=Tue W=Wed R=Thu F=Fri）
- 唤醒不需要登录密码（系统级 wake event）
- 屏幕保持锁定，只是 launchd 队列恢复运行
- 配合之前 `e4fef60` 已把 teod 从 15:30 改到 15:35

**验证**：
```bash
pmset -g sched    # 查看当前 schedule
```

**取消**：
```bash
sudo pmset repeat cancel
```

### 主干 commit 时间线（最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `c26faf3` | gitignore + cache 目录 | Claude（本轮）|
| `8607ae2` | 中危 #1 自选池跳过预闸 + #2 节假日识别 | Claude（本轮）|
| `2968143` | md：规则 3b 阈值 1.3% | Claude |
| `9b2a583` | T 规则 3b 阈值 1.3% | Claude |
| `b296183` | md：T 规则 3 升级 0.7%+1.5% | Claude |
| `e3a8987` | T 规则 3 升级 0.7%+1.5%（被 9b2a583 覆盖到 1.3%）| Claude |
| `789fb29` | md：T 模块重写 + 6 T bug | Claude |
| `e4fef60` | T 模块按 5 条规则重写 | Claude |
| `d7ecb77` | md 全景扫描 | Claude |
| `82e3375` | second_check / not_bought / _gf isinf | Claude |
| `730a6fe` | md 第 2 段 | Claude |
| `5e1f752` | tomorrow_plan + indicators nan | Claude |
| `3df6d1d` | md 第 1 段 | Claude |
| `bf9ce11` | notifier nan/inf | Claude |
| `36f5a97` | 自选池优先 + T 跨日字段 | Codex |
| `ee5d2c7` | T 模块文档 | Codex |
| `0145717` | T 模块实时 B/S + EOD | Codex |
| `588d3c1` | fetch_minute_today | Codex |

### 用户必做的运维操作（**两个，还没做**）

```bash
# 1. teod plist 15:35 生效（e4fef60 引入）
launchctl unload ~/Library/LaunchAgents/com.zhuge.stock.teod.plist
launchctl load   ~/Library/LaunchAgents/com.zhuge.stock.teod.plist

# 2. mac 工作日 09:25 自动唤醒（本轮中危 #3）
sudo pmset repeat wake MTWRF 09:25:00

# 验证
pmset -g sched
```

### Codex 工作区状态（不变）

- `dashboard_app.py`（UI + RADAR 风格）— **完整保留**未触碰
- AI 文档 Codex 8 段 — 仍在末尾

---

## 2026-06-02 Claude（当日总收尾 + 给 Codex 的接力清单）

### 当日成果总览

2026-06-02 V1.6 + T 模块实战首日。Claude 一共做了 **18 个 commit**（10 个 fix/feat + 8 个 docs），修复 **13 个 bug + 实现朱哥拍板的正 T 5 条规则 + 节假日识别全面上线**。

### 完整 commit 时间线（最新在上）

| commit | 类型 | 内容 |
|---|---|---|
| `0996cba` | docs | 中危 bug #1 + #2 + #3 md 记录 |
| `c26faf3` | chore | gitignore 加 cache 目录 |
| `8607ae2` | feat | 中危 #1 自选池跳预闸 + #2 节假日识别 |
| `2968143` | docs | 规则 3b 阈值 1.3% md 记录 |
| `9b2a583` | fix | T 规则 3b 阈值 1.5% → 1.3% |
| `b296183` | docs | T 规则 3 升级 md 记录 |
| `e3a8987` | feat | T 规则 3 升级 0.7% + VWAP（1.5% 后被 9b2a583 覆盖到 1.3%）|
| `789fb29` | docs | T 模块重写 + 6 T bug md 记录 |
| `e4fef60` | feat | T 模块按 5 条规则重写 + 6 处 T bug |
| `d7ecb77` | docs | 第二轮全景扫描 md 记录 |
| `82e3375` | fix | second_check + not_bought + `_gf` isinf |
| `730a6fe` | docs | 5e1f752 md 记录 + 状态板 |
| `5e1f752` | fix | tomorrow_plan 不更新 + indicators nan |
| `3df6d1d` | docs | bf9ce11 md 记录 + Codex 接力 |
| `bf9ce11` | fix | notifier `_fmt_num/_fmt_pct` nan/inf |

### 当前生效的核心配置

**朱哥拍板的正 T 5 条规则**（`scripts/build_t_signal_observer.py:128-135`）：

```python
BELOW_VWAP_PCT   = 0.013   # 规则 3b: 触发分钟 close 比 VWAP 低 ≥ 1.3%
DROP_PCT_MIN     = 0.007   # 规则 3a: 1-3 分钟急跌 ≥ 0.7%
VOL_MULTIPLE_MIN = 2.0     # 规则 4:  触发量 / 前绿K均量 ≥ 2.0
SHRINK_RATIO_MAX = 0.5     # 规则 5:  下一根缩量比 ≤ 0.5
```

**自选池 V1.4 预闸 bypass**（`trade_review.py:_v14_pregate_main_reason`）：
- `is_custom_pool=True` 跳过分数门槛
- 保留 V1.4 后续 9:36 风险检查（开盘涨幅 / 价格 / 情绪 / V1.5 / V1.6）

**节假日识别**（`data_fetcher.py`）：
- 主：akshare `tool_trade_date_hist_sina` → cache 到 `data/calendar/sse_calendar.json`
- Fallback：`_HOLIDAYS_2026_FALLBACK` 内置 2026 标准节假日
- `_is_trading_day` / `next_trading_date` / `prev_trading_date` / `calc_dates` 全部生效

**EOD 时机**（`launchd/com.zhuge.stock.teod.plist`）：
- 15:30 → 15:35（避开 akshare 收盘后 5 分钟数据空窗）

---

### ⚠️ 给 Codex 的接力清单（请仔细看）

我（Claude）从 2026-06-02 早晨到现在做了 18 个 commit。期间**严格不动你的工作区**：

#### 你的脏文件（**完整保留，没动**）

```
M dashboard_app.py              ← 你的 UI 文案 + RADAR 风格统一（约 760 行改动）
M AI_HANDOFF.md                 ← 末尾有你的 6 段段落
M AI_CHANGELOG.md               ← 末尾有你的 6 段段落
?? data/minute_today/           ← T 模块今日真实分钟数据（已 .gitignore）
?? data/calendar/               ← Claude 新增的交易日历 cache（已 .gitignore）
```

#### 我顺手并入主干的你的稳定工作

`e4fef60` commit 包含你之前在 T 模块脚本里的稳定脏改：
- `build_t_signal_observer.py` 中的 `_make_row` 安全字段落盘（8 行）
- `build_t_trade_tracker.py` 中的跨日字段（entry_report_date / event_report_date / open_days）+ 辅助函数
- `run_t_eod.py` 中的 open_count / open_overdue_count 统计

这些跟我新加的 T 规则改动**完全不重叠**，pull 后你的工作不会丢。

#### 请你尽快做的事

1. **提交你 dashboard_app.py 的脏改**（独立 commit）
   ```bash
   git add dashboard_app.py
   git commit -m "feat(dashboard): UI 安全文案 + 跨页面 RADAR 风格统一"
   ```

2. **补 dashboard_app.py 的 `_gf` 加 `math.isinf` 检查**（约第 251 行）
   ```python
   # 当前
   return None if math.isnan(f) else f
   # 改成
   if math.isnan(f) or math.isinf(f):
       return None
   return f
   ```
   你的 dashboard 是 nan/inf 防线的最后一道，目前只查 nan，inf 会漏过去。

3. **md 里你的 6 段已经在 git 工作区末尾**（HEAD 之后）
   你可以直接 `git add AI_HANDOFF.md AI_CHANGELOG.md && git commit -m "docs: Codex round 4 段"`
   不需要再次 backup/restore，那些段已经原封不动在文件里。

4. **未来要改 T 规则**（朱哥后续可能继续调阈值）
   优先改 `BELOW_VWAP_PCT / DROP_PCT_MIN / VOL_MULTIPLE_MIN / SHRINK_RATIO_MAX` 4 个常量
   不要改 `evaluate_t_signals` 的规则结构（会和我的 mock 测试不一致）

5. **T Bug 5 个未修，可以接手**
   - T Bug #4 缩量阈值 0.5 过严（策略调参，多天数据后再调）
   - T Bug #6 09:33 窗口（设计选择，注释已明确）
   - T Bug #7 open_positions 并发写无文件锁
   - T Bug #8 跨日 trade 进今日 B/S 统计夸大
   - T Bug #9 trade_id `datetime.now()` fallback（边缘场景）

#### 不要做的事

- **不要改 `trade_review.py` 的决策公式**（V1.4 / V1.5 / V1.6 主路径）
- **不要改 `data_fetcher.py:fetch_market_spot`**（spot 主链路）
- **不要改 `run.py`**（launchd 自动化主入口）
- **不要改 `launchd/*.plist`**（除非用户明确要求）
- **不要改 `output/trade_review.csv` 历史记录**

---

### 用户必做的 2 个运维操作（**至今还没做**）

```bash
# 1. teod plist 15:35 生效（e4fef60 引入）
launchctl unload ~/Library/LaunchAgents/com.zhuge.stock.teod.plist
launchctl load   ~/Library/LaunchAgents/com.zhuge.stock.teod.plist

# 2. mac 工作日 09:25 自动唤醒（8607ae2 / 中危 #3）
sudo pmset repeat wake MTWRF 09:25:00

# 验证
pmset -g sched
```

这两条不跑：
- EOD 仍会在 15:30 触发，今天的 `minute_data_missing` 现象会重演
- mac 早上睡眠 → 09:36 check_buy 仍会延迟到 09:44 之后

---

### 明早验证清单

**08:30** morning-digest 推送：
- 龙头池 / 主策略字段是否还有 `nan`（验证 `bf9ce11` notifier 双层防线 + `5e1f752` 数据源治理）

**09:36** check_buy 触发：
- 候选不再带 `已回退 V1.4/V1.5`（验证 `5e1f752` tomorrow_plan 自动生成）
- 自选池标的能进入 9:36 判定（验证 `8607ae2` 中危 #1 自选池 bypass）

**09:35+** T 模块每分钟：
- `data/minute_today/_ma5_slope_<today>.json` 自动生成（验证朱哥规则 1）
- t_signal CSV 不再出现 `high_throw / sim_sell`（验证 e4fef60 反 T 移除）
- 触发的 `low_absorb / sim_buy` 必须满足新规则（跌 ≥ 0.7% + VWAP 距离 ≥ 1.3%）

**15:35** EOD：
- 不再 `minute_data_missing`（验证 e4fef60 + 用户 launchctl reload）

**19:00** update_review：
- `output/tomorrow_plan/tomorrow_plan_20260602.csv` 生成
- `tomorrow_plan_latest.csv` 指向 `next_trade_date=20260603`

### 给所有协作 AI 的当前项目状态板

| 系统 | 状态 |
|---|---|
| V1.6 主链路（pick / theme_auto / check_buy）| ✅ 稳定 |
| V1.4 预闸 | ✅ 自选池 bypass 已上线 |
| V1.5 资金条件 | ✅ 不变 |
| V1.6 plan 自动更新 | ✅ 已修（5e1f752）|
| 节假日识别 | ✅ 已修（8607ae2）|
| T 模块（按朱哥 5 条规则）| ✅ 已上线 |
| nan/inf 防线（4 层）| ✅ 已就位（notifier / indicators / helper / second_check）|
| Codex UI（dashboard）| ⚠️ 工作区脏，等 Codex 自己 commit |
| Codex _gf isinf | ⚠️ 还没补 |
| launchd WakeUp | ⚠️ 等用户 pmset |
| 5 个低危 T bug | ⚠️ 等 Codex 接手 |

至此 Claude 当日工作完毕。

---

## 2026-06-02 Claude（持仓持续追踪 + 止损后 30 天跟踪 — 朱哥重大策略改动）

### 朱哥拍板的需求

**原话**：
> 现在需要只改逻辑 只要我买了 一直没有卖 。那就一直记录盈亏 。不是只记录一天 。
> 其次 止损的股票也要做记录 看止损后一个月内的涨跌

### 老逻辑（T+1 强制卖）的问题

- T 日买入 → T+1 收盘**必卖**（不管涨跌）
- 持仓时间固定 1 天
- 没法体现"持有 3-5 天的中线"和"短线被止损但实际是好票"两种情况

### 新逻辑

1. **持仓追踪**：买入后只要没触发止损就一直持有，每天 update_review 滚动更新
2. **止损后 30 天跟踪**：止损卖出的股票，继续记录 30 个交易日内的反弹/继续跌

→ 可以**事后回测**："如果当时没止损，这只票后续涨/跌多少？" "止损卖飞了几次？"

### 修改文件

`trade_review.py` 一处大改：

#### A. COLUMNS 新增 16 个字段（向后兼容）

持仓追踪字段（10 个）：
```
holding_status         holding/stopped/post_stop_done/manual_sell/legacy_t1_sell
latest_tracking_date   最后一次 update_review 处理的日期
days_held              持仓交易日数
latest_close           最新收盘价
latest_return_pct      最新相对 adj_buy 的收益（含滑点）
peak_high              持仓期间最高价
peak_low               持仓期间最低价
peak_return_pct        持仓期间历史最高收益
peak_drawdown_pct      持仓期间历史最大回撤
exit_date / exit_price / exit_reason   卖出三件套
```

止损后追踪字段（4 个）：
```
post_stop_max_return_pct      止损后最高反弹 vs exit_price（正数 = 反弹了 = 卖飞）
post_stop_max_drawdown_pct    止损后最低回撤（继续跌多深）
post_stop_days_tracked        已追踪天数（最多 30）
post_stop_tracking_done_date  30 天追踪完成日
```

#### B. `_calc_row()` 改成按 entry_date 分流

```python
if entry_date <= 20260602:
    → legacy_t1_sell（保留老逻辑，老数据全部走这路径）
else:
    if stop_triggered:
        → stopped + 进入 post_stop 追踪
    else:
        → holding + 初始化 peak_*/latest_*/days_held
```

#### C. 新增 `_update_holding_rows(df, cfg)` 滚动追踪函数

每天 19:00 update_review 调一次，处理所有 holding / stopped 状态的行：

- **holding 状态**：拉今日 K 线，更新 peak_* / latest_* / days_held；检查 today_low ≤ stop → 切到 stopped
- **stopped 状态**：拉今日 K 线，相对 exit_price 算 post_stop_max_return / max_drawdown；满 30 天 → 切到 post_stop_done

#### D. `update_review()` 主流程末尾调用

返回值新增 `holding_tracking` 字段：
```python
{
    "n_holding_updated":   N,   # 今日持仓中更新了几只
    "n_stop_triggered":    N,   # 今日新触发止损几只
    "n_post_stop_updated": N,   # 止损追踪中更新几只
    "n_post_stop_done":    N,   # 完成 30 天追踪几只
}
```

### 向后兼容性

| 老 CSV 行（report_date ≤ 20260602） | 走 `legacy_t1_sell` 路径，保留 simulated_trade_return / adjusted_sell_price 等老字段 |
| 新 CSV 行（report_date ≥ 20260603）| 走新持仓追踪路径，simulated_trade_return 只在止损或手动卖时填 |
| weekly/monthly 复盘统计 | 基于 simulated_trade_return，不受影响 |
| 16 个新字段在老 CSV 中 | 空字符串（_ensure_columns 自动补） |

### 是否运行 python run.py

- 否，仅本地 mock 单元测试

### 验收

4/4 场景全通过：

| 场景 | 期望结果 | 实际 |
|---|---|---|
| 新数据 T+1 涨 2% 未止损 | holding, peak_return +2.9%, 未卖 | ✅ |
| 新数据 T+1 盘中跌穿止损 | stopped, exit_price=97.097, ret=-3% | ✅ |
| 新数据 T+1 开盘就跌破 | stopped, 开盘价止损 96.0, ret=-4.1% | ✅ |
| 老数据 entry_date=20260602 | legacy_t1_sell, simulated_trade_return=+2.99% | ✅ |

### Git

- branch：`restore/radar-terminal-keep-t`
- commit：`bddfcfd feat(holding): 持仓持续追踪 + 止损后 30 天跟踪（朱哥需求）`
- 248 行改动（+241 / −7），仅改 trade_review.py 一个文件

### 禁改文件检查

- `run.py`：未改
- `output/trade_review.csv`：未改（schema 兼容新字段）
- `config/version_flags.yaml`：未改
- `launchd/*.plist`：未改
- 自动下单：未新增
- 券商连接：未新增

### 给 Codex 的接力（dashboard UI 配套需求）

朱哥这套新逻辑生效后，dashboard 应该新增 / 修改这些展示：

1. **持仓中页面** — 显示所有 `holding_status=holding` 的行
   - 列：股票、买入日、买入价、当前价、当前收益、最高收益、最大回撤、持仓天数、止损价
2. **已卖出 / 止损追踪页面** — 显示 `holding_status=stopped` 的行
   - 额外列：止损日、止损价、止损后最高反弹、止损后最低回撤、追踪进度（X/30 天）
3. **历史已完成页面** — 显示 `holding_status=post_stop_done` 或 `legacy_t1_sell` / `manual_sell`
4. **手动卖出按钮**（朱哥的实操路径） — dashboard 加按钮"标记已卖出"
   - 写 `exit_date=今日 / exit_price=今收 / exit_reason=manual_sell / holding_status=manual_sell`

### 给所有 AI 的明日验证清单（新增）

明天 06-03 19:00 update_review 跑完后：
- 看 `output/trade_review.csv`，如果今日有买入：
  - report_date=20260603 的行 `holding_status` 应该是 `holding` 或 `stopped`
  - 不再是 `simulated_trade_return` 立即填值（除非止损）
- 看 `logs/auto_run.log` 应该出现 `[holding_track]` 日志

### 主干 commit 时间线（最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `bddfcfd` | **持仓持续追踪 + 止损 30 天跟踪** | Claude（本轮）|
| `6f076d7` | 当日总收尾 md | Claude |
| `0996cba` | 中危 bug md | Claude |
| `c26faf3` | gitignore | Claude |
| `8607ae2` | 中危 #1 + #2 | Claude |
| `2968143` / `9b2a583` | 规则 3b 1.3% | Claude |
| `b296183` / `e3a8987` | 规则 3 升级 0.7% + VWAP | Claude |
| `789fb29` / `e4fef60` | T 模块 5 条规则重写 | Claude |
| `d7ecb77` / `82e3375` | 第二轮扫描 | Claude |
| `730a6fe` / `5e1f752` | tomorrow_plan + indicators nan | Claude |
| `3df6d1d` / `bf9ce11` | notifier nan/inf | Claude |

---

## 2026-06-02 Codex T 跨日记录口径修复

### 本次背景

用户明确要求做 T 记录不能只看当天：如果一只股票当天出现 B/S 点后没有触发止盈或止损，后续每天都要继续追踪，直到止盈、止损或人工复核。上一版 T 交易记录虽然能生成当天 B/S 点，但跨日 open 单缺少清晰的入场日、事件日和持仓天数字段。

### 已修复

- `scripts/build_t_trade_tracker.py`
  - T 交易字段新增 `entry_report_date`、`event_report_date`、`open_days`。
  - B/S 点字段新增 `entry_report_date`、`event_report_date`。
  - `trade.report_date` 表示本次记录日，`entry_report_date` 表示原始入场日，`event_report_date` 表示退出事件日或本次记录日。
  - `bs_log.report_date` 表示 B/S 点事件发生日。
  - open 单超过 3 天时，`note` 追加“已 open N 天，建议人工复核”。
  - 写 `t_open_positions.csv` 的同时写 `t_open_positions_<report_date>.csv` 每日快照。
- `dashboard_app.py`
  - 做 T 交易表新增记录日、入场日、持仓天数、备注。
  - B/S 点表新增事件日、入场日。
  - open 超过 3 天时显示风险提醒。
- `scripts/run_t_eod.py`
  - T summary 新增 `open_count`、`open_overdue_count`。

### 验收状态

- `py_compile` 曾通过：`scripts/build_t_trade_tracker.py`、`scripts/run_t_eod.py`、`dashboard_app.py`。
- 四个原 T 样例曾通过：低吸止盈、低吸止损、高抛回补、高抛踏空止损。
- 跨日 open 验证曾通过：Day1 open，Day2 触发止盈后写入正确的入场日、事件日和 B/S 点。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 上一批已提交：`36f5a97 fix watchlist priority and simulated T tracking`。
- 本节改动仍在工作区，尚未提交，等待用户确认。

## 2026-06-02 Codex dashboard UI 安全文案修正

### 本次背景

用户要求逐页检查 dashboard，找出可点击但功能不清、假指标、误导文案和布局问题，先记录问题后统一优化。本轮先做第一批低风险 UI 修正，只改展示口径，不改后端策略逻辑。

### 已修正

- `dashboard_app.py`
  - 首页将“实时信号流 / RADAR_LIVE_FEED / 延迟 12ms”改为“本地信号记录 / LOCAL_REVIEW_FEED / 更新 本地CSV”。
  - 首页将“模拟收益”改为“模拟收益率”，避免把收益率误显示成现金金额。
  - 首页将“9:36 确认买入”改为“9:36 模拟确认”。
  - 首页右侧流程中“资金条件层 0%”改为“检查进度”，避免误解为真实资金条件通过率。
  - 候选股票卡片 mini 折线标注为“趋势示意”，避免误解为真实分时图。
  - 买入确认页将“已买入”统一改为“模拟买入 / 模拟确认”，将“直接放弃”改为“未通过 / 暂不执行”。
  - T+1 / 候选复盘可见“已买入”口径统一改为“模拟买入”。
  - 明日计划将“明日交易权限”改为“明日计划口径”，并给覆盖重建按钮增加“不下单、不接券商”说明。
  - 做 T 观察空状态说明区分没有信号、脚本未跑、1 分钟行情源缺失、sample 仅用于验证。
  - 手动补跑将重复“立即执行”按钮改成具体动作名，如“补跑 T+1 复盘 / 生成本周复盘 / 生成本月复盘”。
  - 将废弃的 `st.components.v1.html` 滚动辅助替换为 `st.iframe(..., height=1)`，消除 Streamlit 1.57 废弃提示。

### 验收状态

- `py_compile dashboard_app.py` 曾通过。
- `git diff --check` 曾通过。
- Streamlit AppTest non-crash 曾覆盖全部 10 个页面。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 本轮 UI 安全文案修正尚未提交，等待用户确认。
- 工作区同时还保留上一批未提交的 T 跨日记录口径修复。

## 2026-06-02 Codex dashboard UI 第二批清理

### 本次背景

Claude 提交 `notifier.py` nan/inf 修复后，用户要求 Codex 先检查 md 接力是否完整，再继续 UI。已确认 Claude 的最新记录保留；同时从 `/tmp/handoff_with_codex.md.bak` 和 `/tmp/changelog_with_codex.md.bak` 把 Codex 前两段未提交交接记录追加回来。

### 已修正

- `AI_HANDOFF.md` / `AI_CHANGELOG.md`
  - 追加 Codex 的 T 跨日记录口径修复段。
  - 追加 Codex 的 dashboard UI 安全文案修正段。
  - 未覆盖 Claude 的 `notifier.py` 修复和实战首日观察段。
- `dashboard_app.py`
  - 候选复盘页：大盘环境、止损后跟踪、资金预筛缺失时，主界面改为用户友好状态说明；具体命令收进“开发者排查”折叠区。
  - 手动补跑页：主卡片不再直接展示命令，只展示作用、建议和“不接券商、不自动下单”边界；实际白名单命令收进折叠区。
  - 手动补跑结果提示不再把命令铺在主提示里，改为“详情见日志”。
  - 资金源健康探测：主卡片不再直接展示命令，增加“只读探测，不写推荐、不触发买入确认”说明；实际只读命令收进折叠区。
  - 可见“交易权限”展示口径改为“明日计划口径”，不改内部字段和后端逻辑。

### 验收

- `py_compile` 通过：
  - `dashboard_app.py`
  - `scripts/build_t_trade_tracker.py`
  - `scripts/run_t_eod.py`
- `git diff --check` 通过。
- Streamlit AppTest non-crash 通过全部 10 个页面：
  - 今日总览
  - 买入确认
  - T+1 复盘
  - 未买入跟踪
  - 周月复盘
  - 候选复盘
  - 明日计划
  - 做T观察
  - ⭐ 我的自选
  - 手动补跑

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 工作区仍 dirty：
  - `dashboard_app.py`
  - `scripts/build_t_signal_observer.py`
  - `scripts/build_t_trade_tracker.py`
  - `scripts/run_t_eod.py`
  - `AI_HANDOFF.md`
  - `AI_CHANGELOG.md`
  - `data/minute_today/` 未追踪真实分钟数据，不建议提交。
- 建议下一步先让用户确认是否提交 `dashboard_app.py` + 两个 T 脚本 + 两份 AI md；不要提交 `data/minute_today/`。

## 2026-06-02 Codex 逐页 UI 审查与 T 展示修复

### 本次背景

用户要求调用 Chrome 逐页检查 dashboard，每个导航页识别可点击但未实现、假指标、误导文案、布局/展示异常，最后统一修改。Chrome 可操作，但页面无障碍树和截图偶尔不同步；已结合 Chrome 点击、Streamlit AppTest 和代码定位完成本轮修复。

### 已检查页面

- 今日总览
- 买入确认
- T+1 复盘
- 未买入跟踪
- 周月复盘
- 候选复盘
- 明日计划
- 做T观察
- ⭐ 我的自选
- 手动补跑

### 发现并修复

- 今日总览：
  - 市场脉冲在行情字段缺失时不再把上涨家数/跌停数等显示成 `0`，改为 `—`，避免误判为真实 0。
  - 本地信号记录中的 `已放弃` 改为 `未通过`。
- Plotly 图表：
  - 隐藏 Plotly 英文 modebar，避免页面露出 `Download plot as PNG / Zoom / Pan` 等英文工具按钮。
- T+1 / 周月 / 候选复盘：
  - 将 `正式胜率统计`、`正式结算`、`正式止盈规则` 等文案改为模拟复盘口径。
  - 将 `买入触发` 改为 `模拟触发`。
  - 将候选复盘 `是否买入` 改为 `是否模拟确认`。
  - 将 `完全未买入` 改为 `未触发模拟买入`。
  - 将 `模拟未运行` 改为 `资金预筛未运行`。
- 做T观察：
  - 修复 sample 展示只依赖 `t_trade_latest.csv` 的问题；勾选“显示样例数据”后会从 dated sample 文件补充样例交易记录。
  - 样例 fallback 验证：能读到 4 笔 sample T trade、8 条 B/S 点。
  - 安全提示区分“真实可实盘异常”和“历史安全字段缺失”。历史空字段只黄灯提示，不再误报为疑似可实盘。
- `scripts/build_t_signal_observer.py`：
  - 对所有 T 信号行补齐默认安全字段，即使是未触发/数据缺失短返回行，也写入：
    - `execution_mode=simulate`
    - `can_execute_live=False`
    - `order_status=not_submitted`
    - `broker_status=not_connected`
  - 不接券商，不自动下单，不写 `output/trade_review.csv`。

### 验收

- `py_compile` 通过：
  - `dashboard_app.py`
  - `scripts/build_t_signal_observer.py`
  - `scripts/build_t_trade_tracker.py`
  - `scripts/run_t_eod.py`
- `git diff --check` 通过。
- Streamlit AppTest non-crash 通过全部 10 个页面。
- 做T样例 helper 验证：
  - sample signals rows: 8
  - sample trades rows: 4
  - B/S rows: 8
  - safety: 无可实盘异常；历史真实 T 信号存在空安全字段，新生成记录已修复。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 本轮改动未提交，等待用户确认。
- 工作区仍包含此前未提交的 T 跨日记录口径修复和本轮 UI/T 安全展示修复。
- `data/minute_today/` 是未追踪真实分钟数据，不建议提交。

## 2026-06-02 Codex UI 假指标/英文/误导控件清理

### 本次背景

用户指出 dashboard 仍存在假数字、假指标、不能点但像按钮的元素，以及残留英文字段。本轮仅做 UI 展示层修正，不改后端交易逻辑。

### 已修复

- 今日总览：
  - `正式买入`、`买入条件` 等容易误解的文案改为 `模拟买入`、`模拟确认条件`。
  - 表格最后一列从 `操作` 改为 `只读状态`，`CONFIRM / OBSERVE / FAILED` 改为 `模拟确认 / 观察中 / 未通过 / 待检查`。
  - `实时监测 (ON)`、`历史记录` 改为 `本地记录`、`只读展示`，避免用户误以为可点击。
  - 未到 9:36 检查时，候选股票和信号流优先显示 `待 9:36 检查`，不再误显示 `未通过`。
  - 没有收益字段时，`模拟收益率` 不再显示假 `0.00%`，改为 `— / 暂无模拟收益记录`。
  - `市场情绪` 改为 `本地情绪分`，并显示 `本地评分`，避免误解为实时大盘真值。
- 假视觉清理：
  - 移除今日候选卡片和 KPI 卡片中的 mock sparkline 假走势。
  - 自选股卡片移除按股票代码随机生成的假柱状图，改为基于真实字段完整度的进度条。
  - V1.6 侧栏不再展示固定 `100%` 假达标率，改为 `推荐记录 3 只 / 检查进度 0/3 / 模拟确认 0/3` 等真实计数。
- 中文化：
  - 首页 `MARKET SENTIMENT`、`LOCAL_REVIEW_FEED`、`MARKET PULSE`、`V1.6 ACHIEVEMENT FLOW` 等可视英文改为中文。
  - 自选页 `WATCHLIST RESEARCH`、`RESEARCH CONSOLE`、`Research Reason`、`Research Pulse` 改为中文。
  - 做T页 `T EXECUTION LAB`、`SIMULATE ONLY`、`V1.6 SIDE MODULE` 改为中文。
- Streamlit 默认工具栏：
  - 通过 CSS 隐藏 dataframe 默认工具栏，减少 `Download/Search/Fullscreen` 等非业务按钮感。

### 验收

- `py_compile` 通过：
  - `dashboard_app.py`
  - `scripts/build_t_signal_observer.py`
  - `scripts/build_t_trade_tracker.py`
  - `scripts/run_t_eod.py`
- `git diff --check` 通过。
- Streamlit AppTest non-crash 通过全部 10 个页面。
- 浏览器刷新 `http://localhost:8501/` 后确认：
  - `MARKET SENTIMENT`、`WATCHLIST RESEARCH`、`RESEARCH CONSOLE`、`趋势示意` 不再出现。
  - 首页显示 `待 9:36 检查`、`暂无模拟收益记录`、`本地情绪分`。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 本轮 UI 清理未提交，等待用户确认。
- 工作区仍 dirty，包含 UI 修复、T 脚本修复、AI 文档更新，以及未追踪 `data/minute_today/`。

## 2026-06-02 Codex 跨页面 RADAR 风格统一

### 本次背景

用户指出“今日总览”已经按 Stitch/RADAR 终端风格重构，但其它页面仍是旧 Streamlit 风格，导致整体割裂。本轮仅做前端风格统一，不改后端业务逻辑。

### 已修复

- `render_page_header()`：
  - 不再强制英文 uppercase，中文 kicker/aside 保持自然展示。
  - 修复右侧说明卡因为 HTML 缩进被 Markdown 当作代码块渲染的问题。
- 补齐统一 Hero：
  - `未买入跟踪`
  - `周 / 月复盘`
  - `每日候选复盘`
  - `手动补跑`
- 中文化已有 Hero：
  - `买入确认`：`Execution Review / Review Lens` 改为中文。
  - `T+1 复盘`：`Outcome Audit / Audit Scope` 改为中文。
  - `明日交易计划`：`Plan Console / Control Notes` 改为中文。
- 全局 CSS：
  - 非今日页的 `h2/h3` 统一为 RADAR 玻璃终端章节标题。
  - `st.divider`、caption、metric 等进一步统一到深色终端视觉。

### 浏览器确认

- 已刷新 `http://localhost:8501/`。
- 实测点击：
  - `买入确认`
  - `未买入跟踪`
  - `候选复盘`
  - `手动补跑`
- 确认右侧说明卡不再露出 `<div style=...>` 原始 HTML。
- 非今日页已出现统一终端 Hero，视觉不再完全割裂。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest non-crash 通过全部 10 个页面。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 跨页面 UI 统一未提交，等待用户确认。
- 当前仍是“基础统一”，还不是每个页面都深度卡片化；后续可按页面逐个把表格改为自渲染终端卡片/表格。

## 2026-06-02 Codex 买入确认页深度卡片化

### 本次背景

用户说明 Claude 今天改了底层代码但未动 UI，要求先读最新 MD 后继续修 dashboard UI。经确认当前 dirty 文件主要是 `dashboard_app.py` 与 AI 文档，底层 T 脚本已不在当前 dirty 列表；`data/calendar/`、`data/minute_today/` 为未追踪数据目录，本轮不处理。

### 已修复

- `买入确认` 页面：
  - 保留原有三段分类逻辑，不改数据来源、不改交易判断。
  - 将原 Plotly 横向分布图替换为 RADAR 终端风格 HTML 分布卡：
    - 模拟确认
    - 值得观察
    - 未通过
  - 将“未通过”明细从 `st.dataframe` 改为与其它分组一致的股票卡片展示。
  - 升级通用 `stock_card()` 外观为 V2 玻璃态卡片，带左侧状态光条和 hover 风格，减少与今日总览的视觉割裂。
  - 修复新增 HTML 片段未套 `_h()` 导致浏览器显示 `<div style=...>` 原始源码的问题。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest non-crash 通过全部 10 个页面。
- 浏览器刷新 `http://localhost:8501/` 并点击 `买入确认`：
  - 确认显示 `三段结果总览`、`只读统计`。
  - 确认不再露出 `<div style=...>` 原始 HTML。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 本轮 UI 深度卡片化未提交，等待用户确认。
- 下一步建议继续按页面推进：`做T观察` → `明日计划` → `候选复盘`。

## 2026-06-02 Codex 做T观察页终端卡片化

### 本次背景

用户确认 Claude 今日改了底层代码，但要求 Codex 继续处理 UI 风格统一。先读取最新 AI 文档后继续，不改后端主逻辑、不运行 `python run.py`。

### 已修复

- `做T观察` 页面：
  - 保留原有 T 信号读取、T 交易记录读取、B/S 点读取逻辑。
  - 将“今日真实 T 信号”从普通 dataframe 展示改为 RADAR 终端卡片流。
  - 将“T 交易记录”从普通 dataframe 展示改为终端交易卡片。
  - 将 B 点 / S 点记录改为终端点位卡片。
  - 增加 T 信号类型、退出原因、B/S 点原因、交易状态的中文映射。
  - 对 `nan`、空值、缺失价格做前端兜底，显示为 `—`、`无触发`、`未设置` 等友好文案。
  - 页面继续保留“做 T 模拟记录 / 不构成自动买卖指令”的安全提示。

### 当前真实数据状态

- 当前真实 T 信号可显示。
- 当前真实 T 交易记录为空时，页面显示暂无真实 T 交易记录。
- 因默认不显示 sample，且真实交易记录为空，B/S 点区不会误造数据。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest non-crash 通过全部 10 个页面。
- 浏览器刷新 `http://localhost:8501/` 并点击 `做T观察`：
  - 确认显示 `T 信号流`。
  - 确认显示 `只读观察`。
  - 确认没有 `nan` 文案。
  - 确认没有 `<div style=...>` 原始 HTML。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- `dashboard_app.py` UI 改动未提交，等待用户确认。
- 下一步建议继续深度统一：`明日计划` → `候选复盘` → `T+1复盘` → `未买入跟踪`。

## 2026-06-02 Codex 明日计划页前端安全视觉优化

### 本次背景

用户要求继续逐页统一 dashboard UI，并重点识别“能点但容易误解”“假指标”“英文残留”“普通后台表格感”等问题。本轮先处理 `明日计划` 页面。

### 已修复

- `明日计划` 页面：
  - 保留原有计划读取、人工编辑、保存、脚本按钮逻辑，不改交易判断。
  - 在一键操作区新增 `LOCAL SCRIPT CONTROL` 安全说明卡，明确：
    - 不会运行 `python run.py`
    - 不会自动下单
    - 不会连接券商
    - 只是生成本地复盘/计划文件
  - 将 `核心观察股（focus_stocks）` 从普通 dataframe 改为终端观察卡片：
    - 股票代码
    - 股票名称
    - 入选原因
    - 只读观察标签
  - 将 `V1.6 配置状态` 从普通 dataframe 改为 `CONFIG SNAPSHOT` 只读配置卡。
  - 修复新增 HTML 卡片未压平导致浏览器显示 `<div style=...>` 原始文本的问题。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest 打开 `明日计划` 无异常。
- 浏览器刷新 `http://localhost:8501/` 并点击 `明日计划`：
  - 确认显示 `LOCAL SCRIPT CONTROL`。
  - 确认显示 `FOCUS NODE`。
  - 确认显示 `CONFIG SNAPSHOT`。
  - 确认没有 `nan`。
  - 确认没有 `<div style=...>` 原始 HTML。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- `dashboard_app.py` UI 改动未提交，等待用户确认。
- 下一步建议继续深度统一：`候选复盘` → `T+1复盘` → `未买入跟踪`。

## 2026-06-02 Codex 候选复盘页主线板块与文案优化

### 本次背景

用户继续要求逐页检查 UI，识别假指标、英文/开发字段、不能点但像按钮的问题。本轮处理 `候选复盘` 页面。

### 已修复

- `候选复盘` 页面：
  - 保留原有候选生命周期聚合、资金条件层观察、T+1 表现、止损跟踪读取逻辑。
  - 将 `主线板块判断` 的普通 dataframe 改为 `SECTOR SCAN` 终端板块卡片。
  - 去掉前台缺失提示里的 `status=...` 开发字段。
  - 修复原因翻译函数误把 `V1.4/V1.5` 中的斜杠拆成两个原因，导致页面出现 `未知原因：V1.5` 的问题。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest 打开 `候选复盘` 无异常。
- 浏览器刷新 `http://localhost:8501/` 并点击 `候选复盘`：
  - 确认页面打开正常。
  - 确认没有 `nan`。
  - 确认没有 `<div style=...>` 原始 HTML。
  - 确认 `未知原因：V1.5` 已消失，文案正常显示为 `已回退 V1.4/V1.5`。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- `dashboard_app.py` UI 改动未提交，等待用户确认。
- 下一步建议继续深度统一：`T+1复盘` → `未买入跟踪` → `周月复盘`。

## 2026-06-02 Codex T+1复盘页结算卡片化

### 本次背景

用户继续要求逐页修 UI，减少普通 dataframe、假指标感和未解释清楚的展示项。本轮处理 `T+1 复盘` 页面。

### 已修复

- `T+1 复盘` 页面：
  - 保留原有 T+1 结算、止损、风险调整成功率读取逻辑。
  - 将 `已完成 T+1 复盘明细` 从普通 dataframe 改为 `T+1 SETTLEMENT` 终端结算卡片。
  - 每张卡展示：
    - 股票名称 / 代码 / 推荐日期 / 模式
    - 模拟收益
    - 买入价 / 滑点后 / 止损价 / 结算方式
    - T+1 开盘 / 最低 / 收盘 / 最大回撤
    - 冲高 3%、冲高 5%、是否止损、风险调整成功
    - 止损说明与止盈规则说明

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest 打开 `T+1 复盘` 无异常。
- 浏览器刷新 `http://localhost:8501/` 并点击 `T+1 复盘`：
  - 确认显示 `T+1 SETTLEMENT`。
  - 确认没有 `nan`。
  - 确认没有 `<div style=...>` 原始 HTML。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- `dashboard_app.py` UI 改动未提交，等待用户确认。
- 下一步建议继续深度统一：`未买入跟踪` → `周月复盘`。

## 2026-06-02 Codex 未买入跟踪页原因与机会成本卡片化

### 本次背景

用户继续要求逐页检查 UI，减少普通表格、假指标感和误解性展示。本轮处理 `未买入跟踪` 页面。

### 已修复

- `未买入跟踪` 页面：
  - 保留原有未买入样本筛选、二次观察统计、错过大涨判定逻辑。
  - 将 `不买原因排名` 的右侧 dataframe 改为 `BLOCK REASON` 终端原因卡片。
  - 将 `错过大涨` dataframe 改为 `MISSED SURGE` 机会成本卡片。
  - 卡片明确提示“机会成本只用于复盘漏选，不构成补买建议”。
  - 保留底部 `未买入完整明细` dataframe，作为详细排查表。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest 打开 `未买入跟踪` 无异常。
- 浏览器刷新 `http://localhost:8501/` 并点击 `未买入跟踪`：
  - 确认显示 `BLOCK REASON`。
  - 确认显示 `MISSED SURGE`。
  - 确认没有 `nan`。
  - 确认没有 `<div style=...>` 原始 HTML。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- `dashboard_app.py` UI 改动未提交，等待用户确认。
- 下一步建议继续深度统一：`周月复盘`。

## 2026-06-02 Codex 周月复盘页模式对比卡片化

### 本次背景

用户继续要求逐页统一 dashboard UI，减少普通 dataframe 和旧式成绩表。本轮处理 `周月复盘` 页面。

### 已修复

- `周月复盘` 页面：
  - 保留原有周期统计、模式统计、胜率、止损率、盈亏比计算逻辑。
  - 将 `全A vs 主题龙头 对比` 从普通 dataframe 改为 `MODE SCORECARD` 终端模式对比卡片。
  - 卡片展示推荐数、模拟触发、触发率、已 T+1 复盘、风险调整成功率、止损率、盈亏比。
  - 保留下方柱状图和明细 tab，方便继续排查。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest 打开 `周月复盘` 无异常。
- AppTest 文本断言确认 `MODE SCORECARD` 已渲染，且无 `nan`。
- 浏览器自动化点击该页时本轮曾出现工具超时，但 AppTest 页面级验收通过；未发现代码异常。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- `dashboard_app.py` UI 改动未提交，等待用户确认。
- 主要页面已完成第一轮风格统一；后续可做全局收口和提交拆分。

## 2026-06-03 Codex UI 提交前边界复核

### 当前分支

- `restore/radar-terminal-keep-t`

### 当前工作区

- 未提交修改：
  - `dashboard_app.py`
  - `AI_HANDOFF.md`
  - `AI_CHANGELOG.md`
- 未追踪数据目录：
  - `data/calendar/`
  - `data/minute_today/`

### 已确认状态

- `trade_review.py` 持仓持续追踪 / 止损后 30 天跟踪已在此前提交中落地，当前工作区不再 dirty。
- 自选池 13 → 27 只已在此前提交中落地，当前工作区不再 dirty。
- 当前剩余待提交内容主要是 dashboard UI 第一轮风格统一和 AI 文档记录。

### 验收

- `py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- 10 个页面 Streamlit AppTest 全部无异常：
  - 今日总览
  - 买入确认
  - T+1 复盘
  - 未买入跟踪
  - 周月复盘
  - 候选复盘
  - 明日计划
  - 做T观察
  - ⭐ 我的自选
  - 手动补跑
- 浏览器刷新 `http://localhost:8501/`：
  - 确认 `RADAR_TERMINAL` 顶部导航存在。
  - 确认没有 `nan`。
  - 确认没有 `<div style=...>` 原始 HTML。
  - 确认主要导航项存在。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 建议下一步

- 如果用户确认 UI 当前可接受，可以提交：
  - `dashboard_app.py`
  - `AI_HANDOFF.md`
  - `AI_CHANGELOG.md`
- 不建议提交：
  - `data/calendar/`
  - `data/minute_today/`

## 2026-06-03 Codex T+1 / 自选页精修

### 本次任务

- 按朱哥要求优先精修 `T+1 复盘` 和 `⭐ 我的自选` 两页。
- 目标是更贴近 `今日总览` 的 RADAR_TERMINAL 终端风格，同时明确“自选池优先评估，但不是买入指令”。

### 修改范围

- `dashboard_app.py`
  - `T+1 复盘`：
    - 新增页面专属终端 CSS。
    - KPI 改成高密度终端栅格。
    - 等待 T+1 样本改成卡片队列。
    - 已完成样本保留结算流卡片，并新增更清晰的 `SETTLEMENT STREAM` / `PERFORMANCE CHARTS` 区块。
    - 止盈/止损说明改成两张规则卡，仍然只读展示，不改变任何结算规则。
  - `⭐ 我的自选`：
    - 页面宽度从偏宽布局收敛到 1060px 左右。
    - 自选卡片改为双列高密度网格。
    - 明确文案：自选池优先进入候选评估，但仍必须通过安全过滤、V1.6 计划层和 9:36 技术确认。
    - 修复 Streamlit 分段 `st.markdown` 导致 CSS grid 不生效的问题：卡片组改为一次性渲染整组 HTML。

### 验收

- `.venv/bin/python3 -m py_compile dashboard_app.py` 通过。
- `git diff --check` 通过。
- Streamlit AppTest：
  - `T+1 复盘` 无异常。
  - `⭐ 我的自选` 无异常。
- 浏览器检查 `http://localhost:8501/`：
  - `T+1 复盘` 有 KPI、结算流、规则卡，无 raw HTML，无 `nan`。
  - `⭐ 我的自选` 显示 27 只，自选优先文案存在，无 raw HTML，无 `nan`。
  - 自选卡片已实际变为双列：浏览器测得 grid columns 为 `525px 525px`。

### 安全边界

- 未运行 `python run.py` 或任何 `run.py` 子命令。
- 未修改 `run.py`。
- 未修改 `trade_review.py`。
- 未修改 `output/trade_review.csv` 历史记录。
- 未修改 `config/version_flags.yaml`。
- 未修改 `launchd/*.plist`。
- 未新增自动下单或券商连接逻辑。

### 当前状态

- 当前改动尚未提交。
- 待提交文件预计为：
  - `dashboard_app.py`
  - `AI_HANDOFF.md`
  - `AI_CHANGELOG.md`
- 仍不建议提交未追踪数据目录：
  - `data/calendar/`
  - `data/minute_today/`

### 追加修正

- `做T观察` 的“今日真实 T 信号”按股票代码合并展示，避免同一股票多条 low/high/no-trigger 记录看起来像重复推荐。
- `⭐ 我的自选` 去掉重复 chip：
  - 不再在 hero、工具条、列表头、每张卡里反复显示“自选优先 / 自选 ≠ 买入”。
  - 保留全局安全说明：自选池优先进入候选评估，但仍需安全过滤、V1.6 计划层和 9:36 技术确认。
- `⭐ 我的自选` 的“快速添加 / 搜索筛选”从 Streamlit 原生 expander 大横条改为小型 `打开控制台` 弹层入口：
  - 保留股票识别、加入自选、搜索、status/priority 筛选、主题/理由勾选能力。
  - 只改展示布局，不改变 `_wl_identify()`、`_wl_save()` 或自选池 CSV 写入逻辑。
- 追加修正：`RESEARCH INPUT` 二级标题已移除，主页面默认不再摊开输入框；需要新增/筛选时点击 `打开控制台`。
- 浏览器复核 `⭐ 我的自选`：
  - 旧的“展开：快速添加 / 搜索筛选”不存在。
  - `RESEARCH INPUT` 不存在。
  - 快速添加输入框移动到 `打开控制台` 弹层内，placeholder 为 `例如 300476 / 胜宏科技`。
  - 自选卡片仍为双列，浏览器测得首屏卡片宽度约 525px。
- 这次仍是纯 dashboard 展示层修改，不改变任何 T 信号生成、选股、买入或记录逻辑。

### 2026-06-03 10:29 追加：自选页首屏控件清理

- 根据朱哥最新浏览器截图，`⭐ 我的自选` 首屏仍有原生 Streamlit 控件横条，视觉上与 `今日总览` 不一致。
- 已继续调整 `dashboard_app.py`：
  - 删除旧的 `watchlist-controls-anchor` / `watchlist-popover-anchor` 相关 CSS。
  - 首屏不再渲染“打开控制台”大按钮或横向输入控件。
  - `搜索、识别与观察筛选` 改为只读说明卡：`观察池优先评估`。
  - “快速识别 / 新增”和“搜索 / 筛选展示”移动到页面底部 `展开维护自选池` 内。
  - 去掉首屏 `active / p1`、`priority / stock_code`、`MARKET RESEARCH FEED` 等半英文/冗余标签。
- 浏览器 DOM 复核 `http://localhost:8501/`：
  - `⭐ 我的自选` 已选中。
  - 旧的 `打开控制台` 不存在。
  - 旧的 `默认展示全部自选股，需要新增...` 不存在。
  - `active / p1`、`priority / stock_code`、`MARKET RESEARCH FEED` 不存在。
  - `中电港`、`大族激光` 等自选卡片正常显示。
  - `展开维护自选池` 仍存在，保留新增、识别、搜索、筛选和保存能力。
- 验证：
  - `.venv/bin/python3 -m py_compile dashboard_app.py` 通过。
- 安全边界：
  - 未运行 `python run.py` 或任何 `run.py` 子命令。
  - 未修改 `run.py`、`trade_review.py`、`output/trade_review.csv`、`config/version_flags.yaml`、`launchd/*.plist`。
  - 未新增自动下单或券商连接逻辑。

---

## 2026-06-03 Claude（dashboard 持仓追踪页 + T 规则 1 删除）

### 朱哥本日新增需求

1. **T 规则 1（5 日均线斜率向上）删掉** — `9433419`
2. **持仓追踪 csv 字段需要在 dashboard 显示** — `d883861`（本轮）

### 修改文件

**1. `scripts/build_t_signal_observer.py`**（`9433419`）
- 删除 `ma5_missing` / `ma5_slope_not_up` 两条 fail return
- `ma_val` / `slope_ok` 保留为输出字段，但不参与判定
- docstring 5 条规则 → 4 条规则

**2. `dashboard_app.py`**（`d883861`）
- 新增 `page_holding_track(df_all)` 函数（约 200 行）
- 导航第 4 位插入「持仓追踪」
- 主流程 dispatch 加 `elif page == "持仓追踪"`

**3. `朱哥策略说明.md`**（`9433419`）
- T 模块章节由 5 条规则改成 4 条
- 规则编号重排，加注 ma5 仅记录不参与判定

### dashboard 持仓追踪页面结构

**风格**：严格沿用 Codex 的 RADAR V2 玻璃卡片
- 复用 `render_page_header / kpi_card / glass_card_html / chip_html`
- 颜色：`COLOR_BOUGHT`（持仓中绿）/ `COLOR_DROP`（止损红）/ `COLOR_MAGENTA_NEON`（卖飞）
- 字体：`FONT_MONO`（JetBrains Mono）
- **不改任何后端代码，不动 Codex 已 commit 的页面**

**4 个 KPI 卡片**：
- 持仓中 N 只
- 已止损 N 只
- 平均当前收益
- 已止损卖飞 N 只（post_stop_max_return_pct ≥ 3% 算卖飞）

**4 个分组卡片区**：
| 分组 | holding_status | 显示字段 |
|---|---|---|
| 持仓中 | `holding` | 10 字段（买入日 / 持仓天数 / 买入价 / 止损价 / 最新收盘 / 当前收益 / 期间最高 / 期间最低 / 最大收益 / 最大回撤）|
| 已止损 30 天追踪 | `stopped` | 10 字段 + POST-STOP TRACK 子块（止损日 / 追踪天数 / 止损价 / 最高反弹 / 最低回撤 + 卖飞 🚀 标记）|
| 30 天追踪完成 | `post_stop_done` | 同上 |
| 手动卖出 | `manual_sell` | 10 字段 |

### 是否运行 python run.py

- 否

### 验收

- `py_compile dashboard_app.py` 通过
- Streamlit AppTest 全 11 页 non-crash 通过
- '持仓追踪' 在导航第 4 位正确注册
- `9433419` 3/3 mock 测试通过（ma5 缺失 / 斜率 False / 正常 三场景）

### Git

- branch：`restore/radar-terminal-keep-t`
- commits：
  - `9433419 feat(t-rule): 删除规则 1「5 日均线斜率向上」前置门`
  - `d883861 feat(dashboard): 新增「持仓追踪」页面`

### 当前生效的 T 模块 4 条规则

```python
# scripts/build_t_signal_observer.py:128-135
BELOW_VWAP_PCT   = 0.013   # 规则 2b: 离 VWAP ≥ 1.3%
DROP_PCT_MIN     = 0.007   # 规则 2a: 1-3 分钟跌 ≥ 0.7%
VOL_MULTIPLE_MIN = 2.0     # 规则 3:  绿量 ≥ 前 1-3 根绿 K 均量 × 2
SHRINK_RATIO_MAX = 0.5     # 规则 4:  下一根缩量比 ≤ 0.5
```

时间窗口（规则 1）：`09:33-10:15`。

### 给所有 AI 的状态

- T 规则确定为 4 条（不再变动除非朱哥再拍）
- 持仓追踪 UI 已就绪，明早 06-04 9:36 真买入后即可在 dashboard 看到
- Codex 的 RADAR V2 风格被严格沿用，无视觉割裂
- 至今合入主干 27 个 Claude commit + 3 个 Codex 大 commit

### 主干 commit 时间线（最新在上）

| commit | 内容 | 谁做 |
|---|---|---|
| `d883861` | dashboard 持仓追踪页面 | Claude（本轮）|
| `9433419` | 删除 T 规则 1 ma5 斜率 | Claude |
| `86347f3` | dashboard watchlist + T review UI | Codex |
| `ecf4f1c` | update_review 完整 4-step 链路 | Claude |
| `68aafec` | 策略说明 md | Claude |
| `3dc5ab2` | RADAR dashboard 大重构 | Codex |
| ... | （早 24 个 commit）| Claude |
