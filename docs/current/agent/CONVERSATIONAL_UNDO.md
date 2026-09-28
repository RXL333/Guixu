# Conversational Undo / 对话式撤销

版本：PHASE L，2026-09-22

## 1. 定义与边界

Conversational Undo 是对已经真实改变磁盘的 Conversation ExecutionRound 执行确定性逆向文件操作。它不是删除消息、删除执行历史，也不是把 `current_plan_version_id` 指回旧方案。Plan Restore 只产生新的方案版本；Undo 会产生新的 core undo plan、OperationJournal 和 `round_kind=UNDO` 的 ExecutionRound。

V1 支持最近一次可逆执行、明确轮次和同一执行内的显式文件集合。它不支持 Redo、级联撤销、跨 Conversation 撤销或任意时间点快照恢复。

## 2. 事实源与目标解析

`UndoTargetResolver` 只接受当前 Conversation 的持久 ExecutionRound：明确 round ID/“第 N 次”优先，其次是本轮 stable file references，最后是最近一个 `COMPLETED + FORWARD + 有 COMMITTED operation + 未 FULLY_UNDONE` 的轮次。文件内容、Evidence 或模型输出不能触发 Undo；自然语言只作为用户消息解析 target，不产生路径。

“可以撤销吗”属于查询，只返回可逆性说明，不生成执行确认。REPORT_ONLY 或没有实际成功 operation 的轮次返回 `UNDO_NOT_APPLICABLE`。

## 3. UndoPlan 与 UndoPlanItem

schema v10 新增：

```text
Conversation
├── ExecutionRound FORWARD
│     └── core Plan -> actual COMMITTED operations
└── UndoPlan
      ├── immutable plan_hash
      ├── basis_file_state_revision
      ├── target_execution_round_id
      └── UndoPlanItem *
            ├── stable file_id
            ├── original_operation_id
            ├── current_source / restore_target
            ├── expected_fingerprint
            └── READY / BLOCKED_* / ALREADY_REVERSED

UndoPlan approved/executed
└── ExecutionRound UNDO
      └── core undo Plan -> operations -> operation_events
```

UndoPlan 只从原轮次 core plan 中状态为 `COMMITTED` 的 MOVE/COPY operation 构建。planned/failed/skipped operation 不进入撤销。Plan 创建后不可编辑；任何磁盘状态变化都通过新 preview 或 `STALE` 处理。

## 4. Preview、Approval 与执行

用户消息或历史按钮都调用同一个 `/undo-plans` backend。请求最多生成 `WAITING_FOR_APPROVAL` preview；即使文字中说“直接执行”，也不能绕过 UI confirmation。

批准时复核 plan hash、`basis_file_state_revision`、source path、SHA-256、target no-clobber 和 item 状态。执行前再次做同样检查，并阻止同一 Conversation 中仍在 QUEUED/RUNNING 的 AgentTurn。批准和执行是两个独立 API；重复执行已完成计划只返回已有结果。

## 5. 文件验证与冲突

- source 不存在：`UNDO_SOURCE_MISSING`；
- source 内容变化：`UNDO_SOURCE_MODIFIED`；
- stable file 当前路径不是 Journal 预期 source：`FILE_MOVED_EXTERNALLY`；
- 原位置已被占用：`UNDO_TARGET_CONFLICT`；
- source/target 不同时位于 active authorized scope：`UNDO_SCOPE_VIOLATION`；
- 文件已由用户恢复且 fingerprint 一致：`ALREADY_REVERSED`，不重复移动；
- 目录缺失由现有 FileOperationExecutor 的已审计目录创建能力处理并写 created directory journal。

Undo 不改名避让、不覆盖、不猜测外部位置。MOVE/rename 反向移动；COPY 仅复用现有 `send2trash` 安全回收未变化副本，绝不直接永久删除。

## 6. 历史依赖与 Partial Undo

`ExecutionDependencyAnalyzer` 查找目标轮次之后所有 completed FORWARD round 的实际 `COMMITTED` operation。后续轮次再次操作同一个 stable file ID 时，该 item 为 `BLOCKED_DEPENDENCY`，V1 阻止整个 preview 执行，不自动 cascading undo。

显式 MessageFileReference/UI selection 可将计划限定为同一 ExecutionRound 的子集。若引用集合来自不同轮次，返回 `UNDO_REFERENCE_AMBIGUOUS`。部分成功后原轮次为 `PARTIALLY_UNDONE` 并保存 `undone_file_count / reversible_file_count`；全部恢复后为 `FULLY_UNDONE`。原 ExecutionRound 永远保留。

## 7. Workspace、PlanVersion 与 Semantic Cache

成功 Undo 更新 core `files.current_path`、ConversationFile projection、`current_execution_round_id`，并令 `file_state_revision + 1`。它不倒退 PlanVersion 指针、不删除 taxonomy。所有旧 active plan approval 若基于更旧 file-state revision 会标记 STALE，后续必须重新校验。

普通 move/rename 不改变 fingerprint，因此 `file_evidence` 继续 VALID，不重新调用 Vision/OCR/Planner/Classifier。只有 validation 发现内容变化时，Undo 被阻止并沿用 Semantic Cache 的 content-change 策略。

## 8. Session/Crash Recovery

WAITING_FOR_APPROVAL 的 UndoPlan 重启后仍可查看，但批准时必须重新验证 revision 和磁盘。`EXECUTING` 期间退出时，SessionRecovery 将相关 round 和 UndoPlan 标为 `RECOVERY_REQUIRED`。再次执行同一计划时，FileOperationExecutor 根据 Journal 跳过已 `UNDONE` operation，只处理未完成项；不会重新执行全部。

## 9. UI 与 API

UndoPreviewCard 展示目标轮次、可恢复/冲突/已恢复数量、逐文件路径和普通用户可读原因。确认、取消、blocked、partial/full badges 与 Change History 共用持久状态。

主要 API：

- `GET /conversations/{id}/reversible-executions`
- `GET/POST /conversations/{id}/undo-plans`
- `GET /conversations/{id}/undo-plans/{undo_plan_id}`
- `POST .../{undo_plan_id}/approve`
- `POST .../{undo_plan_id}/execute`
- `POST .../{undo_plan_id}/cancel`

核心撤销可离线运行，不依赖 DeepSeek/Qwen。当前仓库没有通用 Agent Tool Registry；因此 V1 使用受限 API facade，不伪造 `reverse_move_file` 等模型工具。

## 10. 安全、错误与当前限制

关键错误包括 `UNDO_TARGET_NOT_FOUND`、`UNDO_NOT_APPLICABLE`、`UNDO_REFERENCE_AMBIGUOUS`、`UNDO_DEPENDENCY_CONFLICT`、`UNDO_SOURCE_MISSING`、`UNDO_SOURCE_MODIFIED`、`UNDO_TARGET_CONFLICT`、`UNDO_SCOPE_VIOLATION`、`UNDO_PLAN_STALE`、`UNDO_PLAN_HASH_MISMATCH`、`UNDO_APPROVAL_REQUIRED`、`UNDO_EXECUTION_INTERRUPTED` 和 `UNDO_RECOVERY_REQUIRED`。

当前限制：不做 Redo；不跨多个 ExecutionRound 合并 partial undo；历史依赖不级联；外部移动即使 stable identity 可定位也保守阻止；COPY Undo 依赖系统回收站；通用 AgentOrchestrator/Tool Registry 仍未建立。

## 11. 测试

自动化覆盖 latest/specific target、Journal-only、approval boundary、partial/full state、dependency、modified/missing/external move/target conflict、stable ID、idempotency、restart ledger 和现有 safety regression。20 文件真实临时目录 smoke 覆盖 Round 1、局部 Round 2、5 文件 Undo、其余文件不变以及 Undo 后继续 Round 4。

