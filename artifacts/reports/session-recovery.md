# Phase K — Session Recovery 阶段报告

日期：2026-09-21  
状态：已完成本阶段代码与自动化验收，保留后续 Agent/桌面人工验收边界。

## 1. 实际交付

- 新增 schema v9 / Alembic `0009_session_recovery`。
- 新增 `conversation_agent_turns`：持久化分析、重规划、执行尝试及中断/重试关系。
- 新增 `conversation_reconciliations`：保存启动、打开、操作前和手动核对结果。
- 为 `conversation_plan_versions` 增加 `basis_file_state_revision`，执行前可阻止基于旧工作区状态的方案。
- 新增 `WorkspaceReconciliationService`、`RecoveryValidationService`、`SessionRecoveryService`。
- 新增恢复状态、工作区核对、方案 revalidate、resume/retry、scope relink API。
- Conversation Workspace 增加外部变化、scope 不可用和 AgentTurn 中断提示；无自动模型重放。
- 内容变化继续复用既有 Semantic Cache ledger 并使旧 fingerprint evidence 失效；移动/重命名不改变 stable `files.id`。

## 2. 恢复语义

关闭应用后，Conversation、Message、Context、PlanVersion、ExecutionRound、ConversationFile、FileEvidence、OperationJournal 和 Undo 记录均保留。启动时仅把未结束 AgentTurn 标为 `INTERRUPTED`，把仍有未完成 operation 的执行轮次标为 `RECOVERY_REQUIRED`。用户必须明确选择继续分析、重试或重新核对；系统不自动调用模型、不自动批准、不自动执行、不重放文件操作。

## 3. 工作区核对

支持 `UNCHANGED`、外部重命名/移动、`MODIFIED_EXTERNALLY`、`FILE_MISSING`、`PATH_CONFLICT`、`NEW_FILE` 和 `SCOPE_UNAVAILABLE`。路径只是 projection；唯一 fingerprint 找到新路径时只更新 `conversation_files.current_known_path` 与核心 `files.current_path`。新文件只显示摘要，不自动加入 Conversation 或触发 AI。

相关计划只在受影响 file_id 改变时进入 revalidation；scope 不可用会阻止执行并保留历史可读性。relink 必须提交已授权 `scope_grant`，不会静默扩大访问范围。

## 4. 主要文件

- [session_recovery.py](../../backend/src/guixu/application/session_recovery.py)
- [0009_session_recovery.py](../../backend/migrations/versions/0009_session_recovery.py)
- [SESSION_RECOVERY.md](../../docs/SESSION_RECOVERY.md)
- [session-recovery-audit.md](session-recovery-audit.md)
- [test_session_recovery.py](../../backend/tests/integration/test_session_recovery.py)

## 5. API

`recovery-status`、`reconcile`、`revalidate-plan`、`resume-analysis`、`external-changes`、`relink-scope`、`agent-turns` 和 `agent-turn retry` 已加入运行时 OpenAPI 契约 `contracts/openapi-runtime.json`。批准与执行 refinement 入口会先做方案 revalidation，再进入现有 PlanApproval/FileOperationEngine/OperationJournal 路径。

## 6. 验收命令

| 检查 | 结果 |
|---|---|
| `uv --directory .\\backend run pytest -q` | **169 passed, 2 warnings** |
| `uv --directory .\\backend run pytest -q tests/integration/test_session_recovery.py` | **4 passed** |
| `npm.cmd run test -- --run` | **4 files / 31 passed** |
| `npm.cmd run typecheck` | **exit 0** |
| `npm.cmd run build` | **exit 0** |
| `uv --directory .\\backend run python ..\\scripts\\export_runtime_contract.py` | **exit 0** |
| `git diff --check` | **exit 0**（仅有 Git 的 CRLF 提示） |

警告为既有 Starlette deprecation、Pillow decompression bomb 提示和 Windows pytest 临时 reparse 目录清理提示；均未改变退出码。

## 7. 未做与剩余风险

- 没有实现 Chat UI、AgentOrchestrator、Tool Calling、Incremental Replanning、Watch Folder 或 Conversational Undo。
- resume/retry 只创建新的持久化 AgentTurn，实际模型 worker 由后续阶段接入。
- scope relink 依赖现有授权 grant；不可用目录不会被猜测或自动替换。
- 未进行新的真实 DeepSeek/Qwen 请求；Phase K 复用现有 Semantic Cache 与 AI-only 回归。
- 未在本阶段重新执行 pywebview 原生桌面人工截图；自动化前端测试、typecheck 和 production build 已通过。

## 8. 下一阶段切入点

下一阶段应先在 Chat UI 中消费 `recovery-status` 和 AgentTurn 状态，再把一次用户消息绑定到 AgentTurn checkpoint；模型循环与 Tool Registry 仍必须沿用现有 scope、PlanApproval、FileOperationEngine、OperationJournal 和 Undo 安全边界。
