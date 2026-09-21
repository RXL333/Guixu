# PHASE H — Post-Execution Conversation 实现报告

日期：2026-09-21  
状态：PASSED（PHASE H V1 范围）

## 实现结果

修改前审计见 [post-execution-conversation-audit](post-execution-conversation-audit.md)。当前工作树缺少目标中预期的 PHASE F `AgentOrchestrator/Intent Router/Tool Registry` 产物，因此没有伪造通用 Agent；本阶段以窄职责 PostExecutionConversationService 接入 PHASE D/G 与现有安全执行核心。

最终链路为：已完成 ExecutionRound → 读取 CurrentWorkspaceState → 从当前 taxonomy/file membership 限定 affected scope → 校验真实磁盘和 fingerprint → 复用或最小刷新 evidence → 受限模型判断 → 编译新的 FULL/DELTA PlanVersion → 用户批准 → 既有 FileOperationEngine 执行 → 新 ExecutionRound → Conversation 继续 ACTIVE。

## 数据、迁移与复用

- migration：`0006_post_execution_conversation.py`，schema version 6，非破坏性升级。
- PlanVersion 新增 `baseline_execution_round_id`、`plan_kind`；ConversationFile 新增 `current_category_id`。
- 直接复用：Conversation/Context/Message、files/FileProfile evidence、taxonomy/categories、plans/operations/operation_events、PlanCompiler、OperationJournal、TaskCoordinator/FileOperationEngine、Undo 安全记录和 ModelProfile/Privacy。
- 没有新建第二套 Execution、Evidence、文件 identity、向量库或模板/规则替代物。

## Workspace、范围与 Evidence

WorkspaceStateService 读取当前 scope、requirements、taxonomy、plan/execution pointers、稳定 file ID、当前路径、fingerprint、分类和 FileProfile。操作日志更新核心 path 后，ExecutionRound 完成会同步 ConversationFile；历史 Plan 路径不被重写。

AffectedScopeResolver 输出 LOCAL/PARTIAL/GLOBAL、category IDs、候选 file IDs、固定目标类别和 preserve-unaffected。GLOBAL 需要显式二次确认。EvidenceReuseService 输出 REUSE/REFRESH_REQUIRED/INVALID，只在候选范围内补证；模型返回的 ID/category 均须属于受控集合。

## Plan 与执行安全

局部调整创建 `DELTA`，显式全局调整创建 `FULL`；二者都绑定最后成功 ExecutionRound、basis Context revision 和现有 core plan hash。批准前不触碰磁盘，执行前重新校验 baseline 与 affected files。第二/第三轮继续通过既有 journal、碰撞策略、授权 scope 和 executor，不允许模型提供目标路径或调用磁盘。

外部移动、内容变化、缺失和重复 fingerprint 分别产生 `FILE_MOVED_EXTERNALLY`、`FILE_CHANGED`、`FILE_MISSING`、`PATH_CONFLICT`，阻止陈旧方案静默执行。Conversation 删除仍不操作磁盘或 Undo。

## API 与前端

新增 workspace-state、refinements/prepare 和 plan-version/execute API；批准 API 同步 core journal approval。前端在完成轮次后继续接收消息，展示影响范围、候选/保留文件、evidence 复用/刷新、DELTA 变化和全局确认，批准后执行并刷新消息、文件、版本和轮次。

## 自动化与真实模型证据

- 修改前 baseline：后端 149 passed；前端 25 passed。
- PHASE H 专项：`test_post_execution_conversation.py` 4 passed，覆盖第二/第三轮真实 temp 文件移动、500 文件/20 候选局部范围、global warning、restart、external move/change/missing、evidence reuse/refresh。
- 后端最终：`uv --directory .\backend run pytest -q` → 153 passed / 2 warnings。
- 前端：`npm.cmd run test -- --run` → 4 files / 28 passed；`npm.cmd run typecheck` → exit 0；`npm.cmd run build` → exit 0。
- AI-only 旧主链包含在后端全量回归并通过。
- 真实 DeepSeek：20 个项目测试图片记录，10 个候选、10 evidence reused、0 refresh、2 个 DELTA 操作、ExecutionRound #2 COMPLETED；一次调用 1563/565 tokens、2741 ms。详见 [real-post-execution-refinement](real-post-execution-refinement.md)。
- 用户明确要求加快进入下一阶段，因此未继续做额外 Playwright/pywebview 截图复验；不把未运行的截图项写成通过。

## Screenshots 与 Performance

截图目录未生成：用户在收尾时明确要求停止反复验证并尽快进入下一阶段，因此本轮保留前端自动化、typecheck 和 production build 证据，不虚构人工截图。性能边界通过 500 文件/20 候选测试和真实 20 图片/10 候选请求验证；局部 refinement 的解析、模型输入与 DELTA 编译都限定在 affected scope，未重新处理无关文件。

## 已知限制与下一阶段切入点

- V1 范围解析依赖当前 taxonomy 名称和受控短语，不支持“这些/那几个”、框选引用或复杂指代。
- GLOBAL 目前在当前 taxonomy 内全量重评，不重建 taxonomy；完整 Incremental Replanner 留给下一阶段。
- PHASE F 通用 Agent runtime/Tool ledger 在当前工作树不存在；当前后续整理是安全边界明确的专用编排服务。
- 取消正在进行的远程 refinement 尚未形成持久 AgentTurn ledger；现有 HTTP 超时/模型取消能力不等价于可恢复 turn cancellation。
- file ID 仍是 Task 内跨移动稳定，而非跨 Task 全局 canonical identity。

下一阶段最合适的切入点是补齐统一 AgentOrchestrator/AgentTurn ledger，把当前 `prepare_refinement` 注册为受限能力，并保持本阶段的 affected-scope、evidence freshness、PlanVersion baseline、approval 和 FileOperationEngine 边界不变。不要绕过它们直接让模型操作路径。
