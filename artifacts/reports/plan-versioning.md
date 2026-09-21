# PHASE G — Plan Versioning 实现报告

日期：2026-09-20  
状态：PASSED（PHASE G 范围内）。本阶段只建立方案版本基础设施，未实现增量重规划、Conversational Undo、Agent Orchestrator 或 Tool Calling。

## 1. 修改前审计

审计报告见 [plan-version-audit](plan-version-audit.md)。现状只有 PHASE D 的 `conversation_plan_versions` 基础存储、Context current pointer 和 ExecutionRound 映射：没有版本服务、差异 API、恢复语义、Conversation approval ledger、stale/hash 保护或历史前端。用户要求中的 PHASE F Agent V1 产物在当前工作树不存在，因此没有伪造其完成状态；本阶段只把 PlanVersion 基础补到可被未来 Agent 接入的边界。

## 2. 新增/修改数据

- `backend/migrations/versions/0005_plan_versioning.py`：v4→v5 幂等迁移，保留 SQLite migration backup 和显式禁止 destructive downgrade。
- `conversation_plan_versions`：新增 `kept_file_count`、`conflict_count`、`created_by_message_id`、`restored_from_version_id`。
- `conversation_plan_approvals`：新增 Conversation 层批准快照/状态表，唯一绑定一个 PlanVersion，保留 plan hash/context revision。
- fresh `contracts/database.sql`、运行时 Database helper 和 Alembic 保持同构语义；迁移新增列的 SQLite FK 限制由 service 归属校验补偿。
- `app.state.plan_versions` / `PlanVersionService` / `PlanDiffService`：将版本规则集中于 service/repository，而不是 controller 内写 ORM/SQL。

复用：`plans`、`operations`、`operation_events`、`tasks`、`files`、`conversation_contexts`、`conversation_messages`、`conversation_execution_rounds`。没有重写 Planner、Classifier、FileOperationEngine、Undo 或复制 FileProfile/Evidence。

## 3. 版本规则

- Conversation 内版本号按唯一约束递增；parent 必须是当前 pointer，失败返回 `PLAN_VERSION_PARENT_NOT_CURRENT`。
- basis_context_revision 不能晚于当前 Context；Context CAS 失败不会留下插入行。
- 已绑定 Plan 时重新读取并核对 `plans.plan_hash`；不一致返回 `PLAN_HASH_MISMATCH`。
- 旧版本内容不覆盖；只允许受控生命周期状态推进。已执行版本不会因为后续方案被重写。
- 每次新版本都会使旧 ACTIVE approvals 失效；Context 更新也会使 ACTIVE approval 变为 STALE。

## 4. Diff / restore / execution

`PlanDiffService` 按 `file_id` 对现有 operations 做确定性比较，并对 taxonomy snapshot 输出分类新增、删除、重命名/重挂载及文件目标/保留/冲突变化。没有模型调用。

恢复会检查会话内 ConversationFile 的当前 fingerprint、存在性和授权 scope，使用目标 Plan/hash 创建新的 PROPOSED child，写入 `restored_from_version_id`；不会修改旧行、执行 Undo 或触碰真实文件。

新执行 endpoint 必须经过 ACTIVE `conversation_plan_approvals`，校验 current pointer、plan hash 和 approval context revision 后才创建 ExecutionRound。旧 `/executions` facade 保留给 PHASE D 兼容，不代表新版本可绕过 approval 的推荐入口。

## 5. 前后端 API

新增：

- `GET /api/v1/conversations/{id}/plan-versions`
- `GET /api/v1/conversations/{id}/plan-versions/current`
- `GET /api/v1/conversations/{id}/plan-versions/{version_id}`
- `GET /api/v1/conversations/{id}/plan-versions/{version_id}/diff`
- `POST .../{version_id}/approve`
- `POST .../{version_id}/restore`
- `POST .../{version_id}/execution-rounds`

Conversation Workspace 的整理预览现在支持 v1/v2/v3 历史切换、历史状态提示、确定性差异摘要和“恢复为新方案”入口。恢复只创建新版本，不直接执行。

## 6. 测试证据

- `backend/tests/integration/test_plan_versioning.py`：2 passed，覆盖 v1→v2→v3→恢复 child、parent/版本号、taxonomy/file diff、approval、hash/context 绑定、执行轮次、approval stale、文件 fingerprint 改变时阻止恢复。
- `backend/tests/integration/test_conversation_data_model.py`：2 passed，确认 PHASE D 会话/消息/Context/文件/执行/重启继续工作。
- 全后端回归：`backend/tests -q`，149 passed，0 failed（包含 3 个将旧 schema v4 断言更新为 v5 的测试、1 个 v4→v5 Alembic 增量测试，以及 2 个 PHASE G 专项测试）。
- 前端：`npm.cmd run test -- --run`，4 files / 25 passed；`npm.cmd run typecheck` exit 0。
- OpenAPI：`scripts/export_runtime_contract.py` exit 0，运行时 contract 已重新导出。

非阻塞 warning：Starlette/第三方 deprecation、Pillow 边界测试 warning、Windows pytest reparse 临时目录清理 WinError 145；不影响退出码，也没有测试路径删除用户文件。

## 7. 已知债务与安全边界

- `MAX(version_number)+1` 仍是候选分配方式，最终安全性依赖 SQLite 唯一约束和冲突回滚；高并发下会返回显式 conflict，不承诺无锁队列。
- SQLite v4→v5 ALTER 新列不能追加 FK；service 对 message/version/plan 所属做强校验，新数据库 contract 保留 FK。
- 现有 `files.id` 仍是 Task 内稳定身份，跨 Task 的全局 canonical identity 未在本阶段重做；Conversation 不创建第二套 File 表。
- ToolCall/ToolResult、Agent Orchestrator、增量重规划、自然语言回复和 Conversational Undo 均 deferred。
- 旧 PHASE D `/executions` API 仍可直接创建兼容 ExecutionRound；下一阶段应逐步让 UI/Agent 只使用 approval-gated endpoint，再考虑 deprecate 旧 facade。

## 8. 下一阶段切入点

下一阶段可在不改 schema 核心关系的前提下接入 AgentOrchestrator：读取 Context → 生成/保存 Message → 创建 PROPOSED PlanVersion → 展示 diff → 用户批准 → 通过 approval-gated execution endpoint 创建 ExecutionRound。ToolCall ledger 和 reference resolver 应先独立设计，不把路径或模型 provider 细节放入 Conversation。
