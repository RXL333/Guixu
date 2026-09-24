# Session Recovery / 会话恢复

版本：PHASE K，2026-09-21

本阶段为 Conversation Agent 建立“可关闭、可重新打开、可继续核对”的持久化基础。它不启动 LLM，不自动重放模型请求，不自动批准或执行方案，也不实现 Watch Folder 或 Conversational Undo。

## 1. 持久化边界

```text
Conversation
├── Message（append-only 用户可见历史）
├── ConversationContext（结构化当前状态 + context_revision + file_state_revision）
├── ConversationFile（stable files.id + 当前路径/指纹投影）
├── PlanVersion（不可变方案语义）
├── ExecutionRound（一次明确方案的执行映射）
├── AgentTurn（分析/重规划/执行尝试的可恢复状态）
└── Reconciliation（每次启动/打开/操作前的工作区核对）

ConversationFile ──> files ──> file_profiles / file_evidence
PlanVersion ────────> plans ──> operations / operation_events / Undo
ExecutionRound ─────> existing forward/undo plans and OperationJournal
```

Conversation 仍然不是 Task。Task 继续表示一次扫描、解析、分类或后台分析作业；Conversation 只保存长期会话关系和当前状态。旧 Task 不会被伪造为新会话。

## 2. 启动恢复流程

应用创建时调用 `SessionRecoveryService.audit_startup()`：

1. `QUEUED` / `RUNNING` 的 AgentTurn 标记为 `INTERRUPTED`，原因是 `APP_RESTARTED_DURING_TURN`；不重新发送原请求。
2. `RUNNING` 且仍有未完成 operation 的 ExecutionRound 标为 `RECOVERY_REQUIRED`，继续由既有 OperationJournal/RecoveryService 接管。
3. 打开会话或执行前调用 Workspace Reconciliation，重新核对授权 scope、路径、大小、mtime 和必要时的 SHA-256。
4. UI 展示中断、外部变化和 scope 不可用，用户明确操作后才创建新的 retry/resume 记录。

应用关闭不删除消息、上下文、方案、执行轮次、文件引用、Evidence Cache、OperationJournal 或 Undo 依赖。

## 3. Workspace Reconciliation

`WorkspaceReconciliationService` 只访问当前仍有效的授权 scope。结果状态包括：

- `UNCHANGED`：路径、size/mtime 和 fingerprint 与上次观察一致；
- `RENAMED_EXTERNALLY` / `MOVED_EXTERNALLY`：通过稳定 fingerprint 找到唯一的新路径，并只更新路径 projection；
- `MODIFIED_EXTERNALLY`：内容 fingerprint 改变，ConversationFile 变为 `FILE_CHANGED`，相关 semantic evidence 失效；
- `FILE_MISSING`：无法在授权 scope 内找到唯一匹配；
- `PATH_CONFLICT`：同一 fingerprint 出现多个候选，阻止猜测；
- `NEW_FILE`：scope 中出现但尚未属于会话的新文件，仅报告，不自动绑定或分析；
- `SCOPE_UNAVAILABLE`：目录不可访问、授权已撤销或 scope 不完整。

每次发生变化只推进 `ConversationContext.file_state_revision`。`context_revision` 只由结构化工作状态变更推进，避免把普通外部新增文件误报为用户要求冲突。

Reconciliation 会将变化写入 `conversation_reconciliations`，包含触发来源、scope 状态、revision、摘要、事件和是否需要用户操作。它不执行移动、复制、删除或 Undo。

## 4. PlanVersion revalidation

PlanVersion 保存 `basis_file_state_revision`。批准/执行入口在进入既有 PlanApproval/Execution 逻辑前调用 `RecoveryValidationService`：

- scope 不可用、plan hash 不一致、运行日志存在未完成 operation、相关 ConversationFile 缺失/改变或 fingerprint 不匹配时返回 `PLAN_REVALIDATION_REQUIRED`；
- 不相关的 `NEW_FILE` 不会使已有局部方案失效；
- 方案仍然必须通过现有 hash、authorization、approval、FileOperationEngine 和 OperationJournal 安全边界；
- revalidation 只返回原因和当前 reconciliation，不修改旧 PlanVersion，也不自动生成新计划。

## 5. AgentTurn

`conversation_agent_turns` 是最小持久化 turn ledger，记录 turn kind、状态、请求 hash、checkpoint/result JSON、关联 Task/PlanVersion/ExecutionRound、retry parent 和 interruption code。支持 `QUEUED`、`RUNNING`、`WAITING_FOR_USER`、`WAITING_FOR_APPROVAL`、`COMPLETED`、`FAILED`、`CANCELLED`、`INTERRUPTED`。

Phase K 只提供 CRUD、启动中断标记、`resume-analysis` 和 `retry`。resume/retry 创建新的 turn，保留原记录，不调用模型，不自动执行。未来 AgentOrchestrator 可在 turn 上挂接 checkpoint 与受限 ToolCall ledger。

## 6. Scope relink 与隐私

scope 不可用时历史 Conversation 仍可读取，文件和消息不会被删除。`POST /conversations/{id}/relink-scope` 只接受现有 `SourceRegistry` 生成的 `scope_grant`，要求新目录存在，撤销旧 active scope 后建立新的授权快照，并按 fingerprint 重新关联已知文件；无法唯一关联的文件保持 `MISSING`。不会把路径字符串当作授权，也不会静默扩大范围。

## 7. Semantic Cache 与 FileProfile

Reconciliation 的内容变化会调用既有 `EvidenceCacheService` 使该 stable file 的旧 fingerprint evidence 失效。内容不变或仅移动/重命名时复用 `file_evidence`；不复制 OCR、摘要或视觉描述到会话表。新文件只做摘要展示，不触发 AI 分析。

## 8. API

当前提供：

- `GET /api/v1/conversations/{id}/recovery-status?reconcile=true`
- `POST /api/v1/conversations/{id}/reconcile`
- `POST /api/v1/conversations/{id}/revalidate-plan`
- `POST /api/v1/conversations/{id}/resume-analysis`
- `GET /api/v1/conversations/{id}/external-changes`
- `POST /api/v1/conversations/{id}/relink-scope`
- `GET /api/v1/conversations/{id}/agent-turns`
- `POST /api/v1/conversations/{id}/agent-turns/{turn_id}/retry`

这些 endpoint 是持久化和安全核对 facade；不会调用 LLM、自动回复、自动批准或直接操作真实文件。

## 9. Migration 与兼容

Alembic `0009_session_recovery` 将 schema v8 升级到 v9，新增 `basis_file_state_revision`、`conversation_agent_turns` 和 `conversation_reconciliations`。迁移非破坏性；旧数据库先沿用现有 SQLite backup 流程，旧 Task 的 nullable 会话列与 OperationJournal/Undo 不变。Fresh schema 与 runtime migration 同构。

## 10. 后续接入点

下一阶段 Chat UI 可从 recovery-status 渲染中断与外部变化卡片；AgentOrchestrator 可将一次用户请求绑定 AgentTurn，读取 Context/PlanVersion/FileReference 并在 checkpoint 后更新 turn。任何新方案仍应写入新的 PlanVersion，任何对话式 Undo 都必须创建新的 undo Plan/ExecutionRound 并重新 approval。

本阶段明确不包含：Chat UI 重做、LLM 对话循环、Tool Calling、Incremental Replanning、自动 Undo、Watch Folder 和向量数据库。
