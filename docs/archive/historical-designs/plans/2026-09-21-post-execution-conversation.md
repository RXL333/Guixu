# PHASE H — Post-Execution Conversation 实施计划

## 目标与范围

在现有 Conversation、PlanVersion、ExecutionRound、PlanCompiler、FileOperationEngine 和 OperationJournal 之上，实现执行后仍保持 ACTIVE 的同会话局部整理闭环。第二轮及以后必须基于当前磁盘事实，复用有效 Evidence，只为受影响文件生成 DELTA 方案，并继续经过预览、批准和安全执行。

本阶段不实现高级文件指代、Conversational Undo、长期记忆、Watch Folder、向量检索、多 Agent 或任意磁盘工具。

## 关键依赖顺序

1. 审计现有执行完成状态、路径同步、Conversation 数据、证据复用和 UI；先产出 `artifacts/reports/post-execution-conversation-audit.md`。
2. 在 fresh schema、运行时迁移和 Alembic 中加入最小必要的 execution baseline / plan kind 数据；保持旧数据库非破坏升级。
3. 实现 WorkspaceStateService、受影响范围解析、Evidence freshness/reuse 决策、外部变化同步与 Delta Plan 校验。
4. 建立最小 post-execution refinement 编排/API：意图识别、global confirmation gate、Context revision、PlanVersion、approval、ExecutionRound 与执行后文件状态投影。
5. 集成 Conversation Workspace：执行后 Composer 保持可用，展示 affected scope、DELTA 方案、全局重整确认和当前文件刷新。
6. 添加后端/前端回归、500→20 性能边界、三轮持久化与安全测试；只有已有有效配置时运行真实 DeepSeek smoke test。
7. 更新 OpenAPI、数据模型文档、PHASE H 专项文档、阶段报告与 `PROJECT_STATUS.md`。

## 重要设计决策

- Conversation 生命周期与 ExecutionRound 分离，执行成功不关闭会话。
- `ConversationFile.file_id` 是身份；`current_known_path` 是可更新投影；历史 PlanItem/OperationJournal 路径不可改。
- AffectedScopeResolver 只允许返回已存在的 category/file ID，路径不由模型提供。
- LOCAL/PARTIAL refinement 默认 `preserve_unaffected=true`；DELTA plan 中任何越界 file_id 都会被拒绝。
- Evidence 决策为 `REUSE / REFRESH_REQUIRED / INVALID`，fingerprint 变化绝不复用旧证据。
- Global replan 必须先显式确认；确认前不生成可执行 current plan，不触碰磁盘。
- PHASE F AgentOrchestrator 在当前工作树缺失；本阶段只补满足 PHASE H 的窄编排服务，不伪造通用 Tool Calling。

## 验收与验证

- 数据层：旧库升级、baseline round、plan kind、Conversation ACTIVE、稳定 file_id、current path、历史不覆盖。
- 领域层：LOCAL/PARTIAL/GLOBAL、preserve unaffected、有效 evidence reuse、必要 refresh、missing/changed/moved external、delta stale。
- 执行层：批准前磁盘不变，批准后经过既有 FileOperationEngine/Journal，Execution #2/#3 与 PlanVersion 正确绑定。
- 性能：500 个文件、20 个候选时，只验证/评估受影响集合，Vision refresh 显著小于 500。
- 前端：继续发送、refinement loading、affected scope、DELTA 卡片、批准、第二轮记录、文件刷新、global warning、restart resume。
- 收尾：后端全量测试、前端测试、typecheck、production build、OpenAPI 导出；真实模型和人工截图如受外部配置或桌面环境阻塞，报告必须明确，不写成通过。

