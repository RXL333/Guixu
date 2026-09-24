# Phase F 首次分析闭环审计

审计依据：当前工作区源码、`contracts/database.sql`、Conversation 数据模型实现、AI-only 任务链和前端会话页面。

## 当前状态

本文件记录的是实现后的复核结果；“阻断原因”一节保留修改前的根因，便于追溯。

| 环节 | 状态 | 证据 / 结论 |
| --- | --- | --- |
| Conversation creation | IMPLEMENTED | `POST /api/v1/conversations` 强制 `scope_grant`，持久化 scope、Context 和可选 model profile。 |
| Folder scope binding | IMPLEMENTED | `SourceRegistry` + `conversation_scopes` 已存在；首次分析需要复用创建会话时的授权引用。 |
| Message persistence | IMPLEMENTED | `POST /conversations/{id}/messages` 只保存用户消息和文件引用。 |
| First-turn endpoint | IMPLEMENTED | `POST /api/v1/conversations/{id}/turns` 保存 USER 消息并启动受限首次分析服务。 |
| Agent Orchestrator | MISSING（本阶段最小替代） | 后续 Agent 运行时尚未建立；本阶段只增加受限的首次分析编排服务，不引入通用 Tool Calling。 |
| Intent routing | IMPLEMENTED | 无方案/执行指针时进入首次 `ORGANIZE_REQUEST`；已有方案或执行记录继续走后续 refinement。首次消息中的“这些文件”默认指向已授权 scope，显式文件引用仍经 resolver 校验。 |
| Scanner | IMPLEMENTED | `TaskService.start()` 使用受授权目录执行真实 Scanner。 |
| Parser / FileProfile | IMPLEMENTED | `ParsingService` 生成并缓存 `FileProfile` 与 Evidence。 |
| Semantic Cache | IMPLEMENTED | `EvidenceCacheService` 在 Parser、Planner、Classifier 链路中复用有效 Evidence。 |
| DeepSeek / Qwen model adapter | IMPLEMENTED | `ModelGateway` 已提供文本、JSON 和视觉调用；能力检查会阻止未验证或不支持的模型。 |
| AI taxonomy planner | IMPLEMENTED | `AITaxonomyPlanner.plan_task()` 使用真实 Profile/Evidence 调用 ModelGateway。 |
| AI file classifier | IMPLEMENTED | `AIFileClassifier.classify_taxonomy()` 使用真实 Profile/Evidence，低置信度保留为 review/keep。 |
| Plan Compiler | IMPLEMENTED | `OperationService.compile()` 只持久化计划和 operation journal，不移动文件。 |
| PlanVersion v1 mapping | IMPLEMENTED | 首次链路写入唯一 `FULL / PROPOSED` v1，带 `plan_id`、`plan_hash`、basis revision，baseline execution 为空。 |
| PlanPreviewCard | IMPLEMENTED | 首次分析返回真实 PlanVersion 和 metrics，前端现有卡片渲染预览。 |
| Progress / Event mechanism | IMPLEMENTED | API 返回 scan/evidence/taxonomy/classification/preview/complete 阶段；Task events 同步持久化。 |

## 阻断原因

修改前的根因是：前端 `appendMessage()` 在没有历史 ExecutionRound 时只设置占位提示；后端 Message API 按设计只保存消息，不调用 Planner、Classifier 或模型。因此模型配置成功也不会触发首次分析。本阶段已由 bounded First Organization Analysis service + turn API 修复。

## 本阶段实现边界

复用既有 Task、Scanner、Parser、Evidence Cache、Planner、Classifier、Plan Compiler、Operation Journal 和 PlanVersion 表。新增仅限于一个受限的 First Organization Analysis service、turn API、前端发送适配和回归测试；不实现通用 Agent Orchestrator、Tool Calling、Incremental Replanning 或文件执行。

## 真实链路复核

在隔离数据库 `artifacts/test-workspaces/phase-f-real-deepseek-20260924-120906/data/app.sqlite3` 和 5 个合成图片文件上使用已启用的 DeepSeek profile（只读取 Windows Credential Manager 中的 secret，不在报告输出）。最终成功任务为 `cae45fbb-b4d0-4ae3-b200-284633dc103b`：

- Planner 与 classifier 均产生 `model_calls`，数据库用途分别记录为兼容枚举 `planning` / `classification`。
- 5 条 `CLOUD_MODEL / VISUAL_DESCRIPTION` evidence 已持久化，说明图片走了受控视觉输入；没有本地语义分类回退。
- 生成 4 个 AI 类别、5 个受影响文件、0 个需保留文件，唯一 PlanVersion 为 v1 `FULL / PROPOSED`，无 ExecutionRound、无 baseline execution。
- 真实源文件 SHA-256、路径和数量在请求前后保持不变；任务只生成预览。
- 全链路返回 `200`，端到端耗时约 33 秒（扫描/本地解析占主要时间，模型调用延迟写入 `model_calls.latency_ms`）。
