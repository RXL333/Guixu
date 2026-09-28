# Guixu 1.0 Bug Registry

更新时间：2026-09-28
Feature Freeze：ACTIVE

## 统计

| Severity | Open | Fixed | Accepted |
|---|---:|---:|---:|
| P0 | 0 | 1 | 0 |
| P1 | 1 | 5 | 0 |
| P2 | 1 | 2 | 0 |
| P3 | 1 | 0 | 0 |

> “Open P0 = 0”只表示当前已登记缺陷；在安全和 crash matrix 完成前，不代表最终 P0 gate 已通过。

## P1-005 — 本地千问图片整理无法生成预览

- **Severity:** P1
- **Area:** packaged app / local Qwen vision classification
- **Reproduction:** 使用本机 `0.1.0` 冻结包、隔离数据目录，通过原生文件夹选择器新建三张合成 JPG 的会话；将 `qwen3-vl:4b-instruct` 连接配置为 `http://127.0.0.1:11434/v1`，能力测试中“文本/视觉”均已验证；输入“请按照图片内容分类，分类目录名称全部使用中文。”并点击“生成整理方案”。
- **Actual:** UI 显示“AI 返回的整理结果未通过安全校验”。持久 `task_events` 有 `AI_CLASSIFY_BATCH_FAILED`、`code=VISION_DESCRIPTION_MISSING`、`file_count=3`；模型调用账本显示 planning/classification/repair 传输均为 `ok`，但视觉描述未满足分类契约。PlanVersion 和文件操作均为 0，安全拒绝生效。这个结果不证明是模型、提示词还是响应解析单独造成，需进一步检查脱敏响应结构。
- **Expected:** 已标记视觉可用的本地模型能完成三图的规划/视觉证据/分类并生成可审查预览；若不满足完整契约，设置页应明确显示能力限制，失败页给出具体错误码及恢复指引。
- **Fix proposal:** 为本地 Qwen 加三图真实契约验收，抓取仅含字段名/缺失状态的诊断；修复模型提示或有界修复流程，并让能力测试覆盖非空 `visual_description`。不得以文件名或臆测结果填充视觉证据。确认后重建同一便携包并复测。
- **Evidence:** `artifacts/reports/release-audit-2026-09-28.md`；本轮隔离数据库 `artifacts/test-workspaces/release-qa-safe-2026-09-27/data/app.sqlite3`。
- **Status:** FIXED_IN_SOURCE_AND_REBUILT_PACKAGE（2026-09-28）。本机真实 Qwen 三图首次预览、逐文件建议展示 API、人工确认后生成 v2 移动方案通过；后端全量 228 passed、前端 53 passed。先前打包版原生首次预览通过，新包已覆盖并完成冻结诊断。最终打包版原生“建议确认→批准执行”仍是独立的发行验收缺口，整体未达到上线条件。详见 `phase-n-local-qwen-vision-fix.md`。
- **2026-09-28 修复进展:** 源码真实 Ollama 三张合成 JPG 首轮预览连续三次通过；针对重复类别 ID、层级限制、视觉描述缺失、单图冗余字段缺失和虚构证据引用加入约束及有界修复。后端 226 passed，前端 52 passed。同名便携包已重建并通过冻结诊断；原生打包版完整视觉整理尚未复测，故本项仍保持 OPEN。证据：`artifacts/reports/phase-n-local-qwen-vision-fix.md`。

## P2-003 — 普通聊天模型调用未进入审计记录

- **Severity:** P2
- **Area:** Conversation chat / model call audit
- **Reproduction:** 在 `0.1.0` 冻结包、隔离测试数据库中复用已验证 DeepSeek 档案，连续两轮普通聊天。AI 返回两条回复、会话保存 4 条消息；数据库 `model_calls=0`，PlanVersion、ExecutionRound、Operation 均为 0。
- **Cause:** `/api/v1/conversations/{id}/chat` 直接调用 `DeepSeekAdapter.chat`；计划和分类走的 `ModelGateway._call` 才持久化 `model_calls`。当前 `model_calls.purpose` CHECK 也没有 `chat`，且聊天发生在 Task 创建前。
- **Impact:** 普通聊天费用/用量、延迟、失败次数无法在模型调用审计中追踪。不能据此声称预算与调用日志已覆盖聊天。
- **Fix proposal:** 为 Conversation 级聊天增加不保存提示词/图片内容的调用 ledger（或向 `model_calls` 增加 `chat` purpose 与可空 Conversation 关联），按成功/失败写入模型、token、时延、错误码，并加迁移、API/数据库回归和冻结包复测。
- **Status:** OPEN（2026-09-26）。

## P3-001 — AI 聊天回复直接显示 Markdown 标记

- **Severity:** P3
- **Area:** Conversation message rendering
- **Evidence:** 本机冻结包真实 DeepSeek 回复中的 `**分类维度**`、列表标记按原样显示。`ConversationMessage.vue` 用 `<p>{{ message.content }}</p>` 将整段回复作为纯文本呈现。
- **Impact:** 多段列表和强调文字难读；不会导致文件操作错误。
- **Fix proposal:** 支持受限 Markdown 段落、列表、强调和代码，并对链接/HTML 严格清理，保留复制原文行为；加入恶意 HTML 不执行的前端测试。
- **Status:** OPEN（2026-09-26）。

## P0-001 — Conversation 文件引用 API 未校验活动授权目录

- **Severity:** P0
- **Area:** Authorization scope / ConversationFile API
- **Actual:** 仅凭 task file ID 可将其他授权目录中的文件附加到 Conversation，列表 API 随后会暴露其路径。
- **Fix:** 批量附加前，在同一事务中解析并验证全部文件均位于该 Conversation 当前活动 scope；任一越界则整批拒绝。API 返回 `409 REFERENCE_SCOPE_VIOLATION`。路径变化在提交前再次校验；拒绝 UNC/device path。
- **Regression Test:** `test_bulk_file_attachment_is_atomic_and_rejects_out_of_scope_ids` 与 `test_conversation_file_api_rejects_file_outside_authorized_folder`；加上文件引用和 crash-resume 定向集成共 `8 passed`。
- **Status:** FIXED（2026-09-24；仍需继续完成独立的全套授权/安全矩阵）。

## P1-003 — 真实 DeepSeek 首轮 v1→v2 组合链曾出现模型契约失败

- **Severity:** P1
- **Area:** Model contract / first analysis / pre-execution replan
- **Reproduction:** 在隔离临时目录用 5 个合成 JPG 与当前启用的 DeepSeek profile 运行 `python scripts/run_phase_n_real_e2e.py`。
- **Expected:** 真实模型生成 v1，修改要求后得到 v2、diff，并可进入显式批准与执行。
- **Actual:** 初期真实请求曾在规划/分类 schema 校验停止。修复后，2026-09-24 真实隔离 5-JPG E2E 完整通过：v1→执行前修改→parent-linked v2→diff→审批前磁盘未变→批准执行→重启读取消息/方案/执行/文件关系；7 次 DeepSeek planning/classification/repair 调用均成功，`secret_recorded=false`。报告：`artifacts/reports/phase-n-real-deepseek-e2e.json`。旧脚本历史 URL 错误也已修正并由此次运行验证。
- **Fix:** 分类和规划各加入一次有界 repair；首次视觉分类允许无旧 evidence ID，但必须有视觉描述且不得伪造 ID，保存描述后再进入最终 ClassificationService 校验；图片批次限为 4，缓存描述无需重复生成。空类别结果改为一次带原始已授权证据的明确契约重问；缺少解释字段时用中性说明、空标签，并加入 `insufficient_evidence` 进入复核；首次/后续分析 API 和前端显示具体校验原因，不再误报“授权不足”。2026-09-24 真实 DeepSeek 5-JPG v1→v2→批准→执行→重启读取 E2E exit 0，P1-003 已关闭。
- **Release condition:** 已覆盖的 v1→v2→审批→执行→重启读取流程当前通过一次；重启后继续对话、Undo 和发行包仍是独立 release gate，不属于本缺陷的复现条件。
- **Status:** FIXED（2026-09-24，真实隔离 E2E 通过一次；更长组合流程仍需单独验收）。

## P1-004 — 执行前重规划失败可能损坏仍可见的 v1 工作状态

- **Severity:** P1
- **Area:** PlanVersion / Task transaction consistency
- **Reproduction:** 已有 FULL v1 时，调用 `FirstAnalysisService.revise_before_execution()`，让规划或分类中途失败。
- **Expected:** v1 仍是可执行的 current plan；未生成的 v2 不改变 core Task、taxonomy、plan 或 context。
- **Actual / code evidence:** 旧实现先持久写入 Task，再调用模型；taxonomy approve/compile 在 Conversation v2 创建前发生。故障注入证实分类失败后 Task revision 从 7 变为 9，旧 v1 无法按原 revision 安全批准。
- **Fix so far:** 现有 AgentTurn ledger 增加执行前重规划检查点；失败时恢复旧 Task/taxonomy/core plan/context/approval 状态，新记录只标记 superseded，不碰磁盘与 journal。启动时恢复被进程中断的尝试；v2 创建与检查点完成在同一事务。批准与执行在重规划运行期间被拒绝。
- **Regression Test:** `test_failed_pre_execution_replan_preserves_approvable_v1` 覆盖规划失败、分类失败、核心 Plan 编译后版本提交前失败；`test_interrupted_pre_execution_replan_restores_v1_on_restart` 覆盖重启补偿；v1→v2 正常路径同组通过。当前定向命令 5 passed。
- **Remaining release checks:** 并发交错与发行包恢复仍未验收，但核心旧 v1 状态损坏问题已通过失败/中断注入回归关闭；这些项目单独跟踪，不再作为已复现 P1。
- **Status:** FIXED（2026-09-24，5 个定向集成测试通过）。

## P2-001 — 5000 文件附加到 Conversation 耗时偏高

- **Severity:** P2
- **Area:** Large-directory performance
- **Evidence:** `scripts/run_phase_n_performance.py` 在本机隔离数据集重新测得 500/1000/5000 文件 attach 为 0.131/0.256/1.298 秒，reconcile 为 0.320/0.644/3.409 秒；SQLite integrity 均正常。
- **Fix:** 首次扫描复用已持久化的 file identity 快照；ConversationFile 使用批量插入/查询和一次性 scope 校验，避免逐文件重新哈希与重复数据库往返。5000 文件 attach 从 32.73 秒降至 1.298 秒。
- **Impact:** 后端 attach 瓶颈已修复；尚未测桌面 UI 帧率/列表渲染，不把后端结果外推为 UI 流畅度通过。
- **Regression Test:** `scripts/run_phase_n_performance.py`；文件引用/API scope 定向集成共 `8 passed`。
- **Status:** FIXED（2026-09-24；UI 规模性能仍是独立未测验收项）。

## P2-002 — 重启后视觉 evidence 重建导致分类缓存输入不匹配

- **Severity:** P2
- **Area:** Semantic Cache / AI Classifier
- **Expected:** 文件 fingerprint、taxonomy、model 与授权输入未变化时，重启后继续分类应复用视觉 evidence 与同一输入哈希的持久分类结果。
- **Actual:** 缓存恢复使用 evidence ledger 的随机行 ID、不同 origin 且缺少 `AI-vision` capability 标记；这些差异使输入哈希改变，原分类被忽略并再次请求模型。
- **Fix:** 按首次 `append_model_evidence` 规则重建稳定 evidence ID、来源与 capability 集合；分类前查精确输入缓存，对已完成文件跳过 provider 调用，并按原 file ID 顺序返回结果。
- **Regression Test:** `test_visual_classification_reuses_persisted_result_after_restart`；首次分析与 classification 定向回归 `25 passed`。
- **Status:** FIXED（2026-09-24）。

## P1-001 — 首次执行前修改要求不会生成 PlanVersion v2

- **Severity:** P1
- **Area:** Conversation / Plan Versioning
- **Description:** 首次分析生成 FULL v1 后，用户在第一次执行前继续修改整理要求，前端只保存 Message，不调用 replanning/refinement；后端现有 refinement 又要求 completed baseline ExecutionRound。
- **Reproduction:** 新建 Conversation → 首次分析得到 v1 → 输入“建筑单独分类，截图和文档照片分开”。
- **Expected:** 更新结构化 context，生成 parent=v1 的新 FULL PlanVersion v2，可查看 diff；磁盘保持不变。
- **Actual:** 只保存用户消息，显示“首次整理分析能力尚未接入当前工作区”，没有 v2。
- **Root Cause:** `store.appendMessage()` 仅在已有 completed round 时调用 refinement；`PostExecutionConversationService.prepare_refinement()` 只支持 post-execution baseline。
- **Fix:** 在首次 Task 上复用稳定 FileProfile/evidence，重新生成 taxonomy、classification 与 core Plan；创建 parent=v1 的不可变 FULL v2，并保留旧版本。不调用 FileOperationEngine。
- **Regression Test:** `test_first_plan_can_be_revised_to_v2_before_any_execution`；前端 `replans a proposed first plan before any execution`。
- **Status:** FIXED（2026-09-24）

## P1-002 — Windows 打包脚本可能吞掉前端构建失败

- **Severity:** P1
- **Area:** Packaging
- **Description:** `npm ci` 或 `npm run build` 失败时，PowerShell 脚本仍可能继续 PyInstaller 并最终 exit 0，导致旧 `frontend/dist` 被打进看似成功的新包。
- **Reproduction:** 让 `esbuild.exe` 被 Vite 占用后运行 `package-windows.ps1 -SkipTests -SkipInstaller`；审计中实际观察到 npm EPERM、`vue-tsc` not recognized，随后 PyInstaller 继续并成功退出。
- **Expected:** 任一 native build command 非零立即停止，不能产生/宣称新 release。
- **Actual:** `$ErrorActionPreference='Stop'` 未自动把 native `$LASTEXITCODE` 转成终止错误。
- **Root Cause:** 脚本没有对 `npm.cmd ci`、`npm.cmd run build`、`uv run pyinstaller` 等 native command 显式检查退出码。
- **Fix:** 对 npm、verify、PyInstaller、release metadata 全部增加 `$LASTEXITCODE` gate；同时改用 `RuntimeInformation.IsOSPlatform` 兼容 Windows PowerShell 5。
- **Regression Test:** 受控覆盖 `npm.cmd` 返回 7，脚本立即抛出 `npm ci failed with exit code 7`，外层进程 exit 1，未进入后续构建。
- **Status:** FIXED（2026-09-24）

## P1-000 — 首轮 FULL 方案无执行入口

- **Severity:** P1
- **Area:** Conversation UI / Execution
- **Description:** 首轮 FULL Plan 没有 baseline，前端隐藏执行按钮，后端也拒绝无 baseline 的 execute。
- **Reproduction:** 首次分析后查看 Plan v1。
- **Expected:** 明确 UI 批准后可由安全执行器执行。
- **Actual:** 只能预览。
- **Root Cause:** 把 post-execution DELTA 的 baseline 条件错误应用到首轮 FULL。
- **Fix:** commit `b6ef4ed`；首轮显示“确认并开始整理”，FULL 无 baseline 可执行，DELTA 仍要求 baseline。
- **Regression Test:** `test_first_plan_can_be_explicitly_approved_and_executed`。
- **Status:** FIXED
