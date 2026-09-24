# Phase K Session Recovery 实施计划

## 目标

为现有 Conversation 数据层增加安全的应用重启恢复：启动只恢复持久化元数据；打开会话时按授权 scope 做轻量工作区对账；不自动批准、执行或重放任何 Agent/文件操作。

## 范围与顺序

1. 审计现有 Conversation、Task、OperationJournal、Semantic Cache、前端 store 与启动生命周期，输出 `artifacts/reports/session-recovery-audit.md`。
2. 以非破坏迁移新增恢复快照/AgentTurn 状态字段与 workspace reconciliation 记录，保留旧 Task、Plan、Journal、Undo。
3. 实现 `SessionRecoveryService`、`WorkspaceReconciliationService`、`RecoveryValidationService`：读取历史、把 RUNNING/QUEUED turn 变为 INTERRUPTED、按 file_id/fingerprint 检测外部变化、更新 file_state_revision、使受影响方案需要重新校验。
4. 暴露最小 recovery-status/reconcile/revalidate/resume API；resume 只创建新的分析入口，不重放旧请求。
5. 接入 Conversation store 和 Workspace UI：恢复提示、外部变化摘要、scope unavailable、plan revalidation、interrupted analysis/execution 卡片。
6. 增加重启、外部移动/重命名/修改/缺失/新增、缓存复用、方案 stale、AgentTurn 中断和执行 journal 安全测试。
7. 更新 `docs/SESSION_RECOVERY.md`、阶段报告和 `PROJECT_STATUS.md`。

## 关键决策

- SQLite/backend 是真相源；前端选中文件等 ephemeral state 不恢复。
- 快速校验使用 `stat`，只在需要定位移动或确认 fingerprint 时读取 SHA-256；不在 app startup 扫描所有历史 scope。
- Reconciliation 只更新 ConversationFile 当前投影和 Context revision，不改写历史 Message、PlanVersion、ExecutionRound。
- 已批准但未完成的方案保持查看能力，任何执行前均需 recovery validation；无关新增文件不强制重算整个方案。
- 真实执行中断继续复用现有 OperationJournal/RecoveryService，禁止整批盲重放。

## 验收

- 后端与前端恢复 API 可用；旧数据库可升级；165+ 后端与既有前端回归不退化。
- 重启后 Conversation/Message/Context/Plan/Execution/File References/Semantic Cache 可读。
- 外部文件变化有结构化状态；scope 不可用时历史仍可打开；模型不可用不阻塞历史查看。
- 不自动执行、不自动批准、不自动重放模型请求、不修改真实文件。
