# PHASE L Conversational Undo 实施计划

## 目标与边界

在现有 `OperationJournal`、`UndoCompiler`、`FileOperationExecutor` 和 Conversation 数据模型之上，建立可持久化、可预览、需明确批准、可恢复的对话式撤销。逆向路径只能来自实际成功的 Journal operation；自然语言只定位 ExecutionRound，不能直接执行文件操作。

不实现 Redo、级联撤销、跨 Conversation 撤销、系统快照或新的文件执行器。

## 依赖顺序

1. 审计现有 Undo、Journal、Recovery、ExecutionRound 和前端历史展示，形成 `artifacts/reports/conversational-undo-audit.md`。
2. schema v10：持久化 UndoPlan/UndoPlanItem；为 ExecutionRound 补充 forward/undo 语义、目标轮次和细粒度 undo state；保持旧 Task、Plan、Journal、Undo 数据兼容。
3. 实现 `UndoTargetResolver`、`ExecutionDependencyAnalyzer` 和 `ConversationalUndoService`：从成功 Journal operation 构建不可变 preview，校验 stable file ID、scope、fingerprint、外部移动、目标冲突与后续依赖。
4. 实现批准、执行、部分撤销和幂等；执行继续使用现有 FileOperationExecutor，并把 Undo 作为新 ExecutionRound/Journal 历史保存。成功后更新 ConversationFile、file_state_revision 和旧未执行方案的 revalidation 基线。
5. 接入 Session Recovery：等待批准的计划重启后重新校验；运行中 Undo 依赖逐 operation Journal 继续，绝不重放已完成项。
6. 提供 Conversation Undo API；对用户消息只做确定性 undo intent/round 定位，不调用模型。按钮和聊天共享同一服务。
7. 前端增加 UndoPreviewCard、确认/取消、冲突提示、历史 undo badge 和快捷撤销。
8. 添加后端/前端回归、临时真实文件 smoke、性能记录；更新 runtime contract、文档、阶段报告和 `PROJECT_STATUS.md`。

## 重点验收

- “撤销刚才那次”定位当前 Conversation 最近一次已完成且未完全撤销的真实执行。
- preview/approval 前磁盘不变；批准时再次验证 plan hash、file_state_revision、scope、source fingerprint 和 target no-clobber。
- 只反转实际 `COMMITTED` operation；后续同 file_id 执行会阻断历史撤销；显式文件集合支持 partial undo。
- 外部移动、修改、缺失、原路径占用、already reversed 均有明确状态，不猜路径、不覆盖。
- Undo 产生新的 core plan、operation journal 和 Conversation ExecutionRound，原历史不删除；重复确认只执行一次。
- Move/Rename Undo 不使内容未变的 Semantic Cache 失效；成功后 `file_state_revision + 1`。
- crash/restart 可从 Journal 识别已完成与待恢复操作。
- 后端、前端测试、typecheck、production build、真实临时目录 smoke 通过；若桌面截图受环境阻塞，报告准确记录，不伪造通过。

