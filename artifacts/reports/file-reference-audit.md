# PHASE I File Reference 现状审计

日期：2026-09-21

## 已有能力

- `conversation_files.file_id -> files.id` 已提供 Conversation 内稳定文件引用；OperationJournal 移动后更新 `files.current_path`，PHASE H 再同步 `current_known_path/fingerprint/category`。
- `ConversationContext.selection_state_json` 已预留，但当前没有可靠运行时写入方；不应把每次 checkbox 点击持久化到 Context。
- 前端 store 已有 `selectedFileIds` 和 `toggleFile`，FileWorkspace 使用整行 button 点击多选；选择仅存在内存中。
- PlanVersion `change_summary.moves[].file_id` 可给出提议影响集合；ExecutionRound 关联 core plan，可从 `operations.state='COMMITTED'` 得到实际成功影响集合。
- Message 已能引用 PlanVersion/ExecutionRound，但没有 file reference 字段或关系表；历史“这些”无法追踪。
- PHASE H `AffectedScopeResolver` 只从 taxonomy/category 名称扩展范围，尚不接受 explicit file IDs。

## 缺口与风险

1. 发送消息时前端 selection 没有提交，发送后也没有清空；切换 Conversation 虽会重新加载数据，但 selection 清理需要显式保证。
2. focused file、active category、Reference Chips、Message reference badge 和 Chat↔File 联动均不存在。
3. exact filename、recent message、latest plan/latest successful execution 的确定性解析不存在。
4. 当前 `prepare_refinement` 会按类别扩大候选集，无法保证显式 selection 的硬边界。
5. 文件缺失/变化已有 PHASE H workspace 校验，但没有 reference 专用批量结果和错误码。
6. 目标中提到的 `docs/CONVERSATION_AGENT_V1.md`、通用 AgentOrchestrator/Tool Registry 在当前工作树不存在；本阶段应接入现有 Message + PostExecutionConversationService，不能伪造通用 Agent runtime。

## Persistent / Ephemeral 决策

- Ephemeral：`selected_file_ids`、`focused_file_id`、`active_category_id` 只存在前端当前会话 store，请求时批量提交；切换会话和成功发送后清空。
- Persistent：采用规范化 `conversation_message_file_references` 表保存发送当时的 stable file IDs、source、role 和 path snapshot。它支持批量查询、FK/Conversation 归属校验和未来 Undo scope；不复制 File/Profile/Evidence，也不把动态 selection 塞进 JSON。
- Runtime `ReferenceContext` 由本轮显式 UI context、最近 Message references、当前 PlanVersion、最近成功 ExecutionRound 和 active category 合成，不持久化 hover/click 噪声。

## Baseline

- 后端 baseline：153 passed / 2 warnings。
- 前端 baseline：4 files / 28 passed。
