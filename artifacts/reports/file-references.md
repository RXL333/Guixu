# PHASE I — File References 实现报告

日期：2026-09-21
状态：PASSED（当前 Conversation 内 V1）

## 1. 当前原始状态

PHASE H 已有 stable `files.id`、`ConversationFile.current_known_path/fingerprint/state`、PlanVersion change summary、ExecutionRound 与前端 `selectedFileIds`。但 selection 仅在前端，Message 不保存文件引用，`ConversationContext.selection_state_json` 未使用，`AffectedScopeResolver` 只按分类推导；仓库没有通用 AgentOrchestrator/Tool Registry，`docs/CONVERSATION_AGENT_V1.md` 也不存在。完整审计见 [file-reference-audit](file-reference-audit.md)。

## 2. ReferenceResolver

新增 `backend/src/guixu/application/file_references.py`。Resolver 只使用当前 Conversation 的结构化状态，确定性解析 UI selection、focus、唯一 exact filename、最近 Message reference、当前 Plan changes、最近成功 Execution 的实际 operation files 和明确 category-all；不调用 LLM、不读取文件正文、不接受模型路径作为权限。

输出包含 source、stable file IDs、count、missing、changed、scope validity、confidence、confirmation 与 reason。独立 `POST /api/v1/conversations/{id}/references/resolve` 可用于预检；Message POST 在持久化前执行同一逻辑。

## 3. Reference Priority

1. UI Selection；2. focused file；3. exact filename；4. 最近 Message reference；5. 明确 Plan changes；6. 明确 latest Execution；7. 明确 active-category-all；8. ambiguous/none。Plan/Execution 专用短语按语义直接进入对应结构化来源，selection 始终覆盖隐式来源。

## 4. UI Selection

FileWorkspace 的 click/button 多选作为 Composer selection context；支持键盘激活、单项取消、全部清空。发送成功或切换 Conversation 后清空 ephemeral selection/focus/category。500 文件测试确认一次 API 请求，Composer 只显示前三个文件和 `+N`。

## 5. Message Persistence

schema v7 / Alembic `0007_file_references` 新增 `conversation_message_file_references`，字段为 message/conversation/file 外键、source、role、path snapshot 与 created_at。它复用 `ConversationFile/files.id`，没有复制 File/Evidence。消息历史以一次批量 JOIN 加载引用，避免 N+1；历史 snapshot 不随后续选择变化。

## 6. Stable File ID

引用 identity 为现有 `files.id`。受控移动只更新当前路径，消息关系仍指向同一 ID；UI 同时获得 path snapshot/current path/state。Path 仅用于展示和 scope 校验。

## 7. Recent Message Reference

Assistant 或 User Message 可绑定文件集合。后续“这些/刚才那几个”在没有 selection/focus 时读取最近持久化集合；单数“这个”面对多文件集合返回 `REFERENCE_AMBIGUOUS`。Assistant badge 可点击并在右侧高亮同一集合。

## 8. Plan / Execution Reference

Plan reference 从当前 PlanVersion `change_summary.moves` 提取 affected IDs。Execution reference 从最新完成轮次对应 operations 中提取实际 `COMMITTED/UNDONE` IDs，不包含计划但失败的文件。Plan proposal / execution result Assistant Message 会保存结果引用。

## 9. Ambiguity Handling

无 selection/focus/唯一来源、重复 filename 或单数指向多文件时不猜。API 返回独立 error code/details；UI 保留草稿并显示“请在右侧选择后再发送”。exact filename 重名返回 `REFERENCE_DUPLICATE_FILENAME`。

## 10. Scope Protection

所有显式 ID 通过一条批量 SQL 验证属于当前 Conversation、未移出 scope，并复核当前路径仍在授权根目录。跨 Conversation ID 返回 `REFERENCE_SCOPE_VIOLATION`。文件内容/prompt injection 不参与 resolver，也不能扩大 scope。

## 11. AffectedScope / Delta Plan

`AffectedScopeResolver` 新增 `explicit_file_ids`。存在时 `scope_type=EXPLICIT`，candidate set 严格等于引用集合并关闭 category/global expansion。Post-Execution refinement 接收 trigger Message ID 与持久化引用，PlanVersion 记录 `created_by_message_id`；Delta evaluator/compiler 只处理这批候选。

## 12. Frontend Integration

- Composer：引用计数、前三项 chip、单项删除、清空。
- Message：引用 badge、缺失提示、点击联动 FileWorkspace。
- Store：selection/focus/category 生命周期；发送时与文本同一请求提交；执行后 refinement 使用已持久化 Message references。
- 响应式：修复小于 1100px 时固定文件面板覆盖 Composer/发送按钮的问题。

## 13. Migration / API

- schema：6 → 7，启动时沿用既有 SQLite 自动备份与非破坏迁移。
- migration：`backend/migrations/versions/0007_file_references.py`。
- API：Message payload 新增 selection/focus/category/context revision/reference role；refinement 新增 referenced IDs/trigger message；新增 reference resolve endpoint。
- `contracts/openapi-runtime.json` 已重新导出。

## 14. Backend Tests

最终命令：`uv --directory .\backend run pytest -q`
结果：159 passed / 2 warnings，exit 0。warnings 为既有 Starlette deprecation 与 Pillow decompression-limit 用例；Windows pytest 临时 reparse 目录清理提示不影响退出码。

专项覆盖 selection/focus/snapshot/isolation、restart 后引用恢复、recent override、exact/duplicate filename、Plan/Execution、missing/moved/scope、explicit AffectedScope、500 文件批量、真实 API 持久化与旧主链回归。File References 专项复跑：5 passed；数据库/桌面安全专项：10 passed / 1 warning，均 exit 0。

## 15. Frontend Tests / Typecheck / Build

- `npm.cmd run test -- --run`：4 files / 31 passed，exit 0。
- `npm.cmd run typecheck`：exit 0。
- `npm.cmd run build`：1727 modules transformed，exit 0。
- 覆盖 selection、500 多选、chips remove/clear、Message badge/missing、点击联动、Conversation switch isolation、发送清空和现有工作流回归。

## 16. UI Screenshots

Playwright 驱动本地 QA Conversation 完成人工检查，截图位于 `artifacts/ui/file-references/`：

- `01-multi-select.png`
- `02-reference-chips.png`
- `03-user-message-reference.png`
- `04-assistant-reference-click.png`
- `05-ambiguous-reference.png`
- `06-missing-file.png`
- `07-post-execution-reference.png`

验证了多选与 chips、持久化 user/assistant 引用、点击高亮、模糊错误、缺失状态、执行后结果引用与 1036px 窄窗口交互。QA 数据只位于隔离的 `artifacts/runtime-ui-qa`，未操作用户文件。

## 17. 安全结论

引用不会调用 FileOperationEngine、不会自动 approve/execute/undo，也没有新增删除能力。跨会话、越界路径、缺失/变化状态会在计划前阻止或交给既有 refresh 流程。OperationJournal 与 Undo schema 未变。

## 18. 当前限制

- FileWorkspace V1 提供 click/键盘多选，未实现原生 Shift 范围选择。
- active category 解析已在后端支持；当前 Conversation Workspace 尚无独立分类浏览器给它赋值。
- missing set 当前 API 返回 remaining IDs，但 UI 只提示并阻止；“继续剩余文件”快捷按钮待后续交互阶段。
- 仓库仍没有通用 AgentOrchestrator/Tool Registry；本阶段使用现有 Message + PostExecutionConversationService 接入 resolved IDs，没有提前造通用 Agent。
- 不支持跨 Conversation、长期记忆、向量搜索、Conversational Undo 或任意磁盘查找。

## 19. 下一阶段建议

下一阶段最合适的切入点是：在真正的 Agent runtime 建立只读 `ReferenceContext` adapter，把已经解析并持久化的 `ResolvedReferenceSet` 注入 turn context；任何 tool/intent 只能消费这个集合，不能生成或扩大 file IDs。随后可补 active-category UI 与 missing 部分继续确认，但不要绕过 Plan/Approval/FileOperationEngine。
