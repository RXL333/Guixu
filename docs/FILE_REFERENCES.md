# Guixu File References

版本：PHASE I，2026-09-21
范围：当前 Conversation 内的稳定文件引用、选择上下文与确定性解析；不包含跨会话检索、长期记忆或 Conversational Undo。

## 1. 为什么需要 File Reference

“这个”“这些”“刚才那几个”只有在绑定到明确文件集合后才能成为安全的整理输入。Guixu 不把自然语言或当前路径直接当权限依据，而是先由 `ReferenceResolver` 解析为当前 Conversation 内的 stable `file_id`，再把该集合交给后续方案生成。引用本身不会移动、复制或删除文件。

## 2. Stable File Identity

文件引用复用现有 `files.id` 与 `conversation_files.file_id`，不创建第二套 File 实体。`ConversationFile` 保存当前已知路径、fingerprint 和状态；`files.id` 在受控移动后不变。因此路径改变不会使历史消息失去目标，内容变化则通过现有 fingerprint/state 同步机制被发现。

## 3. Explicit vs Implicit References

- 显式引用：本轮 UI selection、focused file、唯一 exact filename。它们是硬约束。
- 隐式引用：最近消息集合、当前 PlanVersion 改动集合、最近成功 ExecutionRound 的实际操作集合、语言明确指定的当前分类全量。
- 无法唯一解释时返回结构化错误，不把整个目录当成“这些”。

## 4. Reference Resolution Priority

确定性优先级为：

1. 本轮 UI selection；
2. 本轮 focused file；
3. 当前 Conversation 中唯一 exact filename；
4. 对“这些/刚才那几个”的最近持久化 Message reference；
5. 语言明确要求“刚才改动”时的当前 PlanVersion affected files；
6. 语言明确要求“上一次移动”时的最近已完成 ExecutionRound 实际 affected files；
7. 明确说“当前类别里的所有文件”时的 active category；
8. `REFERENCE_AMBIGUOUS` 或 `NONE`。

计划/执行短语是显式语义，因此不会被不相关的最近消息集合抢占；UI selection 始终最高优先级。

## 5. UI Selection

`FileWorkspace` 通过点击/键盘激活支持可靠多选，store 保存 `selectedFileIds` 与 `focusedFileId`。Composer 展示最多三个文件名和合并计数，支持移除单项与清空。发送成功后清空临时选择；切换 Conversation 时也清空，避免跨会话串用。选择 500 个文件仍只发送一次批量请求。

## 6. Message Snapshot

消息发送时，实际引用写入 `conversation_message_file_references`：

```text
ConversationMessage
  └── MessageFileReference *
        ├── conversation_id
        ├── file_id ──> files.id / ConversationFile
        ├── reference_source
        ├── reference_role
        └── path_snapshot
```

历史消息读取当前路径与当前状态，同时保留发送时的 `path_snapshot`。后续 selection 改变不会修改旧消息。该关系表支持按消息/文件查询，并避免在 Message JSON 中复制文件资料、fingerprint 或 evidence。

## 7. ReferenceContext

第一版把 ReferenceContext 作为运行时聚合而非数据库大 JSON：本轮 selection/focus/category 是 ephemeral；最近消息引用、PlanVersion、ExecutionRound 与 ConversationFile 状态由持久化实体实时合成。已有 `ConversationContext.selection_state_json` 保留兼容，但本阶段不把每次 UI 点击写入数据库，也不持久化 hover。

## 8. ReferenceResolver

`ReferenceResolver.resolve()` 输入用户文本、selection、focus、active category 和 Conversation ID，输出：

```json
{
  "source": "UI_SELECTION",
  "file_ids": ["..."],
  "count": 1,
  "missing": [],
  "changed": [],
  "scope_valid": true,
  "confidence": 1.0,
  "requires_confirmation": false
}
```

解析、批量成员校验、exact filename、最近消息/方案/执行查询均由后端确定性代码完成，不让模型生成 file ID 或原始路径。

## 9. Conversation Isolation

每个候选 ID 必须同时存在于当前 `conversation_files` 且未移出 scope。另一个 Conversation 的 ID 返回 `REFERENCE_SCOPE_VIOLATION`。前端切换会话立即清空 selection/focus/category，后端仍是最终安全边界。

## 10. Missing / Changed Files

引用行保留 file ID，即使文件后来缺失。读取历史时 UI 显示“含不可见文件”；新一轮解析若包含 `MISSING` 返回 `REFERENCE_FILE_MISSING`，包含 `FILE_CHANGED` 返回 `REFERENCE_FILE_CHANGED`。生成 Plan 前，Post-Execution workspace 同步会复核 exists/current path/fingerprint，并按现有 Evidence refresh 策略处理内容变化。

## 11. Path vs Identity

路径只用于展示、授权范围验证和历史 snapshot，不承担 identity。系统内移动更新 `ConversationFile.current_known_path`，Message reference 仍指向同一个 `file_id`。任何模型输出的 path 都不能成为授权或最终引用。

## 12. Agent Integration

当前项目没有通用 Tool Registry/AgentOrchestrator；因此 PHASE I 把 `ResolvedReferenceSet` 直接交给现有消息与 Post-Execution refinement 边界，没有伪造新的 agent runtime。下一阶段接入 Agent 时，应把该集合放进只读 runtime context，并禁止模型扩大 explicit file set。

## 13. AffectedScope Integration

`AffectedScopeResolver.resolve(explicit_file_ids=...)` 优先验证并返回 `scope_type=EXPLICIT`。显式集合存在时关闭 category expansion/global expansion，候选文件严格等于引用集合。

## 14. Plan Integration

Refinement 创建的 `PlanVersion.created_by_message_id` 指向触发消息；其 Plan/`change_summary.moves` 继续保存真实 affected files，避免重复大 JSON。由方案产生的 Assistant `PLAN_PROPOSAL` Message 可绑定结果文件集合。

## 15. Execution Integration

“上一次移动的文件”只读取最近完成 ExecutionRound 对应 operations 中 `COMMITTED`/`UNDONE` 的实际 file IDs，不使用仅计划但失败的条目。执行结果 Message 以 `LATEST_EXECUTION_AFFECTED` 保存可点击引用。

## 16. Security

- 引用不等于批准或执行；仍须 Agent analysis、Plan、Preview、Approval 和 FileOperationEngine。
- resolver 只查询当前 Conversation，不遍历磁盘、不读取文件正文。
- 文件内容中的 prompt injection 不参与引用解析。
- Message persistence 在同一事务内批量验证 membership；删除/移动能力没有因本阶段扩展。

## 17. Error Handling

支持 `REFERENCE_NOT_FOUND`、`REFERENCE_AMBIGUOUS`、`REFERENCE_SCOPE_VIOLATION`、`REFERENCE_FILE_MISSING`、`REFERENCE_FILE_CHANGED`、`REFERENCE_SET_EMPTY`、`REFERENCE_STALE`、`REFERENCE_CATEGORY_NOT_FOUND`、`REFERENCE_DUPLICATE_FILENAME`。API 返回可区分 code 与 details；UI 显示明确提示并保留草稿/选择供用户修正。

## 18. Performance

选择验证、Message reference 写入和消息历史读取都是批量 SQL；历史消息引用以一次批量 JOIN 加载，避免逐消息 N+1。Composer 只预览前三项，500 文件场景不会生成 500 个 chip 或 500 次 API 请求。大量引用仍必须进入 Plan preview 和 Approval。

## 19. Future Conversational Undo Integration

未来“撤销刚才这几个”可由 Message reference、PlanVersion affected set 与 ExecutionRound actual affected set确定 scope，再交给独立的 Conversational Undo 策略校验。PHASE I 只保存可追踪关系，不执行 Undo，也不修改现有 journal/undo 安全边界。
