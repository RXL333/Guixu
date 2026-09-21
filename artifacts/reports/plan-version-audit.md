# PHASE G —— PlanVersion 审计

日期：2026-09-20

## 审计范围

已阅读：

- `PROJECT_STATUS.md`
- `docs/CONVERSATION_DATA_MODEL.md`
- `artifacts/reports/conversation-data-model.md`
- 当前 `conversation_plan_versions` schema、runtime schema helper 与 Alembic v4 migration
- `ConversationRepository` / `ConversationService` / Conversation API schemas
- 现有 `plans`、`operations`、`operation_events`、`SqliteOperationJournal`
- `ConversationContext`、`context_revision`、`ExecutionRound`
- `frontend` conversation store、`PlanPreviewCard`、`FileWorkspace`

以下两个用户要求的前置产物当前不存在，已作为审计事实记录，而不是按旧设计文档假定它们已经实现：

- `docs/CONVERSATION_AGENT_V1.md`：MISSING
- `artifacts/reports/conversation-agent-v1.md`：MISSING
- `AgentOrchestrator` / `revise_plan` / `preview_changes` / `request_execution`：当前源码未找到 Conversation Agent V1 实现

## IMPLEMENTED

- `conversation_plan_versions` 已建立，具有 `id`、`conversation_id`、`version_number`、`parent_plan_version_id`、`basis_context_revision`、`source`、`status`、`taxonomy_id`、`taxonomy_snapshot_json`、`plan_id`、`plan_hash`、`summary`、`change_summary_json`、`affected_file_count`、时间字段。
- `(conversation_id, version_number)` 数据库唯一约束已存在。
- `PlanVersion` 通过 `plan_id` / `plan_hash` 引用既有 `plans`，没有复制 `PlanItem`。
- 创建时默认连接同一 Conversation 的最新版本作为 parent，并在同一事务中尝试更新 `conversation_contexts.current_plan_version_id`。
- `basis_context_revision` 与 `expected_context_revision` 已存在，CAS 冲突返回 `CONTEXT_REVISION_CONFLICT`。
- `ExecutionRound` 已有 `plan_version_id` 与 `execution_plan_id`，并且会检查版本计划与执行计划的一致性。
- `Message` 已有可选 `referenced_plan_version_id`。
- 既有 `plans` 具有 `plan_hash`、`plan_basis_revision`、`approved_task_revision`、`approved_at`、`authorization_json`；`SqliteOperationJournal` 已拒绝错误 hash 和旧 task revision。
- 旧 Task / Plan / Operation Journal / Undo 仍然由既有核心表承载，PHASE G 不需要复制这些实体。

## PARTIAL

- PlanVersion 创建 API 只有 `POST /conversations/{id}/plans` 与列表 API，没有单版本 GET、diff、restore、current endpoint。
- `create_plan_version()` 使用 `MAX(version_number)+1`，虽有 unique constraint，但没有稳定的冲突重试/领域错误映射；并发请求可能把 SQLite `IntegrityError` 暴露为 500。
- PlanVersion 内容没有 service-level immutable guard；仓储没有更新接口，但数据库没有禁止直接修改核心内容字段。
- `status` 只覆盖 DRAFT/PROPOSED/APPROVED/EXECUTED/SUPERSEDED/CANCELLED，缺少明确的 `WAITING_FOR_APPROVAL` 语义；生命周期与“当前/已执行”维度尚未分离。
- 创建新版本不会自动将旧当前版本标记为 SUPERSEDED，也没有保留“已执行版本仍为 EXECUTED”的规则。
- Approval 仍然绑定 `plans.id + plan_hash + task revision`，没有 `plan_version_id` 级别的明确版本授权记录或 stale approval API。
- ExecutionRound 存储版本关系，但创建 API 没有验证 PlanVersion 的 hash、当前状态、当前 context revision 或实际执行前文件状态。
- `taxonomy_snapshot` 只接受调用方传入，没有 deterministic PlanDiff 或基于现有 `plans`/`operations` 的变更统计。
- 现有前端仅显示 `vN` 字样，PlanPreviewCard 的按钮没有行为；store 只加载完整列表，没有 current/viewing/diff/version loading 状态。
- File Workspace 只显示当前文件/空方案/执行记录，不支持历史版本预览，也没有“历史方案不代表当前状态”的提示。

## MISSING

- `PlanVersionService` 作为唯一版本真相源。
- `PlanDiffService`：基于稳定 `file_id` / category / target / keep / conflict 的 deterministic diff。
- `restored_from_version_id`、`created_by_message_id` 关系字段。
- 单版本读取、current、diff、restore API。
- Restore → new version 事务与 scope/fingerprint/file-state 验证。
- 版本级 Approval 绑定与 `PLAN_APPROVAL_STALE` / `PLAN_HASH_MISMATCH` 领域错误。
- 执行入口对 Conversation PlanVersion 的强绑定与 `PLAN_CONTEXT_STALE` / file state stale 拒绝。
- 历史版本 UI、版本下拉、diff panel、restore action、current/approved/executed 状态显示。
- PlanVersion 关联的真实系统事件/assistant message 写入（当前没有 Agent V1，不在本阶段伪造）。
- 并发创建版本的自动化测试、diff/restore/stale approval/hash/file-change 测试。

## INCORRECT / 风险

- `MAX(version_number)+1` 不是完整的并发版本分配策略；unique constraint 只能兜底，不能向 API 提供可理解的冲突语义。
- 当前创建版本会无条件推进 `conversation_contexts.context_revision`，且没有把“创建版本”与“真实 Context 变更”区分开；新服务应要求明确的 basis/expected revision，并在一次事务中保护 current pointer。
- 当前 ExecutionRound 的 `plan_version_id` 可以指向一个没有 hash、没有 approval、不是当前版本的 PlanVersion；这违反“执行只能绑定明确且已授权版本”的阶段目标。
- 旧版本后续不会自动失效旧 Approval，也没有明确阻止通过旧的 plan API 执行新版本语义。
- 当前前端的“查看方案版本”是无行为按钮，可能让用户误以为已经支持历史查看。

## 复用结论

- 继续复用 `plans`、`operations`、`operation_events`、`files`、`taxonomies/categories`、`conversation_contexts` 与 `conversation_messages`。
- 不创建第二套 PlanItem、Execution、File 或 Agent runtime 表。
- 在现有 `conversation_plan_versions` 上做最小 schema 扩展，在既有核心 plan/approval/execution 入口上增加版本校验。
- Agent V1 缺失不阻塞版本基础设施；本阶段不补做 Agent Orchestrator，只提供其未来调用的 service/API 接口。

