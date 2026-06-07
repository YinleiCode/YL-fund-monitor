"""V1.8 sub-agent 模块 (朱哥 2026-06-06 立项 - X-Plus 方案).

4 个 A 股短线专属 agent:
    hot_money_analyst   - 游资追踪 (龙虎榜/量价异动/连板分析)
    chip_bigdeal_analyst - 筹码大单 (主力筹码/大单流入流出)
    theme_momentum_analyst - 题材发酵 (板块强度/概念热度/发酵阶段)
    risk_alert_analyst   - 风险预警 (高位炒作/解禁/技术风险)

每个 agent:
    - 独立 system_prompt (针对单一维度)
    - 共用 news_fetcher 抓的新闻
    - 输出结构化 JSON
    - 返回 SubAgentResult dataclass

灵感:
    - TradingAgents-astock (1011★) 的 hot_money_tracker / lockup_watcher prompt
    - FinGenius (2694★) 的 chip_analysis / big_deal_analysis agent
    - 朱哥策略说明.md 的"题材轮动 + 持仓追踪"
"""
