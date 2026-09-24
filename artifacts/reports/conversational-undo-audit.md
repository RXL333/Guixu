# PHASE L Conversational Undo 审计

日期：2026-09-21

## 结论

当前项目已有安全、真实的 Task 级 Undo 内核，但没有 Conversation 级撤销产品能力。正确方案是复用 core `plans`、`operations`、`operation_events`、`UndoCompiler`、`FileOperationExecutor` 和 `RecoveryService`，在其上增加持久化 UndoPlan、会话目标解析、依赖分析、批准边界与 UI；不建立第二套文件移动引擎。

## 现有能力

1. `UndoCompiler` 从 forward plan 与 `completed_operation_ids()` 构建逆向 plan；MOVE 反转 source/target，COPY 使用 `recycle_copy`。
2. `SqliteOperationJournal` 持久化真实 operation、状态转换、错误码、approval 和逐步 event；成功/失败/跳过可区分。
3. `FileOperationExecutor` 在执行前验证 plan hash、approval、source identity/fingerprint，并使用 no-clobber；Undo 冲突写 `UNDO_CONFLICT`。
4. Move/Rename Undo 可以真实恢复；目标存在时拒绝覆盖；重复执行已 `UNDONE` operation 会跳过。
5. Copy Undo 只通过系统回收站删除未改变的副本；内容变化时拒绝。没有直接 `os.remove()` 的产品路径。
6. `RecoveryService` 可依据 source/target/temp 与 Journal 状态恢复未完成 forward/undo operation。
7. Conversation 已有 `ExecutionRound.undo_status`，但状态只有 `NOT_REQUESTED/AVAILABLE/PREPARED/EXECUTED/BLOCKED`，不足以表达 partial/full undo；ExecutionRound 也缺少 round kind 和 target round relation。

## 逐项回答

1. 当前 Undo 可以真正恢复 MOVE；COPY 只在副本未变化时送入回收站。
2. 编译入口接收 forward Plan，但可撤销集合来自 OperationJournal 的实际完成 operation；Conversation 层仍需强制 Journal 为事实源。
3. Journal 保存实际 source/target、expected SHA-256、状态和事件，文件表在成功 move 后更新 current path。
4. `FAILED/CONFLICT/SKIPPED/COMMITTED` 均有独立状态。
5. 部分执行可以由 operation 状态精确识别，Undo 只应选 `COMMITTED`。
6. Undo 不覆盖目标文件；目标出现会进入 `UNDO_CONFLICT`。
7. UndoCompiler 读取当前位置 identity，执行器再次比较 identity/SHA-256。
8. 外部修改导致 source identity 不匹配并拒绝；Conversation preview 尚不能提前给出细分提示。
9. ExecutionRound 目前只映射 forward PlanVersion/Execution，没有 Undo round kind/target relation。
10. 已有粗粒度 `undo_status`，缺少 `PARTIALLY_UNDONE/FULLY_UNDONE/NOT_REVERSIBLE`。
11. crash recovery 与 Undo 共用 OperationJournal、FileOperationExecutor 状态机和 RecoveryService。
12. MOVE/rename 作为 move 反向移动；COPY 仅安全回收任务创建的未修改副本；REPORT_ONLY 没有 operation，应为 NOT_APPLICABLE。

## 缺口

- 无 Conversation 内 latest/specific/referenced-files target resolver。
- 无 later ExecutionRound 同 file_id dependency analyzer。
- 无持久化 UndoPlan/UndoPlanItem、basis file-state revision、preview item status 与 approval hash。
- 无部分撤销与 remaining reversible file 统计。
- 无 Conversation 级 approval/execute/recovery API。
- 无 UndoPreviewCard、历史 badge、快捷撤销入口。
- 当前通用 AgentOrchestrator/Tool Registry 仍不存在；本阶段应提供确定性 backend facade，不能伪造一个模型工具循环。

## 兼容与安全决定

- 新增 schema，不删除或改写旧 Plan/Execution/Journal。
- Undo core plan 仍写既有 `plans/operations/operation_events`。
- 对话文本只参与意图与轮次定位；所有 file ID/path 来自当前 Conversation、ExecutionRound 和 Journal。
- 历史轮次存在后续同 file_id 操作时保守阻止，不实现 cascading undo。
- Plan Restore 与 Undo 保持两条独立路径。
