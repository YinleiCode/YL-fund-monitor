# 朱哥A股短线三票雷达 — CLAUDE.md

## 项目位置
`/Users/yinlei/Desktop/量化/stock_screener/`

## 运行指令

### 完整运行
```bash
python3 /Users/yinlei/Desktop/量化/stock_screener/run.py
```

### 每日主循环（含买入确认、复盘等全流程）
```bash
python3 /Users/yinlei/Desktop/量化/stock_screener/auto_supervisor.py
```

## 每天自动运行时间（交易日）
| 时间 | 阶段 | 说明 |
|------|------|------|
| 9:25 | 集合竞价后 | 竞价值参考，预判当日苗头 |
| 9:30 | 开盘 | 正式交易开始 |
| 9:36 | 买入确认 | `python3 run.py --check-buy`，用V1.4五条规则+尾盘closing_pool候选判断是否买入 |
| 10:00 | 盘中观察 | 盘中走势观察 |
| 11:00 | 上午收盘前 | 半日总结，下午预判 |
| 13:00 | 下午开盘 | 下午盘观察 |
| 14:00 | 尾盘观察 | 判断尾盘走势和收盘策略 |
| 15:15 | 收盘后 | 数据稳定后用完整数据做收盘总结 |
| 21:00 | 晚间复盘 | 深度复盘，主题/资金/技术三维分析，给出明日预案 |
| 周五15:40 | 周报 | `run.py --weekly-review` 生成周报 |

## 版本现状（2026-06-06 更新）
- **当前活跃版本**:
  - **V1.4** — 择股公式、评分、买入规则（正式版输出 + 收益计算基础）
  - **V1.5-beta** — 资金条件，灰度中，observe_only 模式（mark_only 不影响买入）
  - **V1.6** — 复盘驱动选股，plan_filter_enabled=true 但 `affect_check_buy=false`（2026-06-05 朱哥拍板关掉自动拦截，只打审计标签）
  - **V1.7 ✨** — LLM 情绪+新闻分析师（2026-06-05 上线，mark_only 旁路，每天 18:30 跑）
  - **手动只观察** — 替代 V1.6 自动拦截，用户手动勾选才进观察池
- 所有版本共存运行，V1.4 是正式版输出和收益计算基础。V1.5/V1.7 永不影响 buy_signal_0935（mark_only 守卫）。

## 核心规则与判读逻辑

### 1. 解盘
判断当日行情好坏，市场情绪评分。参考 config.yaml market 节。

### 2. 选股
- 候选池：score>=78 且 人气>=22 且 技术>=20（条件见 config.yaml buy_rules）
- 基础筛选：成交额>=3亿，换手率>=2%，股价>=3元，昨日涨幅1%~9.5%
- scoring 权重：人气热度30分 + 技术动能30分 + 上涨空间25分 + 风险控制15分（扣分制）
- 主题强度 theme_strength 需 >=50

### 3. 买点
#### V1.4 买入五条规则（从9:36开始判断）
1. 尾盘 close_increase 达标的候选股可用 closing_pool
2. 开盘涨幅 $open_change: 低于 -3% 否决，[-3%, -1%) 辅助观察，高于 4% 否决
3. 尾盘涨幅收盘时要在 [1.0%, 9.5%] 范围
4. 尾盘换手率 $turnover_rate: >=2%
5. 尾盘成交额 $amount: >=3亿

买入信号 buy_signal_0935 由 trade_review.check_buy() 基于以上五条综合判断。

#### V1.6 前置门 (2026-06-05 起已关)
当前 `affect_check_buy=false` — V1.6 plan 只打标签（v16_* 审计字段写 CSV），**不再阻塞 9:36 买入**。如果要恢复自动拦截，改 `config/version_flags.yaml` 即可。

#### V1.5 资金条件（observe_only）
当前只记录 v15_* 字段，不影响买入信号和收益计算。allow_block_buy=false 锁定。

#### V1.7 LLM 情绪+新闻分析师 (2026-06-05 上线, mark_only)
每天 18:30 跑 `scripts/build_news_sentiment.py`：
- 对 27 只自选池 + 当日推荐池调 Claude Opus 4.7（默认）或 DeepSeek-Chat
- 输出 11 个 `v17_*` 字段（情绪分 0-10 + 标签 + 摘要 + 风险提示 + 题材）
- **永远不影响 9:36 买入**（mark_only 三层守卫）
- 看板入口：⭐ 自选页 + 🔥 跟踪页 底部「✨ LLM 情绪雷达」expander
- 成本：Claude ~$9/月，DeepSeek ~$0.31/月

#### 手动「只观察」开关 (2026-06-05 起, 替代 V1.6 自动拦截)
- 默认所有自选股走 9:36 V1.4/V1.5 判定（=允许买入）
- 用户在看板「⭐ 自选」或「🔥 跟踪」底部勾选「只观察」→ 写 `data/manual_observe.json`
- 下次 `check_buy` 加载名单，命中的票跳过 9:36 买入（最高优先级前置门）
- 看板显示「✋ 手动只观察」黄色徽章

### 4. 风控
- 买入滑点 0.1%（千一），卖出暂不扣
- 止损价 = adjusted_buy_price * 0.97（统一97%）
- scoring 风险扣分：炸板扣8，破20日线0-2%扣5，近5日涨幅超20%扣3，近10日超35%扣5，上影线超5%扣3，换手率超25%扣5

### 5. 每日推票逻辑
run.py 生成的推荐池按总分排序，取前3输出。配合 trade_review.py 的 review 逻辑记录逐笔交易决策。

自动化辅助工具：
- auto_supervisor.py：补跑总控，被 launchd 每5分钟调起；自动检查当日各任务状态（pick、check_buy、second_check、update_review、summary）按需补跑
- launchd 配置位于 launchd/ 目录

## 模拟模式
- **命令行**：`python3 run.py --simulate` — 手动测试，不影响 auto_supervisor
- **配置文件**：`config.yaml` data_source.simulate_data: true — 全局生效（run.py 和 auto_supervisor 子进程均使用模拟行情）
- **特征**：不连任何真实数据源，生成300只随机股票的模拟 DataFrame，可通过全流程筛选、打分、推送、写入 trade_review.csv。

## 依赖与配置
- config.yaml：主配置文件，阈值、权重、版本日期、买入标准
- config/version_flags.yaml：V1.5/V1.6 灰度特性开关
- config/theme_keywords.yaml：主题关键词

## 启动方式对比
| 方式 | 说明 |
|------|------|
| `python3 run.py` | 手动单次运行盘前选股（full模式），生成推送和Excel报告 |
| `python3 run.py --check-buy` | 9:36 买入确认 |
| `python3 run.py --second-check` | 10:00 二次确认观察（仅记录，不买入） |
| `python3 run.py --theme-auto` | 主题龙头模式（并行实验组） |
| `python3 run.py --update-review` | T+1 复盘补全 |
| `python3 run.py --review-summary` | 周报/月报统计 |
| `python3 run.py --simulate` | 使用模拟行情（不连真实数据源）。config.yaml 设 simulate_data=true 可全局启用（auto_supervisor 也生效） |
| `python3 run.py --test-notify` | 测试 Server酱 推送 |
| `python3 auto_supervisor.py` | 补跑总控，被 launchd 每5分钟调起；自动检查当日各任务状态按需补跑 |

## 自动调度
1. **Claude Code 持久化 cron 作业**（`/Users/yinlei/Desktop/量化/.claude/scheduled_tasks.json`）：交易日全天多时段自动触发分析和观察（9:25、9:30、9:36、10:00、11:00、13:00、14:00、15:15、21:00、周五15:40），每个作业有7天自动过期。cron 作业的 prompt 中包含了该时段的具体指令。
2. **launchd**（`launchd/com.zhuge.stock.*.plist`）：auto_supervisor.py 每5分钟轮询状态、补跑遗漏任务
3. **launchd V1.7 LLM 情绪师**（`launchd/com.zhuge.stock.newssentiment.plist`）：工作日 18:30 自动跑 `scripts/build_news_sentiment.py`（2026-06-05 新增）

## 启动看板（朱哥本地长期开着）

```bash
streamlit run dashboard_app.py    # 默认端口 8501
```

**AI 测试看板时千万别 `pkill -f "streamlit run dashboard_app.py"`** —— 会杀掉朱哥的主进程。改用：
```bash
nohup .venv/bin/streamlit run dashboard_app.py --server.port 8765 \
    --server.headless true --browser.gatherUsageStats false \
    > /tmp/test_streamlit.log 2>&1 &
# 测试完精准 kill
lsof -i :8765 -t | xargs kill
```

## 关键 API 配置（`.env`）
```
SERVERCHAN_SENDKEY=...     # 微信推送
ANTHROPIC_API_KEY=...      # V1.7 Claude Opus 4.7
DEEPSEEK_API_KEY=...       # V1.7 备选 provider (便宜 28 倍)
```
