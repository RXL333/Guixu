# Guixu Conversation Data Model

版本：PHASE D 基础 + PHASE G Plan Versioning，2026-09-20  
范围：持久化数据基础；本文件不定义 Chat UI、Agent loop 或 Tool Calling 实现。

## 1. Conversation ≠ Task

`Task` 仍表示一次扫描/解析/分类/计划/执行工作，拥有当前 task revision、settings、taxonomy、plan 和 operation journal。`Conversation` 是未来长期整理工作空间：它可以保存多轮消息，经历多个不可变 `PlanVersion`，并通过多个 `ExecutionRound` 关联多次既有核心执行。

因此旧 Task 不会被批量伪造成 Conversation；Task 的 `conversation_id` 和 `conversation_plan_version_id` 只在明确建立映射时填写，旧历史仍可独立读取。

## 2. Entity Relationship

```text
Conversation
├── ConversationScope *       (授权 scope 快照，不是路径执行器)
├── ConversationMessage *     (append-only 用户可见历史)
├── ConversationContext 1     (结构化 current state + revision)
├── ConversationFile * ───────> files.id
│                               └── file_profiles.file_id / embedded Evidence
├── ConversationPlanVersion * ─> plans.id (optional)
│                                └── taxonomies.id + immutable snapshot
└── ConversationExecutionRound *
       ├── plan_version_id ───> ConversationPlanVersion.id
       ├── execution_plan_id ─> plans.id
       └── undo_plan_id ──────> plans.id (optional)
                                      └── operations / operation_events

tasks.conversation_id ───────────────> Conversation.id (nullable legacy mapping)
tasks.conversation_plan_version_id ──> ConversationPlanVersion.id (nullable)
```

实现表名：`conversations`、`conversation_scopes`、`conversation_messages`、`conversation_contexts`、`conversation_plan_versions`、`conversation_plan_approvals`、`conversation_execution_rounds`、`conversation_files`。现有核心表保持不变，只给 `tasks` 添加两个 nullable 映射列。

## 3. Conversation

`conversations` 保存 `id/title/status/revision/model_profile_id/metadata_json/created_at/updated_at/deleted_at/last_message_at`。

状态只有会话生命周期：`ACTIVE`、`ARCHIVED`、`DELETED`、`ERROR`。扫描、分析、执行状态属于 Task/Plan/ExecutionRound，不写入 Conversation status。标题默认“未命名整理”，本阶段只支持显式 rename，不调用 LLM 自动命名。

删除是 soft delete：设置 `status=DELETED` 与 `deleted_at`。恢复只清除软删除标记。两者都不调用 FileOperationEngine、Undo 或磁盘删除；子记录和安全 journal 保留。

## 4. ConversationScope

`conversation_scopes` 保存会话绑定的文件夹授权快照：`source_root`、展示名、scope kind、非敏感 `authorization_ref/json`、scope hash 和撤销时间。API 只接受已经由 `SourceRegistry` 注册的 `scope_grant`，不接受任意路径作为授权。

scope 快照不是运行时授权本身。未来 Agent 工具必须重新通过现有 grant/privacy facade 校验，才能访问文件；会话表不保存 API key、原始媒体或 provider 请求。

## 5. ConversationMessage

`conversation_messages` 支持 `USER`、`ASSISTANT`、`SYSTEM_EVENT`，消息类型为 `TEXT`、`STATUS`、`PLAN_PROPOSAL`、`EXECUTION_RESULT`、`ERROR`、`SYSTEM_EVENT`。`sequence_number` 在会话内唯一，消息只追加，不提供静默编辑接口；可见性可通过 `status=REDACTED` 扩展。

消息可以引用 `PlanVersion` 或 `ExecutionRound`，但聊天内容不是系统状态真相。用户要求、当前方案、授权和文件选择必须同步保存到 Context 或其他结构化表。

系统 Prompt 不作为消息 role；模型运行时配置仍属于 ModelProfile/adapter。

## 6. ConversationContext

每个会话一个 `conversation_contexts` 行，包含：

- `context_revision`：并发 compare-and-swap 版本；
- 当前 taxonomy、PlanVersion、ExecutionRound 指针；
- `model_profile_id`、`max_directory_depth`；
- `organization_intent_json`、`confirmed_requirements_json`、`privacy_scope_json`、`selection_state_json`、`strategy_state_json`；
- `file_state_revision` 与创建/更新时间。

`PATCH /context` 必须提交 `expected_revision`。版本不一致返回 `CONTEXT_REVISION_CONFLICT`，不会静默覆盖新状态。普通聊天不增加 context revision；新增确认要求、切换当前方案、绑定执行轮次和更新选择状态属于结构化状态变化。

JSON 只承载适合 JSON 的状态快照；Conversation、Message、PlanVersion、ExecutionRound、FileReference 等关键关系均为明确行和外键。

## 7. PlanVersion

`conversation_plan_versions` 是会话层的不可变方案历史：`version_number`、`parent_plan_version_id`、`basis_context_revision`、source/status、taxonomy 引用/快照、现有 `plan_id/plan_hash`、摘要、变更摘要、影响文件数和时间戳。

支持状态：`DRAFT`、`PROPOSED`、`APPROVED`、`EXECUTED`、`SUPERSEDED`、`CANCELLED`。创建 v2/v3 时追加 child row，不更新 v1；`parent_plan_version_id` 当前是线性历史。一个已有 PlanVersion 只有在创建时绑定 `plan_id`，避免执行“当前模糊方案”。

既有 `plans` 仍负责确定性 `PlanCompiler` 输出、hash、approval 和实际 operation rows；PlanVersion 只负责 Conversation 版本语义。PHASE G 增加 `conversation_plan_approvals` 保存批准时的 plan hash/context revision，并提供确定性 diff、历史恢复 child 和 approval-gated 执行入口；完整规则见 [PLAN_VERSIONING](PLAN_VERSIONING.md)。

## 8. ExecutionRound

当前项目没有独立 `Execution` 表。`plans`（forward/undo）、`operations` 和 `operation_events` 是既有执行事实。因此 `conversation_execution_rounds.execution_plan_id` 和可选 `undo_plan_id` 直接引用既有 Plan；一个 round 必须引用一个 Conversation PlanVersion，且若该版本已有 `plan_id`，执行计划 ID 必须一致。

ExecutionRound 记录 `round_number/status/undo_status/start/completed/summary/affected_file_count`。状态推进只更新执行生命周期字段，不重写其 plan 或消息历史。实际磁盘安全仍由现有 OperationJournal、FileOperationEngine、Recovery 和 UndoCompiler 承担。

## 9. ConversationFile 与 FileProfile/Evidence

`conversation_files` 通过 `file_id -> files.id` 建立稳定关系，并保存 `first_seen_path/current_known_path`、首次/当前 fingerprint、size、mtime、验证时间和 `ACTIVE/FILE_CHANGED/MISSING/REMOVED` 状态。PlanVersion restore 在创建新 child 前复用这套 fingerprint 校验，不重放旧路径。

路径是 location projection，不是 identity。现有执行 journal 在 move/undo checkpoint 中更新 `files.current_path`，`files.id` 保持不变；ConversationFile 因此能在路径从 A 变成 B 后继续引用同一文件。内容验证复用 `read_identity`/SHA-256：文件内容变化会标记 `FILE_CHANGED`，缺失标记 `MISSING`。

当前 `files.id` 的 UUID5 生成范围是单个 Task（以 task UUID 和初始 path 为输入），所以 PHASE D 明确保证“Task 内移动稳定”，没有偷偷宣称已完成跨 Task 的全局文件合并。跨 Task canonical identity 需要后续独立迁移；Conversation 不再新建第二套 file identity。

`FileProfile` 与其中的 Evidence 仍是唯一解析/证据来源。ConversationFile 不复制 OCR、摘要或视觉描述；它只引用 `files`，由 `file_profiles.file_id` 继续关联证据。

## 10. ToolCall / ToolResult 决策

本阶段 deferred。虽然 GitHub 研究建议未来采用 AgentFS 类 pending/result ledger，但当前没有 AgentOrchestrator、工具白名单或调用生命周期，提前建立表会冻结尚未确定的 payload/重放语义。

下一阶段如果需要，建议以独立 `tool_calls/tool_results` 表追加 `conversation_id/message_id/round_id/tool_name/arguments_hash/status/timestamps/result/error`，不把工具参数作为路径执行入口；迁移不会改变本阶段实体。

## 11. File Identity 与内容指纹

使用三层事实：

1. `files.id`：Guixu 当前核心业务 ID；ConversationFile 和 Operation 使用它。
2. `sha256 + size + mtime_ns`：内容/观察 fingerprint；用于验证和 evidence freshness。
3. `volume_id + filesystem_file_id`：Windows/系统文件身份观察值；辅助判断同卷移动，不能独立替代业务 ID。

文件移动只更新路径 projection；文件内容改变会让 ConversationFile 验证状态失效。模型或消息中的路径文字不会进入执行器。

## 12. Plan Versioning 与 Context Revision

Context 更新要求 expected revision；PlanVersion 保存产生它时的 `basis_context_revision`。创建新 PlanVersion 和 ExecutionRound 会推进当前 Context pointer，并在事务中以旧 revision 做 CAS。冲突会回滚整个插入事务，避免孤儿版本。PHASE G 的恢复基于当前 file identity/path/fingerprint 创建新的 PROPOSED child，不能直接重放旧路径；新版本会使旧 active approval 失效。

PlanVersion/ExecutionRound/Message 的历史事实不会被后续请求覆盖；只有 Context current pointer 可以前进。恢复旧方案的未来实现必须基于当前 file identity/path/fingerprint 重新预览，不能直接重放旧路径。

## 13. Soft Delete 与 Legacy Compatibility

Conversation soft delete 不级联删除 Message、Context、PlanVersion、ExecutionRound、ConversationFile，也不影响 Task、Plan、OperationJournal、Undo 或磁盘文件。任务永久删除现在也会阻止存在 ConversationFile 引用的核心文件记录被清掉。

v3→v4 迁移先使用现有 SQLite backup API，再创建新表和 `tasks` nullable columns；v4→v5 迁移新增 PlanVersion 计数字段和 `conversation_plan_approvals`。旧 Task 不自动生成 Conversation。Fresh schema、运行时迁移和 Alembic revisions `0004`/`0005` 保持同构语义，migration 可重复执行。

模板/规则旧表仍按 PHASE C 策略只作兼容，不被 Conversation 新记录依赖。

## 14. 当前基础 API

| API | 行为 |
|---|---|
| `POST/GET /api/v1/conversations` | 创建（要求已授权 scope grant）/列出 active、deleted、all |
| `GET/PATCH/DELETE /api/v1/conversations/{id}` | 读取、改名/归档、soft delete |
| `POST .../{id}/restore` | 恢复可见性 |
| `GET/POST .../{id}/messages` | 读取/追加消息，不调用模型 |
| `GET/PATCH .../{id}/context` | 读取/expected revision 更新结构化状态 |
| `GET/POST .../{id}/plans` | 读取/追加 PlanVersion |
| `GET .../{id}/plan-versions` | 读取版本历史、当前版本与确定性 diff |
| `POST .../{id}/plan-versions/{version}/approve` | 保存 hash/context 绑定的批准 |
| `POST .../{id}/plan-versions/{version}/restore` | 通过文件状态校验创建恢复 child |
| `POST .../{id}/plan-versions/{version}/execution-rounds` | 仅从 active approval 创建执行轮次 |
| `GET/POST .../{id}/executions` | 读取/建立 ExecutionRound 映射 |
| `GET/POST .../{id}/files` | 读取/绑定稳定 file_id |
| `POST .../{id}/files/{file_id}/verify` | 更新路径/指纹观察状态 |
| `POST .../{id}/tasks` | 显式建立旧 Task 映射 |

这些 endpoint 只是持久化 facade，未启动 LLM、Agent、扫描、分类或磁盘执行。

## 15. Future Agent Integration

下一阶段 Chat UI 可将消息写入 Message，将当前意图和确认事实投影到 Context；AgentOrchestrator 读取 Context/PlanVersion/FileReference，而不是重新猜测聊天历史。只读分析应复用 Scanner、Parser/FileProfile、AITaxonomyPlanner 和 AIFileClassifier；写操作仍必须产生既有 PlanCompiler 预览、approval 和 OperationJournal。

## 16. Incremental Replanning 接入点

未来 `revise_proposal` 应使用 `basis_context_revision` 创建 child PlanVersion，并依据稳定 file_id 的 resolved references 计算影响集合；只补缺失 evidence，局部变化仍对最终完整 plan 做确定性冲突/路径检查。不会修改已执行 PlanVersion。

## 17. Undo 接入点

会话层只引用 ExecutionRound 的 forward/undo plan。未来对话式 Undo 应调用现有 UndoCompiler 生成新的 undo Plan，重新检查 fingerprint、后续操作和 approval，再建立新的 ExecutionRound；Conversation 删除永远不隐式触发 Undo。

## 18. 本阶段不包含

没有 ChatGPT 风格页面、自动回复、Tool Calling、Agent loop、增量重规划、Conversational Undo、LangChain/LangGraph/AgentFS/Chroma 或新的分类算法。PHASE D 完成后等待下一阶段确认。

## 19. PHASE H：执行后继续对话扩展

schema v6 在既有关系上做非破坏性扩展：`conversation_plan_versions.baseline_execution_round_id` 固定后续方案的执行基线，`plan_kind` 区分 `FULL/DELTA`；`conversation_files.current_category_id` 保存执行后的当前分类投影。ExecutionRound 完成后同步 current path/fingerprint/category，并推进 Context revision/file revision，但 Conversation 保持 `ACTIVE`。完整行为、安全校验与 API 见 [POST_EXECUTION_CONVERSATION](POST_EXECUTION_CONVERSATION.md)。
