# PHASE D — Conversation Schema Audit

日期：2026-09-20  
范围：迁移前只读审计；本报告不代表已实现 Conversation 功能。

## 1. 当前持久化方式

Guixu 当前没有 SQLAlchemy Declarative ORM。运行时使用 SQLAlchemy Engine/Connection 与原生 SQL，空库由 `contracts/database.sql` 初始化，增量升级由 `backend/src/guixu/infrastructure/db/database.py` 和 Alembic revisions 共同维护。当前 schema version 为 v3，最近一次迁移 `0003_task_soft_delete`。

## 2. 已有表与职责

| 现有表 | 当前职责 | PHASE D 决策 |
|---|---|---|
| `tasks` | 一次扫描/分析/规划/执行工作的聚合、revision、设置、快照、状态 | 保留；增加 nullable `conversation_id` 与 `conversation_plan_version_id` 映射，不把 Conversation 变成 Task 子类 |
| `task_scopes` | Task 的扫描/输出 scope 与授权边界快照 | 保留；新会话用独立 `conversation_scopes` 保存其授权 scope，必要时可记录来源 TaskScope |
| `files` | Task 内扫描到的文件、original/current path、size/mtime、Windows identity、sha256、scan 状态 | 复用 `files.id` 作为当前核心 file_id；移动时只更新 path projection |
| `file_profiles` | 按 file_id/cache key 存 parser profile/evidence JSON | 复用，不复制到 Message/ConversationFile |
| `taxonomies/categories` | Task scope 下的分类树版本与节点 | PlanVersion 可选引用 taxonomy，并保存必要 taxonomy snapshot |
| `plans/operations/operation_events/created_directories` | 版本化 plan、实际操作、journal/checkpoint、undo plan | ExecutionRound 只引用既有 plan；不新建第二套执行日志 |
| `task_events` | Task 生命周期事件 | 保留，Conversation 事件另存在 Message/Context 结构化状态 |
| `model_profiles` | provider/model capability 配置 | Conversation 只引用 `model_profile_id`，不复制 provider secret |
| `privacy_consents` | Task 级出站数据授权与预算 | ConversationContext 保存授权摘要/引用，不把 key 或 provider 请求细节写入会话 |
| `template_versions/rules` | PHASE C 后仅旧任务兼容 | 不被新 Conversation 写入或依赖 |

## 3. 现状差距

当前不存在：Conversation、Message、ConversationContext、PlanVersion、ExecutionRound、ConversationFile、独立 Conversation scope。也不存在独立 `Execution` 表；实际执行由 `plans` 的状态、`operations` 行和 `operation_events` journal 表示。

## 4. 复用与关系结论

1. Conversation 不复制 Task 的 settings、taxonomy、plan 或 execution JSON；新表通过 nullable FK/引用连接现有核心。
2. `files.id` 是现有业务稳定主键，`FileProfile.file_id` 与 operation `file_id` 已使用它。当前生成策略是 task UUID + 初始路径的 UUID5，因此稳定范围是 Task 内；PHASE D 不重写已有 identity 体系，只在 ConversationFile 中禁止以 path 作为关系主键，并记录指纹/路径观察值。跨 Task 的 canonical identity 合并继续作为后续独立迁移项。
3. `files.current_path` 在 operation journal 的 COMMITTED/UNDONE checkpoint 中更新，因而同一 file_id 可跨移动保持引用。ConversationFile 会保存 first/current path 和 fingerprint，并提供验证状态 `ACTIVE`/`FILE_CHANGED`/`MISSING`。
4. 当前 `files.sha256` 可能在初始扫描为空；ConversationFile attach 时优先复用 sha256，否则使用现有文件 identity 读取强 hash，无法读取时保留 size/mtime 观察值并标记待验证，不制造假 hash。
5. FileEvidence 当前内嵌在 `file_profiles.profile_json` 的 FileProfile.evidence 中，已有 parser/model provenance；PHASE D 只引用 FileProfile，不做 Semantic Cache 重构。
6. Privacy authorization 仍由既有 Task/PrivacyService 管理。Conversation scope 保存授权来源与非敏感快照，后续 Agent 必须在授权 facade 中重新校验，不能把会话字段当成授权本身。

## 5. 目标新增实体

```text
Conversation
├── ConversationScope *
├── Message *
├── ConversationContext 1
├── ConversationFile * ──> files ──> file_profiles / embedded Evidence
├── PlanVersion * ────────> plans ──> operations / operation_events
└── ExecutionRound * ─────> plans (forward + optional undo)
                              └── existing Task via plans.task_id
```

新增表：`conversations`、`conversation_scopes`、`conversation_messages`、`conversation_contexts`、`conversation_plan_versions`、`conversation_execution_rounds`、`conversation_files`。`tasks` 增加两个 nullable 映射字段。

## 6. 非目标与安全约束

- 不实现 Chat UI、LLM loop、Agent、ToolCall/ToolResult runtime、增量重规划或 conversational undo。
- Conversation soft delete 只改会话可见性；不得 cascade 删除 `plans`、`operations`、`operation_events`、`files` 或磁盘内容。
- PlanVersion/ExecutionRound/Message 只追加；当前指针通过 Context 更新，更新必须受 revision 保护。

## 7. 迁移要求

v3→v4 必须先调用现有 SQLite backup API；所有新列/表使用 `IF NOT EXISTS` 或列探测，旧 Task 不自动伪造成 Conversation。旧数据库升级后仍可读取原任务、Undo 与 operation journal。fresh schema 与 Alembic/运行时迁移必须保持同构。

## 8. 审计结论

可以在现有核心之上增加薄 Conversation 状态层。最小安全方案是新增关系表、复用稳定 file_id 和既有计划/journal，而不是复制 FileProfile、Execution 或把状态塞入一个 JSON blob。迁移可在不影响当前 AI-only 主链的前提下实施。
