# PHASE H — Post-Execution Conversation 审计

日期：2026-09-21  
范围：修改前现状；以当前源码、schema v5、PHASE D/G 报告和实际测试为准。

## 1. 输入完整性

用户要求先读的 `docs/CONVERSATION_AGENT_V1.md` 与 `artifacts/reports/conversation-agent-v1.md` 在当前工作树不存在。源码中也没有 AgentOrchestrator、Intent Router 或 Tool Registry。PHASE G 报告已经明确记录同一缺口。因此当前项目拥有 Conversation 数据模型、持久消息 UI、PlanVersion/approval/ExecutionRound 基础，但没有能把用户消息转成分析/方案/执行的 PHASE F Agent loop。

本阶段不能把缺失能力描述为“已存在”。实现策略是增加只服务于 post-execution refinement 的窄编排服务和严格后端校验，不引入通用 Shell/File Tool，也不允许模型直接给出路径或执行操作。

## 2. 当前核心实体可复用情况

| 实体/模块 | 当前事实 | PHASE H 处理 |
|---|---|---|
| `conversations` | 状态只含 ACTIVE/ARCHIVED/DELETED/ERROR；执行链不会把它改成 COMPLETED | 直接复用，补回归测试保证执行后 ACTIVE |
| `conversation_contexts` | 已有 current taxonomy/plan/execution pointer、context revision、file state revision、requirements JSON | 复用；状态同步时推进 revision/file revision |
| `conversation_files` | 通过 `file_id` 引用核心 `files.id`；保存 first/current path/fingerprint | 复用；补执行后批量同步、外部变化检测与 scope 校验 |
| `conversation_plan_versions` | 已有 parent、basis context revision、taxonomy snapshot、plan/hash、计数与不可变历史 | 增加 execution baseline 与 FULL/DELTA 语义 |
| `conversation_execution_rounds` | round_number、PlanVersion、既有 plan、状态、summary | 复用；补完成后的同步/指针/版本状态推进 |
| `plans/operations/operation_events` | 真实执行事实、hash、approval、journal/checkpoint、no-clobber 与 Undo 依赖 | 不复制、不重写；Delta 仍持久化为既有 plan/operations |
| `file_profiles.profile_json` | 保存解析后的 FileProfile/Evidence；parser cache 已按内容 hash 复用 | 复用；增加显式 evidence freshness/usability 决策 |
| `taxonomies/categories/classifications` | 保存语义 taxonomy 和 AI 分类结果 | 复用；不根据扩展名、文件名或目录名做最终语义分类 |

## 3. 十项重点结论

1. **Execution 后 Conversation 是否 ACTIVE**：是，现有 execution/task journal 不修改 `conversations.status`；但没有专项回归测试，也没有完成钩子维护 Conversation 状态。
2. **stable file_id 是否跨移动保持**：是。OperationJournal 在 COMMITTED/UNDONE move 时只更新 `files.current_path/path_key`，不修改 `files.id`。
3. **移动后 current path 是否更新**：核心 `files.current_path` 会更新；`conversation_files.current_known_path` 不会自动更新，只在显式 verify 时投影，因此 UI 可能暂时显示旧路径。
4. **FileProfile / ConversationFile 路径职责**：FileProfile 是内容/evidence；核心 `files.current_path` 是执行后的事实路径；ConversationFile 是会话观察投影。当前三者缺少统一 post-execution sync。
5. **最新 ExecutionRound 获取**：列表按 round_number 排序，Context 有 current_execution_round_id；可以准确读取，但 update round 状态不会同时维护 PlanVersion/context/file state。
6. **current PlanVersion**：通过 `conversation_contexts.current_plan_version_id` 保存，创建版本用 context CAS 更新。
7. **执行后 taxonomy**：PlanVersion 的 `taxonomy_snapshot_json` 和可选 taxonomy_id 保留；Context 也有 current_taxonomy_id。不会只依赖 Windows 文件夹名。
8. **Evidence 跨 Turn 复用**：FileProfile evidence 与 parser content cache 可复用，ClassificationService 也按 input hash 缓存；但当前没有 refinement 级 `REUSE/REFRESH_REQUIRED/INVALID` 判定与统计。
9. **为什么不能处理执行后新要求**：缺少 AgentOrchestrator/IntentRouter、CurrentWorkspaceState、AffectedScopeResolver、DeltaPlanBuilder、global confirmation gate，以及从 message 到 PlanVersion 的真实编排 API。
10. **是否会无条件重跑全部文件**：现有一次性 Task 流程面向 task scope 批量解析/分类，没有 post-execution affected-scope 入口。若直接复用旧链会重新遍历全 task，因此必须新增受影响集合参数和后端强校验。

## 4. 当前安全边界

- FileOperationExecutor 已校验 plan hash、approval、source identity、target collision、no-clobber，并将操作逐项写入 OperationJournal。
- AI 分类只返回允许的 category_id/evidence；模型不提供 target path。
- `files.current_path` 的变更发生在 journal 的 COMMITTED/UNDONE checkpoint，不覆盖 operations 的 source/target 历史。
- Conversation soft delete 不删除真实文件，也不级联删除 plan/journal/undo。
- PHASE H 必须继续通过既有 PlanCompiler/OperationJournal/approval/Executor，不创建 `move_file`/`delete_file`/shell 工具。

## 5. 现有缺口与最小改动边界

### 必须补齐

- PlanVersion：`plan_kind=FULL|DELTA`、`baseline_execution_round_id`。
- WorkspaceStateService：从 Conversation scope、Context、最新 executed round、taxonomy snapshot、ConversationFile/Core file/Profile 组装当前事实。
- 执行后同步：成功 move 后保持 file_id、同步 current path/fingerprint、推进 file_state_revision，并保留历史 operation path。
- AffectedScopeResolver：LOCAL/PARTIAL/GLOBAL，category/file ID 必须从 DB/taxonomy 解析；LOCAL/PARTIAL 默认 preserve_unaffected。
- EvidenceReuseService：以 fingerprint 与 evidence 内容/provenance 判定 REUSE/REFRESH_REQUIRED/INVALID。
- DeltaPlanBuilder：只接受已验证 affected file IDs，基于当前路径与既有 category ID 生成最小 operation 集合，并继续走 plan hash/approval/journal。
- Refinement service/API：明确 global confirmation、ambiguity/error codes、Context revision、PlanVersion、approval 与 round completion。
- UI：执行完成后 Composer 持续可用；展示影响范围、DELTA、全局提示、第二/三轮历史和刷新后的文件。

### 不在本阶段补齐

- 通用 ToolCall ledger、任意 tool loop、高级“这些/那几个”引用、Conversational Undo、长期记忆、向量数据库、Watch Folder。
- 跨 Task 全局 canonical file identity。当前 `files.id` 在既有 Task/Conversation 映射内跨 move 稳定。

## 6. 修改前测试基线

- 前端：`npm.cmd run test -- --run` → 4 files / 25 tests passed。
- 后端：系统 Python 缺少 pytest；项目标准命令改用 `uv --directory .\backend run --all-extras pytest -q`。该命令在审计期间启动，最终结果记录到阶段报告，不把中间进度写成通过。

## 7. 实施结论

当前 PHASE D/G 基础足以承载 PHASE H，但不是“接几条 UI”即可完成。最安全的路径是在 v5 上做非破坏 v6 扩展，增加 execution baseline/plan kind 和窄的 post-execution services；真实执行仍委托既有 TaskCoordinator/FileOperationExecutor，Conversation 层只编排、验证和投影状态。

