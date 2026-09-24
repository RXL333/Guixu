# Phase F 首次分析闭环审计

审计依据：当前工作区源码、`contracts/database.sql`、Conversation 数据模型实现、AI-only 任务链和前端会话页面。

## 当前状态

| 环节 | 状态 | 证据 / 结论 |
| --- | --- | --- |
| Conversation creation | IMPLEMENTED | `POST /api/v1/conversations` 强制 `scope_grant`，持久化 scope、Context 和可选 model profile。 |
| Folder scope binding | IMPLEMENTED | `SourceRegistry` + `conversation_scopes` 已存在；首次分析需要复用创建会话时的授权引用。 |
| Message persistence | IMPLEMENTED | `POST /conversations/{id}/messages` 只保存用户消息和文件引用。 |
| First-turn endpoint | MISSING | 没有 `/conversations/{id}/turns`，前端发送后只显示“首次整理分析能力尚未接入”。 |
| Agent Orchestrator | MISSING（本阶段最小替代） | 后续 Agent 运行时尚未建立；本阶段只增加受限的首次分析编排服务，不引入通用 Tool Calling。 |
| Intent routing | MISSING | 首次消息未区分 `ORGANIZE_REQUEST` 与后续 refinement。 |
| Scanner | IMPLEMENTED | `TaskService.start()` 使用受授权目录执行真实 Scanner。 |
| Parser / FileProfile | IMPLEMENTED | `ParsingService` 生成并缓存 `FileProfile` 与 Evidence。 |
| Semantic Cache | IMPLEMENTED | `EvidenceCacheService` 在 Parser、Planner、Classifier 链路中复用有效 Evidence。 |
| DeepSeek / Qwen model adapter | IMPLEMENTED | `ModelGateway` 已提供文本、JSON 和视觉调用；能力检查会阻止未验证或不支持的模型。 |
| AI taxonomy planner | IMPLEMENTED | `AITaxonomyPlanner.plan_task()` 使用真实 Profile/Evidence 调用 ModelGateway。 |
| AI file classifier | IMPLEMENTED | `AIFileClassifier.classify_taxonomy()` 使用真实 Profile/Evidence，低置信度保留为 review/keep。 |
| Plan Compiler | IMPLEMENTED | `OperationService.compile()` 只持久化计划和 operation journal，不移动文件。 |
| PlanVersion v1 mapping | PARTIAL | `PlanVersionService` 已存在，但没有首次分析结果写入 Conversation PlanVersion 的入口。 |
| PlanPreviewCard | IMPLEMENTED | 前端已有真实 PlanVersion 渲染组件，但首次分析永远不会产生数据。 |
| Progress / Event mechanism | PARTIAL | Task events 已持久化；首次会话没有阶段状态返回或系统事件。 |

## 阻断原因

前端 `appendMessage()` 在没有历史 ExecutionRound 时直接设置占位提示；后端 Message API 按设计只保存消息，不调用 Planner、Classifier 或模型。因此模型配置成功也不会触发首次分析。

## 本阶段实现边界

复用既有 Task、Scanner、Parser、Evidence Cache、Planner、Classifier、Plan Compiler、Operation Journal 和 PlanVersion 表。新增仅限于一个受限的 First Organization Analysis service、turn API、前端发送适配和回归测试；不实现通用 Agent Orchestrator、Tool Calling、Incremental Replanning 或文件执行。
