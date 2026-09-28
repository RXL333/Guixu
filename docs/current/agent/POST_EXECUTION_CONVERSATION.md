# Post-Execution Conversation（PHASE H）

## 1. 目标与边界

一次文件执行完成后，Conversation 继续保持 `ACTIVE`。用户可以在同一会话提出第二轮、第三轮局部调整；每轮都重新读取当前磁盘投影、限定受影响集合、优先复用 FileProfile evidence、生成新的 PlanVersion，并继续经过 Preview → Approval → Execute。模型只判断给定 file ID 是否匹配要求以及受限 category ID，不能返回路径或执行文件操作。

本阶段不实现高级指代、框选引用、Conversational Undo、跨会话记忆、Watch Folder、多 Agent、Shell/Python Tool 或无确认移动。

## 2. 执行后的工作区状态

`WorkspaceStateService` 汇总 Conversation/Context、授权 scope、最近已完成 ExecutionRound、当前和最近已执行 PlanVersion、taxonomy、confirmed requirements 以及 ConversationFile/Core File/FileProfile 的投影。`files.id` 是稳定引用；`current_known_path` 是可变位置，不覆盖旧 Plan/Operation 中的历史路径。

执行成功时 `complete_execution_round`：

- 将 ExecutionRound 标记为 `COMPLETED`，对应 PlanVersion 标记为 `EXECUTED`；
- 从 OperationJournal 已更新的 `files.current_path` 同步 ConversationFile；
- 更新当前分类、fingerprint、Context current pointers 和 file revision；
- 保持 Conversation 为 `ACTIVE`，保留全部旧版本、执行和 journal。

## 3. 受影响范围

`AffectedScopeResolver` 只从当前 taxonomy 的受控 category ID/name 与 ConversationFile membership 解析范围：

- `LOCAL`：一个来源类别；
- `PARTIAL`：多个明确来源类别；
- `GLOBAL`：显式“全部/整个/重新规划”等语义，必须二次确认。

局部请求仅把候选 file IDs 交给模型；“其他不要动”会设置 `preserve_unaffected`。模型不能扩大集合、创造 file ID/category ID 或提供路径。含糊、空范围或非法返回分别拒绝为 `REFINEMENT_AMBIGUOUS`、`AFFECTED_SCOPE_EMPTY/INVALID`、`TOOL_VALIDATION_FAILED`。

## 4. Evidence 复用与刷新

Evidence 判断为 `REUSE`、`REFRESH_REQUIRED` 或 `INVALID`。fingerprint 未变且已有 extracted text/OCR/视觉描述/转写等语义 evidence 时直接复用；只有候选集合内证据不足的文件才重新 parse。内容变化、缺失或冲突不会静默沿用旧证据。复用/刷新/无效数量进入 PlanVersion change summary 和 UI。

## 5. DELTA Plan 与执行轮次

schema v6 为 Conversation PlanVersion 增加：

- `baseline_execution_round_id`：本轮所基于的最后一次成功执行；
- `plan_kind`：`FULL` 或 `DELTA`。

DELTA 只包含实际需要调整的文件，`kept_file_count` 记录未变化文件。编译仍使用既有 `PlanCompiler`，持久化和批准仍使用 `SqliteOperationJournal`，执行仍使用 `TaskCoordinator/FileOperationEngine`。批准前磁盘不变化；执行前再次校验 baseline、plan hash、Context revision 和受影响文件状态。每次成功执行创建新的 ExecutionRound，不覆盖旧轮次。

## 6. 外部变化与错误

准备和执行前会在授权根目录内验证候选文件：同一 fingerprint 的唯一新路径标记 `FILE_MOVED_EXTERNALLY`，内容变化为 `FILE_CHANGED`，缺失为 `FILE_MISSING`，多重匹配为 `PATH_CONFLICT`。这些状态阻止旧 DELTA 继续执行，要求重新确认当前状态；系统不会猜测或自动覆盖。

## 7. API 与 UI

- `GET /api/v1/conversations/{id}/workspace-state`
- `POST /api/v1/conversations/{id}/refinements/prepare`
- `POST /api/v1/conversations/{id}/plan-versions/{version}/approve`
- `POST /api/v1/conversations/{id}/plan-versions/{version}/execute`

Conversation Workspace 在已有完成轮次后把新消息作为后续整理请求；展示影响范围、候选数、证据复用/刷新数、DELTA 变更和未变化数。全局重规划先显示明确确认。ExecutionResultCard 在成功后提示可以继续对话。

## 8. 并发、恢复与安全

Context 使用 expected revision CAS；PlanVersion 固定 basis revision、baseline round 和 plan hash。若其他执行轮次已推进，返回 `DELTA_PLAN_STALE`。重启后所有 Message、Context、PlanVersion、ExecutionRound、ConversationFile 和 journal 仍从 SQLite 恢复。

Conversation soft delete、消息追加和后续整理均不会删除真实文件或隐式 Undo。模型 provider 细节和密钥不进入 Conversation 数据；密钥继续由 Windows Credential Manager 管理。

## 9. 性能与测试

局部请求的模型输入规模由 affected scope 决定，而不是目录总文件数；有效 evidence 不重新 parse/上传。500 文件测试中只选择 20 个候选，20 图片真实 DeepSeek 冒烟中只处理 10 个建筑候选并复用全部 10 份 evidence。自动化覆盖连续三轮、批准前磁盘不变、外部变化、重启恢复、全局确认和旧 AI-only 回归；具体命令与计数见阶段报告。

## 10. 当前限制

- V1 的自然语言范围解析采用当前 taxonomy 名称和受控短语，不支持“这些/那几个”等高级指代。
- GLOBAL V1 会对全量文件重新评估，但仍使用当前 taxonomy；完整 taxonomy redesign 留给后续 Agent/Replanner。
- ToolCall/ToolResult ledger 仍 deferred；当前 PHASE F AgentOrchestrator 文件在工作树中不存在，PHASE H 以窄职责 service 接入现有安全核心。
- 当前 file ID 保证 Task 内跨移动稳定，跨 Task 全局 canonical identity 仍是后续债务。
