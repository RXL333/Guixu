# PHASE D — Conversation Data Model 实施计划

## 目标与边界

- 在现有 SQLite + SQLAlchemy Engine + Alembic 体系中新增 Conversation、Message、ConversationContext、PlanVersion、ExecutionRound、ConversationScope、ConversationFile 数据层。
- 复用既有 Task、TaskScope、File、FileProfile/Evidence、Taxonomy、Plan、OperationJournal/OperationEvent、ModelProfile、PrivacyConsent，不复制核心事实。
- 提供无 LLM、无 Tool Calling、无 Chat UI 的基础 repository/service/API 和持久化测试。
- Conversation 删除只做 soft delete；不级联删除磁盘文件、Task、Plan、OperationJournal 或 Undo 依赖。

## 关键决策

1. 当前没有 Declarative ORM，保持现有 repository 原生 SQL 风格；migration 与 `contracts/database.sql` 同步。
2. `files.id` 作为现有稳定业务 file_id；ConversationFile 只引用该 ID，并保存路径/指纹观察值。移动时核心 `files.id` 不变，路径只是 projection。
3. 当前没有独立 Execution 表；ExecutionRound 通过 `execution_plan_id`/`undo_plan_id` 引用既有 `plans`，执行事件继续由 `operations` 与 `operation_events` 保留。
4. ConversationContext 一对一保存结构化 current state，`context_revision` 用 compare-and-swap 保护；Message append-only，不作为状态真相。
5. PlanVersion append-only，保存 parent、basis context revision、既有 plan/taxonomy 引用及必要快照；旧版本不更新覆盖。
6. ToolCall/ToolResult 暂不建表，报告中明确 deferred 到 Agent Orchestrator 阶段，避免在没有调用语义时过早冻结契约。

## 顺序与影响范围

1. 先完成 `artifacts/reports/conversation-schema-audit.md`，记录现状、复用表、差距与 ER 设计。
2. 更新 v4 contract schema 与 `0004_conversation_data_model.py`，并扩展运行时 v3→v4 非破坏迁移及 SQLite backup。
3. 新增 `conversation_repository.py` 与 `application/conversations.py`，实现 CRUD、revision conflict、append-only 版本/轮次、稳定文件引用与验证。
4. 在 `app.py` 注册基础 Conversation API；在 `schemas.py` 增加输入契约。不得调用模型或启动 Agent。
5. 新增后端集成/迁移测试，覆盖重启、旧 Task、软删除、磁盘不变、文件移动/内容变化、计划版本和执行轮次关系。
6. 运行 Conversation 定向测试、数据库/安全回归和现有 AI-only 闭环；修复具体回归后再运行全量验证。
7. 生成 `docs/CONVERSATION_DATA_MODEL.md`、`artifacts/reports/conversation-data-model.md`，更新 `PROJECT_STATUS.md` 并在 PHASE D 后停止。

## 验收

- 新 schema 可从空库初始化，也可从 v3 旧库备份并升级到 v4。
- API 与 repository 支持会话/消息/context/plan version/execution round/file reference 基础操作。
- context expected revision 不匹配返回 `CONTEXT_REVISION_CONFLICT`。
- 已执行 plan 的安全日志不会因 Conversation soft delete 消失；磁盘 hash/path 不变。
- 旧 Task 无 conversation_id 时仍可读；新数据可以显式建立 Task 映射。
- `scripts/verify.py all`、AI-only 闭环、typecheck/build（本阶段不改前端，至少运行后端回归）结果如实记录。
