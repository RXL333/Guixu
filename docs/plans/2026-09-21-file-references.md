# PHASE I File References 实施计划

## 目标与范围

在当前 Conversation 内把 UI selection、focus、最近 Message、当前 Plan、最近成功 Execution 与 exact filename 确定性解析为 stable file IDs；保存不可变 Message reference snapshot，并让 Post-execution affected scope/DELTA 严格服从显式引用。不会新增危险操作、跨会话搜索、Undo、Memory、Vector DB 或 Watch Folder。

## 依赖顺序

1. 审计并冻结 persistent/ephemeral 模型。
2. schema v7 + migration：`conversation_message_file_references`，批量 FK 关系和索引。
3. Repository/ReferenceResolver：归属、scope、missing/changed、exact name、recent message、plan/execution actual results和确定性优先级。
4. Message/resolve API：批量提交 UI context，保存 resolved snapshot，返回结构化 ambiguity/error。
5. PHASE H 集成：explicit IDs 优先并限制 evaluator/DELTA candidate set；PlanVersion 绑定 trigger message。
6. 前端 store/components：多选/focus、chips、清空/移除、发送后与切会话清理、badge 点击高亮、large-count summary、ambiguous/missing state。
7. 后端/前端回归、typecheck/build、可行的隔离 UI 验收。
8. `docs/FILE_REFERENCES.md`、阶段报告和 PROJECT_STATUS。

## 关键验收

- selection > focus > exact filename > recent message > latest plan > latest successful execution > explicit category-all；无法唯一确定时不猜。
- selected IDs 必须属于当前 Conversation 和授权 scope；批量验证，不逐文件发 API。
- Message snapshot 不随后续 selection/path 改变；移动后 stable ID 仍定位当前 path，missing/changed 明确返回。
- explicit set 是 affected scope 上限；模型输出和 DELTA operations 都不能扩大。
- frontend tests、backend tests、typecheck、production build 通过；不把未运行的人工项写成通过。
