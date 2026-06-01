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
