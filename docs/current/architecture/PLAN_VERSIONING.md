# Guixu Plan Versioning

版本：PHASE G，2026-09-20。本文定义 Conversation 层的不可覆盖方案历史；不实现增量重规划、自然语言推理或 Conversational Undo。

## 1. 边界与复用

`ConversationPlanVersion` 是 Conversation 的版本语义，不替代现有 `plans`。现有 `plans`、`operations`、`operation_events`、PlanCompiler 的 hash/approval 和 FileOperationEngine 继续承担可执行事实。一个版本最多引用一个现有 `plans.id`；一个 `ExecutionRound` 必须通过 `plan_version_id` 固定到该版本，并且 `execution_plan_id` 必须与版本的 `plan_id` 一致。

```text
Conversation
├── ConversationContext (CAS revision + current_plan_version_id)
├── PlanVersion v1 ──> existing Plan ──> operations / journal / undo facts
├── PlanVersion v2 (parent=v1)
├── PlanVersion v3 (parent=v2, possibly restored_from=v1)
└── ExecutionRound #n ──> exactly one PlanVersion + existing execution Plan
```

## 2. 表与字段

`conversation_plan_versions` 增加/使用：

- `version_number`：会话内从 1 开始、唯一递增；
- `parent_plan_version_id`：当前只允许线性历史的当前版本作为 parent；
- `basis_context_revision`：生成该方案时的结构化 Context revision；
- `source/status`：USER_REQUEST、SYSTEM、LEGACY 与 DRAFT、PROPOSED、APPROVED、EXECUTED、SUPERSEDED、CANCELLED；
- `plan_id/plan_hash`：现有确定性 Plan 的引用与内容锁；
- `taxonomy_snapshot_json`、`change_summary_json`：当时的展示/审计快照，不是运行时状态真相；
- `affected_file_count/kept_file_count/conflict_count`：确定性摘要；
- `created_by_message_id`、`restored_from_version_id`：可选审计关系。

版本记录不提供覆盖式编辑。生命周期状态是受控迁移（例如 APPROVED、SUPERSEDED），方案内容、父关系、hash 和版本号不变。创建新版本不会伪造历史任务，也不会删除旧 Plan 或操作日志。

## 3. 版本创建与并发

`POST /conversations/{id}/plans` 必须携带 `expected_context_revision`（可省略但推荐提供）和 `basis_context_revision`。服务在一个 SQLite 事务内检查：

1. Conversation Context 存在且 revision 未变化；
2. basis 不晚于当前 Context；
3. parent 属于同一会话，并且是 current pointer；
4. `plan_id` 存在时，传入 hash 与现有 `plans.plan_hash` 相同；
5. 版本号由唯一约束保护，冲突返回 `PLAN_VERSION_CONFLICT`；
6. 插入后 CAS 前进 `current_plan_version_id` 和 Context revision；
7. 旧版本只在其仍处于 DRAFT/PROPOSED/APPROVED 时标为 SUPERSEDED，EXECUTED 事实不会被伪装成未执行。

因此快速并发请求不会静默覆盖当前方案；失败请求回滚，不留下孤儿版本。`MAX(version_number)+1` 只是候选值，最终由 `(conversation_id, version_number)` 唯一键和重试/冲突映射提供保护。

## 4. Diff

`PlanDiffService` 不调用模型。它读取两个版本的 taxonomy snapshot 和现有 Plan operation rows，按稳定 `file_id` 排序，输出：

- 新增/删除/重命名/重挂载分类；
- `UNCHANGED`、`ADDED`、`REMOVED`、`TARGET_CHANGED`、`KEEP_CHANGED`、`CONFLICT_CHANGED` 文件差异；
- affected file ids 与 summary counts。

`GET /conversations/{id}/plan-versions/{version_id}/diff?from_version_id=...` 默认比较 parent。没有 parent 的 v1 返回空差异，不会猜测或调用 AI。

## 5. Approval 与执行绑定

`conversation_plan_approvals` 是 Conversation 层的 approval ledger。它保存批准时的 `plan_id`、`plan_hash`、`context_revision`、授权快照和 ACTIVE/STALE/REVOKED 状态。批准前会重新验证当前指针、Plan hash 和既有 Plan 状态。

创建后续版本、修改 Context 或改变当前指针都会使旧 ACTIVE approval 变为 STALE。只有 ACTIVE approval 才能调用：

`POST /conversations/{id}/plan-versions/{version_id}/execution-rounds`

该 endpoint 固定 `plan_version_id`、Plan hash 和 approval context revision，再创建既有 `conversation_execution_rounds` 映射；未批准、过期、hash 不一致或非 current 版本均返回结构化冲突，不启动文件操作。PHASE D 的旧 `/executions` endpoint 保留用于兼容，但新版本执行入口应使用上述受保护 endpoint。

## 6. 恢复

恢复不是把旧行改回去，也不是重放旧路径。`POST .../plan-versions/{version_id}/restore`：

1. 检查 current pointer 和 Context CAS；
2. 验证 ConversationFile 的当前 path、存在性和 fingerprint；
3. 复用目标版本的 Plan/hash/snapshot；
4. 创建新的 PROPOSED child version，并写入 `restored_from_version_id`；
5. 等待新的 approval 后才能执行。

文件缺失、内容改变、引用已移出授权 scope 或 Context 已过期时，恢复被阻止，不移动/删除任何磁盘文件。

## 7. API

| Endpoint | 作用 |
|---|---|
| `GET /conversations/{id}/plan-versions` | 版本历史 |
| `GET /conversations/{id}/plan-versions/current` | 当前指针 |
| `GET /conversations/{id}/plan-versions/{version_id}` | 单版本 |
| `GET .../{version_id}/diff` | 确定性差异 |
| `POST .../{version_id}/approve` | 绑定 hash/context 的批准 |
| `POST .../{version_id}/restore` | 创建恢复 child 版本 |
| `POST .../{version_id}/execution-rounds` | 仅从 ACTIVE approval 创建执行轮次 |

这些 API 只保存/校验数据，不调用 LLM、不启动 Agent、不执行 Tool Calling。

## 8. 前端行为

Conversation Workspace 的“整理预览”显示当前版本号和状态；用户可以切换 v1/v2/v3 查看历史。历史方案明确标注“这是历史方案，不代表当前整理状态”，并显示确定性差异摘要。恢复按钮只请求创建新方案，不直接执行或修改真实文件；审批和执行入口留给后续 Agent/执行审阅阶段。

## 9. Migration 与兼容

schema version 从 v4 升至 v5，Alembic revision 为 `0005_plan_versioning.py`。fresh schema 同时创建四个 PlanVersion 审计字段和 `conversation_plan_approvals`；v4→v5 运行时迁移先使用现有 SQLite backup，再以幂等 `ALTER TABLE`/`CREATE TABLE IF NOT EXISTS` 补齐。SQLite 对迁移新增列不能追加 FK，因此服务层显式校验 message/version/plan 归属；新库的 contract schema 仍声明 FK。

旧 Task 不自动创建 Conversation，也不需要 PlanVersion；Task、Plan、OperationJournal、Undo 以及真实文件均不受版本历史删除影响。ToolCall/ToolResult、增量重规划和 Conversational Undo 延后，不在 PHASE G 添加表。

