# AI_RULES.md

本文件是朱哥短线雷达 V1.6 项目的 AI 协作硬规则。Claude、Codex、DeepSeek 或任何后续模型接手前，必须先阅读本文件，再阅读 `AI_HANDOFF.md` 和 `AI_CHANGELOG.md`。

## 1. 危险命令规则

默认不运行：

```bash
python run.py
```

禁止运行：

```bash
python run.py --check-buy
python run.py --theme-auto
python run.py --update-review
python run.py --second-check
```

除非用户明确、单独授权，否则任何模型都不能运行上述命令。

## 2. 交易安全规则

- 禁止自动下单。
- 禁止接券商。
- 禁止新增、修改或启用任何真实交易执行逻辑。
- 禁止把观察、模拟、回测结果伪装成真实买卖记录。
- 禁止修改 `output/trade_review.csv` 历史记录。

## 3. 禁改文件

默认禁止随意修改：

- `run.py`
- `trade_review.py`
- `config/version_flags.yaml`
- `launchd/*.plist`
- `output/trade_review.csv`

如果必须修改 `run.py` 或 `trade_review.py`，必须先说明：

- 为什么必须改；
- 会影响哪条链路；
- 有哪些风险；
- 如何验证不触发真实交易；
- 等用户确认后再改。

## 4. Dashboard 规则

- 可以修改 `dashboard_app.py` 做前端展示、布局、交互和可视化优化。
- 修改后必须说明是否只影响前端。
- 如果 dashboard 修改会读取、写入业务数据，必须说明读写文件路径和安全边界。
- dashboard 禁止出现“立即买入”“自动买入”“下单”“执行交易”等真实交易误导按钮。

## 5. T 模块硬安全规则

T 模块永远必须保持模拟状态：

- `execution_mode=simulate`
- `can_execute_live=False`
- `order_status=not_submitted`
- `broker_status=not_connected`

T 模块可以记录：

- T 信号观察；
- T 交易模拟记录；
- B/S 点；
- 止盈止损；
- 盈亏记录；
- dashboard 展示。

T 模块禁止：

- 自动下单；
- 接券商；
- 写入 `output/trade_review.csv`；
- 影响 V1.6 主买入链路。

## 6. 提交前必须输出

提交前必须输出：

```bash
git status --short
git diff --stat
```

同时必须说明：

- `py_compile` 是否通过；
- 是否运行过 `python run.py`；
- 是否修改过禁改文件；
- 是否包含 `output/*` 运行产物；
- 是否包含真实交易相关逻辑。

## 7. 每次任务结束必须更新

每次 Claude / Codex / DeepSeek 完成任务，都必须更新：

- `AI_HANDOFF.md`
- `AI_CHANGELOG.md`

`AI_HANDOFF.md` 记录当前项目状态、风险点和下一步。

`AI_CHANGELOG.md` 追加本次模型操作历史。

## 8. 默认验收方式

优先使用安全验证：

```bash
python -m py_compile <changed_python_files>
```

可以使用 dashboard non-crash / Streamlit AppTest。

禁止为了验证而运行 `python run.py` 或任何危险子命令。

