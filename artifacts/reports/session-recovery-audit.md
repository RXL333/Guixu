# Session Recovery 审计

日期：2026-09-21

## 当前事实

- Conversation、Message、Context、PlanVersion、ExecutionRound、ConversationFile、MessageFileReference 和 `file_evidence` 已经持久化在 SQLite；`ConversationRepository` 是主要读写边界。
- Task、Plan、Operation、OperationEvent、TaskEvent 和 `SqliteOperationJournal` 是既有扫描/执行事实。Task 有 `checkpoint_json` 与 `RECOVERY_REQUIRED`，启动时 `TaskCoordinator.audit_startup()` 会把异常遗留的 RUNNING 任务转入恢复状态。
- FileProfile 仍是 parser snapshot，Semantic Cache 的 `file_evidence` 按 file_id/fingerprint/kind 复用；重启后数据库行仍可读，进程内命中计数会重新开始。
- 当前没有持久化 AgentTurn/Conversation Job 表，RUNNING/QUEUED 的会话分析状态无法在重启后表达，也没有统一的 recovery-status API。
- `WorkspaceStateService` 已能对已知 ConversationFile 做 SHA-256 校验和路径回写，但只覆盖已知文件：无法区分 scope 不可用、NEW_FILE、外部移动/重命名，也会把所有 active approval 一起置 stale。
- 现有前端 `conversationStore.loadConversation()` 已从 API 并行读取会话、消息、context、文件、方案和执行轮次；临时选择状态会在加载时清空。没有恢复 banner、外部变化摘要、AgentTurn 中断卡片或方案重新校验动作。
- 正常 app shutdown 仅由 FastAPI lifespan 关闭数据库；文件执行的 crash 安全性来自 OperationJournal 的事务 checkpoint 与既有 `RecoveryService`，不依赖日志文本。

## 主要风险

1. 关闭应用期间外部文件状态会与 ConversationFile 的 last-known projection 不一致。
2. 已批准方案可能基于旧 Context/File State，不能在 restart 后直接执行。
3. 未持久化的 AgentTurn 会导致 UI 误显示 RUNNING，或错误重放模型请求。
4. scope 缺失时不能把历史会话误判为 404，也不能扩大授权范围。

## Phase K 设计边界

新增轻量 `conversation_agent_turns`、`conversation_reconciliations` 与 PlanVersion 的 `basis_file_state_revision`；恢复服务只创建新的 retry/resume 记录、执行 quick stat/必要 fingerprint 检查并复用已有 evidence/journal。不会自动批准、执行、重放模型请求、全盘监控或修改历史事实。
