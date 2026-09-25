# 项目状态

## PHASE N 真实照片整理阻断修复（2026-09-24）

- 用户实际目录为 `D:\Media\Photos\Nikon_z50照片\测试`（48 JPG）。已在应用数据库确认旧失败执行轮次的 48 个 operation 均停在 `PLANNED`：`operations` 表未保存参与计划哈希的 `reason`，重载后 `verify_plan_hash` 为 false，执行器在首个文件操作前报 `PLAN_HASH_MISMATCH`。失败轮次又使 context revision 增加 1，原批准方案重试报 `PLAN_CONTEXT_STALE`。
- schema v11 / Alembic 0011 保存 `operations.reason`；旧记录只恢复确定性 skip/noop 原因，计划哈希仍须复核通过。允许相同批准方案在失败轮次未触碰任何 operation、任务 revision 未变化时安全重试。迁移前创建 SQLite 一致性备份。其余旧方案如果不能重建原哈希，继续阻止执行。
- 定向测试：操作日志与数据库契约 `20 passed`；首次分析与执行后整理 `16 passed`；失败后零操作重试专项 `1 passed`。最终全量后端 `201 passed / 2 warnings`、前端 `39 passed`，均 exit 0。新 Windows onedir/portable 包构建、冻结诊断和 worker 冒烟 exit 0，路径见 [阶段报告](artifacts/reports/phase-n-photo-classification-fix.md)。
- 真实目录原方案经应用 API 重试执行 `HTTP 200`、ExecutionRound #1 `COMPLETED`；32 项 move `COMMITTED`，16 项 skip `SKIPPED`。随后仅针对这 16 张用已有视觉证据作一次模型复核，生成并批准 DELTA v2，ExecutionRound #2 `COMPLETED`、16 项 move `COMMITTED`。两轮后根目录剩余 JPG 为 0，递归 JPG 仍为 48 张，文件名与逐文件 SHA-256 映射完全一致。未访问测试范围外个人目录。新包尚未进行可见桌面人工操作验收，发布判定仍为 **NOT RELEASE READY**。

## PHASE N 最终验收（进行中，2026-09-24）

当前发布判定：**NOT RELEASE READY**，版本仍为 `0.1.0 dev`，没有生成或标记 1.0 RC/stable。Feature Freeze 生效，详见 [验收矩阵](docs/RELEASE_ACCEPTANCE.md)、[缺陷登记](artifacts/reports/guixu-1.0-bug-registry.md)和[阶段报告](artifacts/reports/guixu-1.0-final-acceptance.md)。

- 已实现执行前 FULL v1→v2 的后端/前端链路；当前真实 DeepSeek 5-JPG v1→修改要求→v2/diff→批准→执行→重启读取完整 E2E 一次通过（7 次模型调用成功，审批前文件 hash 不变）。详见 `artifacts/reports/phase-n-real-deepseek-e2e.json`；更长的继续对话/Undo、发行包链仍未验收。
- 针对用户 16:24 截图核对本机只读任务/模型调用审计：请求已成功返回，规划/分类输出未通过应用契约，旧 UI 却显示“不可用或授权不足”并留下过期扫描状态。修复首次视觉分类引用尚未生成 evidence ID 的死锁、图片批次过大、缓存描述重复要求；缺少解释字段时强制标记证据不足以进入复核；失败 Task 持久化为 FAILED；首次/后续分析 API 和前端现能展示契约错误详情。定向后端测试和前端 16 tests/typecheck 通过。
- 已使用修正后的执行历史 URL 重跑真实隔离 5-JPG 全链并 exit 0：v1 被 v2 supersede、5 个文件目标变化、显式审批后 Execution #1 COMPLETED，重启后读回 5 条消息/2 个方案/1 执行/5 文件引用。此前错误格式输出由有限 repair 和证据降级处理；用户真实目录未被触碰。
- 已修复 Conversation 文件引用 API 的越权 scope attach：跨授权目录的文件 ID 会导致整批拒绝；API 回 `409 REFERENCE_SCOPE_VIOLATION`。新增原子性及 API 回归测试通过；定向组合 `8 passed`。同时将 500/1000/5000 文件 attach 优化至 .131/.256/1.298 秒（原 5000 文件约 32.73 秒）；后端数据已更新，桌面 UI 大列表性能仍未测。
- 发布安全核查新增 `scripts/audit_release_secrets.py`：对 onedir 与 portable zip 各检查 434 个文件、301,780,329 解压字节；开发资产路径与常见 DeepSeek/GitHub/AWS/PEM/Bearer/inline credential 签名均 0 命中。此为已知模式扫描，不排除任意未知凭据。隐私/no-secret caplog 回归重跑 `1 passed`；S17 更新为 PARTIAL（发行态日志与 Credential Manager 仍未覆盖）。
- 本轮开发态安全/幂等回归 `13 passed`：提示注入输出仍受类别 allowlist 限制、自然语言首次请求只生成预览、错误审批 hash 拒绝、目标冲突不覆盖、外部 rename/move/modify/missing/new 均可识别、重复 execute/undo 幂等、Windows reparse 不递归。S01/S03/S04/S05/S09 仅标 PARTIAL；S08/S10/S11 有对应集成证据。完整安全矩阵及发行态验证仍未完成。
- 补上 Conversation 删除安全缺口：`test_conversation_soft_delete_preserves_disk_journal_and_undo` 真实执行 2 个临时文件后删除会话，path/hash 完全不变，operation/event journal 和 round 保留；恢复后 Undo 预览仍可生成（`1 passed`）。API deletion/restart regression `1 passed`。S06/S07 非法段、锁定与只读源的定向场景再通过 `12 passed`；长路径和 ACL permission-denied 仍未覆盖。C20 现为开发态 PASS。
- 继续跑过 migration、旧 Task 与 single-flight 定向回归（`3 passed`）：迁移备份/重复初始化与 legacy snapshot、旧 Task 不自动链接 Conversation、同文件缓存请求串行化均有证据。S15/S16 仅更新为 PARTIAL，因为 SQLite 多写者/异常关闭和真实历史 schema 文件升级尚未覆盖。
- 最新定向验收发现并修复一个会阻断真实整理的安全校验缺陷：部分扫描流程的 `files.sha256` 尚未持久化，ConversationFile 因此记录空指纹，执行前重验证虽显示文件未变化仍拒绝批准（`FILE_STATE_UNAVAILABLE`）。现在仅在已有扫描 SHA-256 时复用，否则安全地读取当前文件 identity；首轮批准→执行、PlanVersion v1/v2/v3/恢复为新版本、post-execution 三轮 DELTA 后端用例共 `3 passed`，前端 workspace `16 passed`。C04/C06/C09 为开发态 PASS，C05/C07 仍 PARTIAL；C10/C11 后由真实 DeepSeek 临时目录 smoke 补齐。当前源码已打包至 `artifacts/release-phase-n/Guixu-0.1.0/Guixu.exe`（SHA-256 `E22BFCD6ABB82978FE0A0CF1891BE14120321023A2CBE36431BEDCFB65CDEFFB`）；frozen diagnose/worker smoke 通过，portable ZIP 已更新，已知签名扫描无命中。
- 模型/AI-only 边界再跑 7 个定向回归通过：`401` 不重试、`429 Retry-After` 有界重试、JSON repair/重问、不支持 Vision 阻断、危险路径类别拒绝、同扩展名基于内容分类。D04/D06/D08/D09/D10/D12 仅记 PARTIAL；timeout/5xx/cancellation 仍未测。
- 当前源码的新冻结包已重建至 `artifacts/release-phase-n/Guixu-0.1.0/Guixu.exe`（SHA-256 `E22BFCD6ABB82978FE0A0CF1891BE14120321023A2CBE36431BEDCFB65CDEFFB`，18,685,411 bytes）及 portable zip（141,514,522 bytes，SHA-256 `1E1962323606C56E77EF467D4CCC29245AB81699C5589543C99BC29EB2C593C9`），与旧 `release-phase-m` 分开。production build、PyInstaller、frozen diagnose 与 worker smoke 已运行；Inno Setup 缺失。当前仍 **NOT RELEASE READY**；P0 全面 gate 尚未通过。
- 最近一次完整回归：`uv run pytest -q` 为 `198 passed`（78.29s，exit 0）；之后新增 timeout/5xx transport 用例定向 `2 passed`，未重复全套。前端 `npm run test:run` 为 5 files / 39 tests passed；最新打包运行的 production `npm run build`（含 vue-tsc）、PyInstaller、frozen diagnose/worker smoke 均 exit 0。Backend 有 Starlette/Pillow warning 与 pytest Windows symlink temp cleanup `WinError 145`；frontend ModelsPage 有未注册 RouterLink warning。B01 暂记 PARTIAL，B02 PASS；桌面 packaged UI/clean machine 仍未验收。
- C12 File References 的精确 5-file 范围回归已补：选择 5 个 stable file IDs 后，ReferenceResolver 和 AffectedScopeResolver 均保持候选集合恰好为这 5 个；该测试定向通过。完整计划编译、审批、执行与真实桌面 UI 链仍属未验收，因此 C12 维持 PARTIAL。
- DeepSeek transport 异常矩阵补测：MockTransport 验证读取超时最多尝试 3 次并返回 `MODEL_NETWORK_ERROR`，503 可恢复以及持续 503 有界失败；定向结果 `2 passed`。D05/D07 只证明传输合约，不代表真实供应商故障注入；D11 请求取消仍未验收。
- 当前 `release-phase-n` EXE 已在本机真实关闭/重启一次，并恢复同一已有会话、消息、48 个文件引用及 96 项文件列表，B11 标记 PASS（saved-session restore）。恢复对象绑定用户真实照片目录，因此没有发送模型请求或执行文件操作；重启后继续 refinement/执行/Undo（C17）仍未验收。
- 已有 20-file 真实 DeepSeek 执行后 refinement smoke 通过；阶段基线全套通过，最近模型修复后只跑了相关定向测试。按用户要求未反复跑完整回归，不将未测写为通过。
- 2026-09-24 使用 `backend\.venv\Scripts\python.exe` 在自动清理的系统临时目录重跑 post-execution DeepSeek smoke，exit 0：20 个合成图片文件，LOCAL/building scope 10 candidates，10 evidence reused、0 refreshed、1 次 AI 调用，DELTA 2 operations，ExecutionRound #2 COMPLETED、Conversation ACTIVE；候选外 10 个文件原路径及 SHA-256 均不变，文件数前后均为 20。C10/C11 标记 current-source real smoke PASS；发行包重启后继续 refinement/执行/Undo 的 C17 仍 NOT_TESTED。
- 最新快速回归：Conversation Undo 4/10 与普通 Execution 8/20 真实子进程 crash→重启→续跑均通过；20 项执行用例恢复余下 12 项且完成 Conversation round。Undo + OperationJournal 定向回归 `24 passed`；首次分析/分类相关集成与分类测试 `25 passed`。50 图 Analysis 在 31 个视觉证据持久化后进程退出，重启复用 31 个视觉 evidence，只继续 19 个文件的视觉分析；补齐另外 3 个已有视觉证据的分类后完成 50 项分类，并恢复 PlanVersion/提议消息，磁盘 hash 不变（专项 `1 passed`，Fake gateway）。真实 DeepSeek v1→v2→批准→执行→重启读取 E2E exit 0，重规划保护集成 `5 passed`。当前登记 open P1=0；发行包恢复、Clean Windows、Inno 安装器、签名、原生 UI/DPI 和最终全量回归未完成；未 push/tag。

版本：0.1.0 dev（PHASE F 首次整理分析链路已接入，禁止发布 0.2.0）。更新时间：2026-09-24。

## PHASE F 首次整理分析

- 首轮真实整理入口已补齐：首次 `FULL / PROPOSED` 方案现在显示“确认并开始整理”，沿用方案 hash、文件状态 revision、授权记录和现有 FileOperationEngine；确认前仍只预览，确认后才创建 ExecutionRound 并移动/复制文件。此前按钮仅对带 baseline 的后续 DELTA 方案显示，导致首轮只能分析不能执行。新增首轮批准→执行临时目录回归测试；同时将桌面目录选择改为 `webview.FileDialog.FOLDER`，消除 pywebview 弃用警告。
- 已修复“发送消息无反应”：此前前端只调用 Message API 保存用户消息，后端明确不触发分析；现在首次发送会调用真实 `POST /api/v1/conversations/{id}/turns`，执行扫描、内容证据解析、AI 规划、AI 分类和只读方案编译。
- 首次分析生成 `PlanVersion v1`（`FULL / PROPOSED`，无 baseline execution），助手回复包含实际文件数量、分类数量和保留/冲突计数；不会移动或修改磁盘文件。
- 已用本机启用的 DeepSeek profile 在隔离目录完成真实 smoke：5 个 JPG → 真实视觉 planner/classifier → 4 个类别、5 个受影响文件、唯一 v1 预览；`model_calls` 为 planning/classification 各 1 次，5 条云端视觉 evidence，磁盘 SHA-256/路径不变，无 ExecutionRound。
- 修复了首次自然语言“这些文件”的旧引用歧义、旧 `model_calls.purpose` CHECK 兼容映射，以及跨任务画像复用时图片缩略图路径水合。
- 首次流程需要有效目录授权、已启用模型和隐私确认；无能力或授权时返回明确错误，不使用本地语义 fallback。已有方案/执行记录继续走后续 refinement。
- 专项验证：后端首次分析 + AI-only 闭环 3 passed；前端 Conversation Workspace 14 passed；typecheck/build 均 exit 0。报告：[phase-f-first-analysis-audit](artifacts/reports/phase-f-first-analysis-audit.md)、[real-phase-f-first-analysis-smoke](artifacts/reports/real-phase-f-first-analysis-smoke.md)。

## Conversation Agent 转型准备

- PHASE L Conversational Undo 已完成：schema v10 / Alembic 0010 新增不可变 UndoPlan/UndoPlanItem，并为 ExecutionRound 增加 FORWARD/UNDO、目标轮次和 partial/full undo state。UndoTargetResolver 支持最近一次、明确历史轮次和同一执行内的 File References；逆向路径只来自真实 COMMITTED OperationJournal。Dependency Analyzer 阻止后来又操作同一 stable file 的历史撤销；preview、approval、hash/revision/scope/fingerprint/no-clobber、外部修改/移动/缺失/目标冲突、幂等和 crash recovery 均接入既有 FileOperationExecutor/Recovery。Undo 成功形成新的 ExecutionRound/Journal，保留原历史，推进 file_state_revision，不倒退 PlanVersion，也不使内容未变的 Semantic Cache 失效。详见 [CONVERSATIONAL_UNDO](docs/CONVERSATIONAL_UNDO.md)、[审计](artifacts/reports/conversational-undo-audit.md) 和 [阶段报告](artifacts/reports/conversational-undo.md)。
- PHASE L 验证：后端全量 176 passed / 2 warnings；前端 4 files / 34 passed，typecheck 与 production build 均 exit 0；20 文件真实临时目录完成 Round 1、局部 Round 2、5 文件 Undo 和继续 Round 4。Playwright 真实页面已保存 request/preview/conflict/confirming/complete/history 截图到 `artifacts/ui/conversational-undo/`，runtime OpenAPI contract 已重新导出。当前限制为不支持 Redo、级联撤销、跨轮次 partial batch，也没有通用 Agent Tool Registry。

- PHASE K Session Recovery 已完成：schema v9 / Alembic 0009 新增持久化 AgentTurn 与 workspace reconciliation ledger，并为 PlanVersion 增加 `basis_file_state_revision`。启动时会把未结束 turn 标记为 INTERRUPTED，把仍有未完成 operation 的执行轮次标为 RECOVERY_REQUIRED；打开/执行前按 stable `files.id`、fingerprint 和授权 scope 核对外部移动、重命名、修改、缺失、冲突、新文件与 scope 不可用。相关方案会在受影响文件变化时要求重新校验，不自动重放模型、批准或执行；既有 OperationJournal/RecoveryService、Semantic Cache、PlanApproval 和 FileOperationEngine 继续复用。新增 recovery-status、reconcile、revalidate、resume/retry、external-changes、scope relink API 与最小 UI 提示。详见 [SESSION_RECOVERY](docs/SESSION_RECOVERY.md)、[session-recovery-audit](artifacts/reports/session-recovery-audit.md) 与 [session-recovery](artifacts/reports/session-recovery.md)。
- PHASE K 验证：后端 169 passed / 2 warnings；前端 4 files / 31 passed，typecheck/build 均 exit 0；runtime OpenAPI contract 已重新导出。剩余边界为后续 Agent worker、Chat UI、Tool Calling、Watch Folder、Conversational Undo 与新的桌面人工截图验收。

- PHASE J Semantic Cache 已完成：新增 schema v8 `file_evidence` canonical ledger 与 Alembic 0008；按 stable file ID + SHA-256 fingerprint 复用 parser/OCR/visual/document/media evidence，记录 producer/model/prompt/schema provenance，支持 content-change invalidation、force refresh、cleanup/clear、统计与单进程 single-flight。AI Planner/Classifier 和 Post-execution refinement 已接入统一服务；taxonomy/requirements 改变只重新分类，不重复读取有效证据。详见 [SEMANTIC_CACHE](docs/SEMANTIC_CACHE.md)、[semantic-cache-audit](artifacts/reports/semantic-cache-audit.md) 与 [semantic-cache](artifacts/reports/semantic-cache.md)。
- PHASE J 限制：L3 分类 decision cache、向量/RAG、Watch Folder、跨 Task canonical file identity、多进程锁和真实 DeepSeek smoke 仍待后续/外部授权；本阶段没有删除旧 `file_profiles`，没有修改 FileOperationEngine 或真实磁盘文件。

- PHASE I File References 已完成：schema v7 新增 MessageFileReference 关系表与 path snapshot，`ReferenceResolver` 可确定性解析 UI selection、focus、exact filename、最近消息集合、当前 Plan changes、最近成功 Execution 的实际 affected files 与明确 category-all。所有结果使用当前 Conversation 的 stable `file_id` 并执行 scope/missing/changed 校验；显式引用严格限制 AffectedScope/Delta Plan，不绕过 Plan、Approval、FileOperationEngine 或 Undo。前端已加入多选引用、Composer chips、消息 badge、点击联动、发送/切换清空和窄窗口布局修复。详见 [FILE_REFERENCES](docs/FILE_REFERENCES.md)、[审计](artifacts/reports/file-reference-audit.md) 与 [阶段报告](artifacts/reports/file-references.md)。
- PHASE I 验证：后端 159 passed / 2 warnings；数据库与桌面安全专项 10 passed；前端 4 files / 31 passed，typecheck/build 均 exit 0；500 文件批量引用通过。Playwright 本地 QA 完成 7 个指定场景并保存到 `artifacts/ui/file-references/`。当前限制为未实现 Shift 范围选择、active-category 浏览 UI、missing 部分继续快捷确认；仓库仍无通用 AgentOrchestrator/Tool Registry，本阶段只接入现有 Message 与 Post-Execution refinement。

- PHASE H Post-Execution Conversation 已完成：执行后 Conversation 保持 ACTIVE；新增 CurrentWorkspaceState、LOCAL/PARTIAL/GLOBAL 影响范围、Evidence reuse/refresh、基于明确 baseline ExecutionRound 的 FULL/DELTA PlanVersion、approval-gated 第二/第三轮执行、外部移动/内容变化/缺失/冲突保护。Conversation Workspace 支持完成后继续输入、全局确认、DELTA 摘要和第二轮执行结果；未实现高级文件指代、Conversational Undo、记忆、Watch Folder 或任意文件工具。详见 [POST_EXECUTION_CONVERSATION](docs/POST_EXECUTION_CONVERSATION.md) 与 [阶段报告](artifacts/reports/post-execution-conversation.md)。
- PHASE H 验证：后端 153 passed / 2 warnings；专项真实临时目录测试 4 passed；前端 4 files / 28 passed，typecheck/build 均 exit 0。真实 `deepseek-flash` 隔离验收使用 20 个项目测试图片记录，只评估 10 个建筑候选、复用 10 份 evidence、生成 2 项 DELTA 并完成 Execution #2；模型调用一次，Conversation 保持 ACTIVE。按用户加速指令停止额外 UI 截图复验。

- PHASE E Conversation UI Skeleton 已完成：主工作区切换为三栏 Conversation Workspace（会话导航 / 消息与输入 / 文件工作区），接入 Conversation、Message、ModelProfile、ConversationFile 的真实 API；支持新建/搜索/切换/重命名会话、消息持久化、文件选择、Current/Preview/History 三个右侧视图以及侧栏/文件区折叠。没有调用 LLM、没有伪造助手回复、没有实现 Chat Agent、Tool Calling 或新执行逻辑。前端报告见 [conversation-ui-skeleton](artifacts/reports/conversation-ui-skeleton.md)，视觉 QA 见项目根目录 [design-qa](design-qa.md)。
- PHASE E 验证：`frontend` 的 `npm.cmd run test -- --run` 为 4 files / 24 passed，`npm.cmd run typecheck` exit 0，`npm.cmd run build` exit 0；IAB 在 1310×898 CSS viewport 验证真实会话、4 个临时文件、消息写入、文件选择、空方案/执行状态、文件区收起和侧栏收起。当前仍保持 0.1.0 dev，未进入 PHASE F。
- PHASE G Plan Versioning 已完成：schema v5 新增 `conversation_plan_approvals`，并扩展 PlanVersion 的恢复来源、摘要计数和消息审计字段；新增集中式 PlanVersionService/PlanDiffService、线性 parent/current CAS、确定性 taxonomy/file diff、hash/context approval stale 保护、历史方案安全恢复 child，以及 approval-gated ExecutionRound API。旧 Plan、OperationJournal、Undo 和真实文件继续复用，不覆盖已执行版本，不执行 Agent/Tool Calling/增量重规划。详见 [plan-version-audit](artifacts/reports/plan-version-audit.md)、[PLAN_VERSIONING](docs/PLAN_VERSIONING.md) 与 [plan-versioning](artifacts/reports/plan-versioning.md)。
- PHASE G 验证：后端 `pytest backend/tests -q` 为 149 passed / 2 warnings；版本专项与会话专项 7 passed，数据库契约/Alembic 4 passed；前端 `npm.cmd run test -- --run` 为 4 files / 25 passed，`npm.cmd run typecheck` exit 0，`npm.cmd run build` exit 0；`scripts/export_runtime_contract.py` 与 `git diff --check` 均 exit 0。warning 仅为既有第三方/Windows pytest 临时 reparse 清理提示，不影响退出码。
- PHASE D Conversation Data Model 已完成：schema v4 新增 `conversations`、`conversation_scopes`、`conversation_messages`、`conversation_contexts`、`conversation_plan_versions`、`conversation_execution_rounds`、`conversation_files`；Task 增加 nullable 会话映射。Context 使用 expected revision CAS，PlanVersion/ExecutionRound/Message 追加式保存，Conversation/File 引用与 soft delete 不操作真实磁盘、不删除既有 plan/journal/Undo。基础 repository/service/API 已加入，但本阶段没有 Chat UI、LLM 对话循环、Agent Orchestrator、Tool Calling 或新分类逻辑。审计见 [conversation-schema-audit](artifacts/reports/conversation-schema-audit.md)，模型文档见 [CONVERSATION_DATA_MODEL](docs/CONVERSATION_DATA_MODEL.md)，阶段报告见 [conversation-data-model](artifacts/reports/conversation-data-model.md)。
- PHASE D 定向验证：Conversation 数据模型集成 2 passed，数据库/Alembic v4 3 passed；全量回归中一次旧 schema v3 断言已同步到 v4 后重新运行。最终命令与退出结果记录在阶段报告。

- PHASE C Legacy Product Cleanup 已完成：任务记录支持单删、批删、最近删除、恢复与受限永久删除；删除路径只修改应用数据库，运行中/待恢复任务被阻止，已有 plan/journal/Undo 安全依赖的任务不能永久删除。模板/自动规则页面、导航、API、服务与新任务写入已退出运行时，新建整理统一为 `auto_plan + user_instructions` 的一次性 AI 流程。旧模板表与 snapshot 字段仅作历史只读兼容，schema v3 升级前自动备份并补齐缺失模板快照。详见 [legacy-product-cleanup](artifacts/reports/legacy-product-cleanup.md)。
- PHASE C 最终验证：`.\backend\.venv\Scripts\python.exe scripts\verify.py all` 退出 0；后端分组为 7、92、16、19、15、10 passed，前端 20 passed，typecheck/build 退出 0；`test_ai_only_end_to_end.py` 在临时目录完成 Planner → Classifier → review → compile → approve → execute。既有 Windows reparse 临时目录清理 warning 与第三方 deprecation/decompression warning 不影响结果。
- PHASE A 稳定基线确认已完成：当前 AI-only 主链、DeepSeek Vision 证据、安全执行/恢复/undo、模板/任务/UI 现状与 Conversation Agent 最小切入点已记录在 [conversation-agent-baseline](artifacts/reports/conversation-agent-baseline.md)。
- PHASE B GitHub 参考研究已完成：已按固定 commit 检查 `joshuasoup/file-organizer`、`Venere-Labs/ragfs`、`tursodatabase/agentfs`、`BorisBesky/file-organizer-desktop` 与 `run-llama/file-organizer` 的 Agent、tools、持久化、文件操作、undo、index/provider/UI、测试和实际许可证文件；只吸收工具边界、审计、状态持久化、UX 和语义缓存思想，未复制代码。详见 [GITHUB_REFERENCE_ANALYSIS](docs/GITHUB_REFERENCE_ANALYSIS.md)。
- 本轮基线验证：`.\backend\.venv\Scripts\python.exe scripts\verify.py all` 退出 0；后端所有分组通过，前端 16 passed，typecheck/build 退出 0。仅有既有第三方 warning 与 Windows reparse 临时目录清理 warning。
- Git 恢复点：`main` / `01dc2f7b7179a5de189abc64c1794cf5126b7517`，但 AI-only/Vision 收口仍位于大量未提交改动中；该 commit 不能单独代表当前工作树基线。本轮没有提交、重置或覆盖既有改动。
- 按用户要求，本阶段在 PHASE C 后停止；未实现 Conversation schema、Chat UI、Agent Orchestrator、Tool Calling 或对话记忆。下一阶段只能在收到新指令后开始。

## AI-only 核心重构

- 当前阶段：AI-only PHASE 02～09 已通过；PHASE 10 已完成真实 DeepSeek 文本语义分类、vision probe、项目 JPG 视觉描述与图片 JSON mode 冒烟，完整可见桌面闭环和语义质量评测仍待补证；PHASE 11/12 的本地模型、可见桌面、安装器与签名为外部阻塞。
- 重构前审计结论：当时默认 UI 强制 `template + universal.types`，`auto_plan`/`fixed_categories` 没有 taxonomy 创建实现；RuleEngine、`classify_universal_types` 与 plan compiler 的 `TYPE_CATEGORIES` 会绕过 AI。上述运行时问题已由 PHASE 02～09 修复，历史根因详见 [AI_ONLY_REFACTOR_AUDIT](artifacts/reports/AI_ONLY_REFACTOR_AUDIT.md)。
- 初始基线证据：后端 121 passed（2 warnings）；前端 12 passed；TypeScript typecheck 退出 0；安全计划 API 定向回归 2 passed。当前 Conversation Agent 基线验证结果见本页上方与 [conversation-agent-baseline](artifacts/reports/conversation-agent-baseline.md)。
- 执行错误：当前源码的 approve → execute → undo 定向测试通过，旧截图错误未复现；PHASE 8 已完成结构化错误 code 与 plan basis/approval revision 重构。
- 外部阻塞：真实 DeepSeek 文本和单图视觉请求已补证，但尚无应用内可见桌面完整闭环、视觉/语义质量评测、本地 Qwen 服务与完整桌面人工验收证据；不得用单次冒烟或 fake adapter 结果替代完整验收。
- PHASE 2 结果：运行时 RuleEngine/规则 API/UI、`classification_mode`、`classify_universal_types` 与 plan compiler 模态 fallback 已删除；阶段测试后端 10 passed、前端 12 passed、typecheck 退出 0。详见 [ai-only-phase-02](artifacts/reports/ai-only-phase-02.md)。
- PHASE 3 结果：FileProfile 文件上下文、解析状态/警告及缓存重绑定已统一；解析/模型测试 19 passed、前端 12 passed、typecheck 退出 0。详见 [ai-only-phase-03](artifacts/reports/ai-only-phase-03.md)。
- PHASE 4 结果：text/json/vision capability gate 与受控图片 derivative 出站链路已接入；模型/分类测试 16 passed、前端 12 passed、typecheck 退出 0。详见 [ai-only-phase-04](artifacts/reports/ai-only-phase-04.md)。
- PHASE 5 结果：统一 AI Taxonomy Planner 已覆盖 auto_plan/template/fixed_categories，阶段测试后端 12 passed、前端 12 passed、typecheck 退出 0。详见 [ai-only-phase-05](artifacts/reports/ai-only-phase-05.md)。
- PHASE 6 结果：批量 AI 分类、视觉描述证据、批次审计与分类完成状态已接入；新增同扩展名文档和全 JPG 语义分类测试，2 passed；相关模型/规划回归 20 passed。详见 [ai-only-phase-06](artifacts/reports/ai-only-phase-06.md)。
- PHASE 7 结果：模板详情/使用/复制编辑、新任务三种 AI 模式、显式内容授权、分类树编辑和 AI 事件进度已接入；后端阶段测试 15 passed，前端 13 passed，typecheck/build 退出 0。详见 [ai-only-phase-07](artifacts/reports/ai-only-phase-07.md)。
- PHASE 8 结果：计划 basis revision、批准 revision、hash/状态复核、数据库 v2 迁移和结构化 UI 错误已完成；临时目录执行/撤销和旧计划失效测试通过，后端定向 20 passed，前端 13 passed，typecheck 退出 0。详见 [ai-only-phase-08](artifacts/reports/ai-only-phase-08.md)。
- PHASE 9 结果：AI-only 全量回归 133 passed；前端 14 passed/typecheck 退出 0；10 文件完整临时目录语义分类执行闭环、模板真实点击和 SOURCE_CHANGED 回归通过。详见 [ai-only-phase-09](artifacts/reports/ai-only-phase-09.md)。
- PHASE 10：使用用户明确授权的一次性 Key，经项目 `DeepSeekAdapter` 对两个同扩展名合成文本发起一次真实请求；`deepseek-chat` 正确返回网络/操作系统类别并通过受限 JSON 契约校验，169 input + 71 output tokens，退出 0。完整应用/视觉联调仍待补证。PHASE 11：本地 8000/11434/1234 均未监听。详见 [ai-only-phase-10](artifacts/reports/ai-only-phase-10.md) 与 [ai-only-phase-11](artifacts/reports/ai-only-phase-11.md)。
- DeepSeek vision probe 修复：根因是硬编码 1×1 PNG 的 IDAT 校验和损坏；已改为 Pillow 动态生成并回读验证的 64×64 PNG。`deepseek-flash` 真实 text/json/vision probe 全部 supported，重建服务实例后 `vision_verified=true` 仍持久；项目测试 JPG 已获得并写入 `visual_description` evidence，真实图片 JSON mode 同样通过。全量后端 136 passed，前端 16 passed/typecheck/build 退出 0；Windows onedir/portable 已重建，EXE SHA-256 `54bf1c954317b47f0369e667c9c41de3d14971f5a78fa656d0f043172f52be50`。详见 [deepseek-vision-probe-fix](artifacts/reports/deepseek-vision-probe-fix.md)。
- PHASE 12：Windows onedir/portable、冻结诊断与 worker 已重建通过；可见桌面人工验收、Inno 安装器、签名与干净机矩阵仍为外部阻塞。详见 [ai-only-phase-12](artifacts/reports/ai-only-phase-12.md)。
- 核心结论与证据汇总：[CORE_AI_ONLY_REFACTOR_REPORT](artifacts/reports/CORE_AI_ONLY_REFACTOR_REPORT.md)。

**阶段 01～09 的源码、安全闭环、执行器、本地解析、分类、双模型隐私适配、完整界面、恢复、发布前验收与 Windows onedir/portable 已实现；真实 DeepSeek 文本语义分类冒烟已通过，完整模型质量评测、ffmpeg/ASR、Inno 安装器与干净 Windows 发行矩阵仍有外部补证项。**

| 阶段 | 内容 | 状态 | 验收报告 |
|---|---|---|---|
| 01 | 桌面骨架与只读扫描闭环 | BLOCKED_EXTERNAL（自动化通过，DT01待人工桌面补证） | [phase-01](artifacts/reports/phase-01.md) |
| 02 | 安全执行器、日志、复制、移动、撤销 | BLOCKED_EXTERNAL（核心通过；卷断开/云占位待专用环境） | [phase-02](artifacts/reports/phase-02.md) |
| 03 | 多模态本地解析与资源管理 | BLOCKED_EXTERNAL（核心与OCR通过；ffmpeg/ASR待组件） | [phase-03](artifacts/reports/phase-03.md) |
| 04 | 模板、规则、目录规划与分类契约 | PASSED | [phase-04](artifacts/reports/phase-04.md) |
| 05 | DeepSeek／Qwen 模型适配、隐私与预算 | BLOCKED_EXTERNAL（AI04～AI12通过；AI01～AI03待用户服务） | [phase-05](artifacts/reports/phase-05.md) |
| 06 | 全页面与审阅交互集成 | BLOCKED_EXTERNAL（UI01～UI10自动化／浏览器通过；pywebview待人工补证） | [phase-06](artifacts/reports/phase-06.md) |
| 07 | 任务恢复、缓存、纠错、完整工作流 | PASSED | [phase-07](artifacts/reports/phase-07.md) |
| 08 | 质量验证、安全、性能与真实模型评测 | BLOCKED_EXTERNAL（自动化/性能通过；真实模型与桌面等待外部条件） | [phase-08](artifacts/reports/phase-08.md) |
| 09 | Windows 打包、安装、离线资源与交付 | BLOCKED_EXTERNAL（onedir/portable/原生窗口通过；Inno/签名/干净机待外部条件） | [phase-09](artifacts/reports/phase-09.md) |

## 执行者后续维护格式

每次更新写明当前阶段、完成的验收项、失败项、外部阻塞、最后一次测试命令与退出结果、下一项可执行工作。阶段可以是 IN_PROGRESS、PASSED、BLOCKED_EXTERNAL、FAILED；不能为了显示完成而把外部联调标成 PASSED。

## 当前恢复点

- 当前阶段：PHASE M UI Deep Polish 界面代码已交付（2026-09-24）；三栏视觉系统、输入/引用交互、文件窗口化、统一弹窗和设置/历史页已更新。前端 37 tests、后端 176 tests 通过；最新 typecheck/build、独立桌面构建与冻结诊断 exit 0，24 张截图已保存。原生 DPI/窗口人工验收、1600/1920 补测及既有能力限制仍保留，不能标记全阶段验收通过。详见 [ui-deep-polish](artifacts/reports/ui-deep-polish.md)。版本保持 dev，本次按用户要求收口，不进入下一阶段。
- PHASE L 最近通过：后端 176 passed / 2 warnings，前端 34 passed、typecheck/build exit 0，schema v10 / Alembic 0010 与运行时 OpenAPI 已更新；20 文件真实磁盘 smoke 和真实浏览器 QA 已完成。
- 最近通过：维护回归后端全量 121 passed、前端 11 passed/typecheck/build、`python scripts/verify.py all` 退出 0；计划批准支持同 ID/同 hash 幂等重试，模型连接支持确认删除并从可用列表移除；Windows onedir 已重建为 434 文件/301,371,902 bytes，冻结诊断与中文 worker exit 0。详见 [maintenance-2026-09-14](artifacts/reports/maintenance-2026-09-14.md)。
- 已交付：`artifacts/release/Guixu-0.1.0/`、`Guixu-portable-x64-0.1.0.zip`、SBOM、SHA256SUMS、锁文件、迁移、源码、脚本、用户/开发手册和九份阶段报告。
- 外部阻塞：Inno Setup/安装器、代码签名、无 Python/Node 干净机安装升级卸载、高 DPI/多系统；DeepSeek 完整应用/视觉链路、本地 Qwen、公平语义评测、ffmpeg/ffprobe/ASR、物理卷断开／云占位；生产 `direct_move` 仍关闭。
- 恢复动作：在受控构建机安装 Inno Setup 6 后运行 `.\scripts\package-windows.ps1`；按 `artifacts/reports/release-readiness.md` 的阻塞清单补证，全部通过前不得改为 beta/release。
