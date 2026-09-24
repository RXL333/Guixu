# PHASE L Conversational Undo 阶段报告

日期：2026-09-22

## 实现结果

- 原有能力：Task 级 UndoCompiler + OperationJournal + FileOperationExecutor 已支持安全 MOVE 恢复、未修改 COPY 回收、no-clobber、fingerprint、逐操作事件和 Recovery；本阶段没有重写它们。
- 新增模块：`conversational_undo.py` 提供 UndoTargetResolver、ExecutionDependencyAnalyzer、UndoPlanBuilder/validator/approval/execution facade。
- schema/migration：v10 / Alembic 0010 新增 `conversation_undo_plans`、`conversation_undo_plan_items`；ExecutionRound 新增 `round_kind`、`target_execution_round_id`、`undo_state`、reversible/undone counts。旧数据默认 FORWARD/NOT_UNDONE，旧 Task/Plan/Journal 不改写。
- Target：明确 round ID/第 N 次 > 同轮 File References > latest reversible。不存在或跨会话 round 被拒绝；查询语句不生成执行。
- Journal usage：只反转实际 `COMMITTED` MOVE/COPY，失败/跳过项不会进入 UndoPlan。路径与 SHA-256 来自 Journal/core file identity，不采用模型路径。
- Dependency：后续 completed FORWARD round 操作相同 file_id 时标记 `BLOCKED_DEPENDENCY`，禁止历史盲撤销，不做 cascade。
- Partial Undo：同一 target round 的显式 file IDs 可生成子集；原轮次记录 PARTIALLY_UNDONE 或 FULLY_UNDONE，历史保留。
- Approval：preview 与 approval/execute 分离；plan hash、basis file-state revision、scope、source hash、target collision 在批准和执行前重验；重复确认返回同一执行结果。
- External changes：missing、modified、manual move、target occupied、scope violation、already reversed 均有 item 状态和错误码。冲突计划不能确认。
- Execution：Undo 继续使用 FileOperationExecutor，产生新 core undo Plan、operations/events 和 `round_kind=UNDO` ExecutionRound。
- Session/Crash Recovery：启动将中断 undo plan/round 标为 RECOVERY_REQUIRED；重试同一 immutable plan 时按 Journal 跳过已 UNDONE 项。
- PlanVersion/Workspace：Undo 不倒退 current plan；成功后更新 ConversationFile、current ExecutionRound 和 file_state_revision，旧 active approval 按 basis revision 失效。
- Semantic Cache：move/rename 不改 fingerprint，不触发 Evidence 重算。
- Frontend：新增 UndoPreviewCard、确认/取消、blocked 提示、快捷撤销、partial/full badge 和 Change History 的 UNDO round 展示。聊天与按钮共用同一 API。
- Agent：核心撤销离线可用。仓库没有通用 Tool Registry，本阶段未伪造模型文件工具；自然语言只在用户消息入口做确定性 intent/target 解析。

## 验证

- Backend 全量：`176 passed, 2 warnings in 67.12s`。
- Conversational Undo + DB contract：`10 passed in 1.47s`。
- Real file smoke：`1 passed in 1.12s`，见 `real-conversational-undo-smoke.md`。
- Frontend：4 files / 34 passed。
- Typecheck：exit 0。
- Browser QA：Playwright CLI 在 1536×960 真实 Vite/FastAPI 页面验证 request、preview、target conflict、approved/confirming、complete、history；截图位于 `artifacts/ui/conversational-undo/`。Partial/dependency 的行为由自动化覆盖，本轮未为这两种状态额外伪造浏览器数据截图。
- Production build：exit 0；runtime OpenAPI contract 已重新导出；`git diff --check` exit 0。

## 性能

Undo preview 只读取 ExecutionRound/Journal 并对候选文件做本地存在性与 SHA-256 验证，不调用 AI。20 文件端到端 smoke（包含多轮真实移动）为 1.12s；未把该数字解释为 500 文件正式基准。500 文件仍受本地磁盘哈希吞吐影响。

## 当前限制

- Redo/Undo-of-Undo 不支持。
- 不自动递归撤销依赖轮次。
- 显式引用跨多个 ExecutionRound 时要求澄清。
- 外部移动保守阻止，不自动从新位置恢复。
- COPY Undo 依赖系统回收站可用性。
- 通用 AgentOrchestrator/Tool Registry 和正式 LLM intent router 尚未存在；不影响按钮和确定性中文撤销短语。
- 本轮保存 6 张截图，覆盖 request/preview、conflict、confirming、complete 与 history；partial/dependency 截图未生成，但组件与后端行为已自动化验证。

下一阶段建议：在正式 AgentOrchestrator 建立后，把 `resolve_undo_target/build_undo_preview/get_undo_status/request_undo` 暴露为只读/approval-gated tools；仍禁止模型获得直接文件移动工具。
