# PHASE D — Conversation Data Model 实现报告

日期：2026-09-20  
状态：PASSED。PHASE D 已完成并在本阶段边界停止；未实现 Chat UI、Agent Orchestrator 或 Tool Calling。

## 1. 审计依据

迁移前已阅读 `PROJECT_STATUS.md`、PHASE C 清理报告、Conversation Agent baseline、GitHub reference analysis、`docs/00_BLUEPRINT.md`、`contracts/database.sql`、当前 Database/Alembic/repository/operation journal、Task/Plan/Taxonomy/FileProfile/Evidence、文件 identity、ModelProfile、PrivacyService 与 API。审计结论见 [conversation-schema-audit](conversation-schema-audit.md)。

当前项目是 SQLAlchemy Engine + 原生 SQL，不是 Declarative ORM；当前没有独立 Execution 表，真实执行记录在 `plans`、`operations`、`operation_events` 中。

## 2. 新增表

- `conversations`：长期会话元数据、生命周期、软删除。
- `conversation_scopes`：授权 scope 的非敏感快照。
- `conversation_messages`：USER/ASSISTANT/SYSTEM_EVENT append-only 历史。
- `conversation_contexts`：一对一结构化当前状态、context revision、current pointers。
- `conversation_plan_versions`：不可覆盖的线性方案版本链；PHASE G 增加恢复来源、摘要计数和创建消息审计字段。
- `conversation_plan_approvals`：PHASE G 新增的批准 hash/context 快照与失效状态。
- `conversation_execution_rounds`：会话执行轮次，映射既有 forward/undo plan。
- `conversation_files`：Conversation 到现有 `files.id` 的稳定引用、路径/指纹观察与变更状态。

## 3. 修改的旧表

`tasks` 增加 nullable `conversation_id` 与 `conversation_plan_version_id`。旧 Task 保持 NULL，不自动生成会话；显式 link 或建立 ExecutionRound 时才填写映射。

## 4. 复用的现有表

`model_profiles`、`task_scopes`、`files`、`file_profiles`/embedded Evidence、`taxonomies/categories`、`plans`、`operations`、`operation_events`、`created_directories`、`privacy_consents`、`task_events` 均保留原职责。ConversationFile 不复制 profile/evidence，ExecutionRound 不复制 operation journal，PlanVersion 不替换 PlanCompiler 输出。

## 5. 最终没有采用的设计

- 没有创建第二套 `File`/semantic cache 表；继续复用 `files.id` 与 FileProfile。
- 没有创建独立 `Execution` 表；使用 `execution_plan_id`/`undo_plan_id` 关联现有 plans + journal。
- 没有把全部 Context 塞进单一不可验证 blob；关键关系均为字段/FK，JSON 仅保存扩展状态。
- 暂不创建 ToolCall/ToolResult 表：当前没有 Orchestrator/tool lifecycle，报告和数据模型文档明确 deferred。
- 没有修改 FileOperationEngine、Planner、Classifier、Taxonomy 或 Undo 算法。

## 6. Migration

schema version 从 v3 升为 v4；PHASE G 再升为 v5。Alembic revisions 为 `0004_conversation_data_model.py` 与 `0005_plan_versioning.py`；运行时 v3→v4→v5 使用同一套幂等 helper。升级前沿用 SQLite backup API，新增表/索引/nullable mapping 可重复执行；downgrade 继续显式禁止破坏性回退。Fresh schema、Alembic head 和 legacy upgrade 均覆盖测试。

## 7. Revision 与不可变历史

Context 通过 `expected_revision` compare-and-swap 更新，冲突返回 `CONTEXT_REVISION_CONFLICT`。创建 PlanVersion/ExecutionRound 也在同一事务中以当前 revision 更新 current pointer，CAS 失败会回滚，避免孤儿版本。Message、PlanVersion、ExecutionRound 不提供覆盖式编辑；执行状态仅推进 round lifecycle 字段。

## 8. Soft delete 与安全边界

Conversation DELETE 只设置 `DELETED/deleted_at`，GET/list 可按 active/deleted/all 查看，restore 仅恢复可见性。未调用文件执行、undo 或删除磁盘文件；FK 对 journal/plan/file 使用 RESTRICT，避免关系删除破坏恢复事实。Task 永久删除若仍被 ConversationFile 引用会被阻止。

## 9. File identity

ConversationFile 的关系键是现有 `files.id`，不是 path。既有 operation checkpoint 移动时只更新 `files.current_path`，文件 ID 不变；验证 endpoint 复用 `read_identity`/SHA-256，路径改变但内容不变保持 ACTIVE，内容变化标记 FILE_CHANGED，缺失标记 MISSING。现有 file_id 的 UUID5 仍是 Task 内稳定范围，跨 Task canonical identity 明确列为后续债务，没有在本阶段偷偷重写核心身份。

## 10. 基础 CRUD / Service / API

新增 `ConversationRepository`、`ConversationService`，并注册无 LLM 的 REST facade：会话创建/列表/改名/归档/soft-delete/restore，消息追加/读取，Context 读取/CAS 更新，PlanVersion 追加/读取，ExecutionRound 映射/读取，ConversationFile 绑定/验证，Task 显式映射。API 创建会话只接受已注册的 source grant，不接受任意路径。

## 11. 测试结果

最终验证：

- `backend/tests/integration/test_conversation_data_model.py`：2 passed，覆盖会话、消息顺序、Context revision conflict、PlanVersion、ExecutionRound、文件移动/内容变化、soft delete/restore、磁盘不变、重启恢复和旧 Task NULL 映射。
- `backend/tests/contract/test_database.py`：3 passed，覆盖 fresh/Alembic v4、v2→v4 backup/repeatability。
- `backend/tests/integration/test_api.py backend/tests/integration/test_task_record_deletion.py backend/tests/integration/test_conversation_data_model.py`：13 passed。
- `backend/tests/integration/test_ai_only_end_to_end.py`：1 passed，现有 Planner → Classifier → review → compile → approve → execute 闭环未受影响。
- `scripts/verify.py all`：最终修复旧 v3 断言后退出 0；后端分组实际通过 `7 / 94 / 16 / 19 / 15 / 10`（安全/集成组包含本阶段测试），前端 20 passed，typecheck/build 退出 0。
- `scripts/export_runtime_contract.py`：退出 0，运行时 OpenAPI 已包含 Conversation persistence API。
- `git diff --check`：退出 0（仅保留既有换行转换提示）。

非阻塞 warning：Starlette/第三方 deprecation、Pillow decompression-bomb 边界测试预期 warning，以及 Windows pytest reparse 临时目录清理的 WinError 145；没有测试失败或用户文件操作。

## 12. 剩余风险

- 现有 `files.id` 仍是 Task 内 UUID5，跨 Task 的同一物理文件合并未在本阶段完成；ConversationFile 不会伪造跨 Task identity。
- Conversation scope 的授权快照不是最终 Agent 权限；未来工具必须重新走 SourceRegistry/privacy facade。
- ToolCall/ToolResult ledger、pending reconcile、ConversationFile 多候选重绑定和 Semantic Evidence Cache contract 延后到 Agent/缓存阶段。
- Windows pytest 清理 reparse 临时目录的既有 WinError 145 warning 仍可能出现；不影响测试退出码。

## 13. 下一阶段接入点

Chat UI 可直接使用 conversation/message/context/plans/executions/files API；AgentOrchestrator 应以 Context 为状态真相，通过现有 Scanner/Parser/Planner/Classifier/PlanCompiler/Approval/OperationJournal/Undo facade 工作。下一阶段仍需先定义 ToolCall/ToolResult 和 reference resolver，再连接真实 LLM；本阶段没有提前实现这些功能。
