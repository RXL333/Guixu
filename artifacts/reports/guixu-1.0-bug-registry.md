# Guixu 1.0 Bug Registry

更新时间：2026-09-24
Feature Freeze：ACTIVE

## 统计

| Severity | Open | Fixed | Accepted |
|---|---:|---:|---:|
| P0 | 0 | 1 | 0 |
| P1 | 0 | 5 | 0 |
| P2 | 0 | 2 | 0 |
| P3 | 0 | 0 | 0 |

> “Open P0 = 0”只表示当前已登记缺陷；在安全和 crash matrix 完成前，不代表最终 P0 gate 已通过。

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
