# 项目状态

版本：0.1.0 dev（PHASE H 多轮整理 V1 已完成，禁止发布 0.2.0）。更新时间：2026-09-21。

## Conversation Agent 转型准备

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

- 当前阶段：九阶段实现已收口；版本保持 dev，发布门等待外部补证。
- 最近通过：维护回归后端全量 121 passed、前端 11 passed/typecheck/build、`python scripts/verify.py all` 退出 0；计划批准支持同 ID/同 hash 幂等重试，模型连接支持确认删除并从可用列表移除；Windows onedir 已重建为 434 文件/301,371,902 bytes，冻结诊断与中文 worker exit 0。详见 [maintenance-2026-09-14](artifacts/reports/maintenance-2026-09-14.md)。
- 已交付：`artifacts/release/Guixu-0.1.0/`、`Guixu-portable-x64-0.1.0.zip`、SBOM、SHA256SUMS、锁文件、迁移、源码、脚本、用户/开发手册和九份阶段报告。
- 外部阻塞：Inno Setup/安装器、代码签名、无 Python/Node 干净机安装升级卸载、高 DPI/多系统；DeepSeek 完整应用/视觉链路、本地 Qwen、公平语义评测、ffmpeg/ffprobe/ASR、物理卷断开／云占位；生产 `direct_move` 仍关闭。
- 恢复动作：在受控构建机安装 Inno Setup 6 后运行 `.\scripts\package-windows.ps1`；按 `artifacts/reports/release-readiness.md` 的阻塞清单补证，全部通过前不得改为 beta/release。
