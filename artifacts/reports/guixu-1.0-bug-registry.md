# Guixu 1.0 Bug Registry

更新时间：2026-09-30
Feature Freeze：ACTIVE

## 统计

| Severity | Open | Fixed | Accepted |
|---|---:|---:|---:|
| P0 | 0 | 2 | 0 |
| P1 | 0 | 8 | 0 |
| P2 | 0 | 4 | 0 |
| P3 | 0 | 1 | 0 |

> “Open P0 = 0”只表示当前已登记缺陷；在安全和 crash matrix 完成前，不代表最终 P0 gate 已通过。

> **2026-09-30 更正。** 上表此前把 P1 记为 open 1、P2 记为 open 1、P3 记为 open 1，与正文各条目的 `Status` 字段不一致——P1-005 实为 FIXED，P2-003 与 P3-001 也已在本轮完成并有回归覆盖。统计表现已按各条 `Status` 重新汇总。P0 计数由 1 增至 2：新增的 P0-002 是本轮从真实历史 schema 升级测试中挖出的迁移缺陷，若未在公开前发现，**任何从 0.1.0 升级的用户都会在首次启动时直接失败**。P1 计数由 7 增至 8：新增 P1-007 发行版本号漂移。

## P1-007 — 发行版本号在五处各写一份，改版本时漏改三处，产物名、SBOM 与校验清单全部错位

- **Severity:** P1
- **Area:** `scripts/package-windows.ps1` / `packaging/Guixu.spec` / `scripts/generate_release_metadata.py` / 版本管理
- **Expected:** 发行产物的目录名、压缩包名、SBOM 里的版本字段与 `pyproject.toml` 声明的版本一致；`SHA256SUMS.txt` 覆盖整个应用文件树。升版本只改一处。
- **Actual:** 版本字面量散落五处。本轮从 0.1.0 提到 0.9.0 时改了 `pyproject.toml`、`__init__.py`、`openapi-runtime.json`、`frontend/package.json`、`Guixu.iss`，**漏了三处**：
  1. `package-windows.ps1:56,86` → 产物目录与压缩包仍叫 `Guixu-0.1.0`
  2. `Guixu.spec:66` → PyInstaller COLLECT 名仍叫 `Guixu-0.1.0`
  3. `generate_release_metadata.py:63,70` → **SBOM 写入 `"version": "0.1.0"`**（这个字段随发行包一起分发），且第 70 行去找 `Guixu-0.1.0` 目录
- **第 3 处最严重，因为它静默降级。** 第 70 行原为 `if onedir.is_dir():`——目录名对不上时**不报错，直接跳过**，于是 `SHA256SUMS.txt` 只剩压缩包与 SBOM 两行。实测：修复前 2 行，修复后 437 行。一个看起来有校验清单、实际不校验 app 内任何文件的发行物，比没有清单更危险。
- **为何没被发现：** **构建成功，exit 0。** 脚本只对「命令失败」设门禁，不校验「产物名字对不对」。这与 P1-002（打包脚本吞掉前端构建失败）是同一类缺陷的两面——那次是失败被吞掉，这次是成功但产物是错的，两者都不让 exit code 变红。
- **Fix:** 五处字面量全部改为读 `backend/pyproject.toml`（唯一声明源）：`Guixu.spec` 新增 `_version()`；`package-windows.ps1` 读出 `$declaredVersion` 并在首行 `Write-Output "Release version: ..."`；`generate_release_metadata.py` 新增 `declared_version()`。三处读不到版本时**抛错，不回退默认值**。`generate_release_metadata.py` 的目录缺失由静默 `if` 改为无条件 `raise SystemExit`。
- **为何定为 P1 而非 P2：** 用户从 GitHub 下载后看到的目录名、包内 SBOM 版本都不对，无法判断装的是哪个版本，事故排查会被版本错位带偏；且校验清单静默降级直接使 B07 门禁失效。
- **Verification:** 重新打包 exit 0，日志首行 `Release version: 0.9.0`，产物 `Guixu-0.9.0/` 与 `Guixu-portable-x64-0.9.0.zip`；重跑元数据生成得 `SHA256SUMS.txt` 437 行、SBOM `version: 0.9.0`；清单中 zip 哈希 `42848920…` 与 `sha256sum` 实测一致；把 `--release-directory` 指向应用目录内部时脚本报 `application directory not found: …`，守卫确认生效。
- **Status:** FIXED（2026-09-30）。
- **教训一：** 同一事实的多个副本，只要有一处能独立改动而不触发任何检查，就迟早漂移。**升版本必须有一条「从产物名反查声明值」的断言。**
- **教训二：** `if x.is_dir():` 包住一段**应当必须执行**的逻辑，是把缺失伪装成成功。缺失应当是硬错误。
- **教训三（本轮自身失误）：** 一次「重建」其实没跑——`rm -rf` 因文件占用失败，而我用 `&&` 串联导致 PowerShell 被短路跳过；后台任务 wrapper 报的 exit 0 来自 wrapper 而非命令，我据此误判构建已完成并读到了旧产物。**判断后台任务是否真跑完，要看命令自己 echo 的退出码，不能信 wrapper 的。**

## P1-006 — 目录授权接受任意系统路径，`C:\Windows` 可被授权为整理根

- **Severity:** P1
- **Area:** `infrastructure/filesystem/grants.py` / 授权边界
- **Expected:** 按 `AGENTS.md`「不碰测试范围外的个人目录」，系统目录与整卷不得被授权为源或目标根；授权必须在**入口**拒绝，而不是等到第一次移动时。
- **Actual:** `canonicalize_directory` 只检查路径存在、是目录、且根本身不是 symlink/reparse point，**没有任何系统位置检查**。实测 `C:\Windows`、`C:\Windows\System32`、`C:\Program Files`、`C:\Program Files (x86)`、`C:\ProgramData`、`C:\Users\Public` 以及任意盘符根 `C:\` `D:\` 全部被接受为 source 授权。桌面桥接的路径选择器会限制用户手点，但 typed-grant API 接受任意字符串——提示注入、缺陷前端或误输入都能拿到授权。文件整理器拿到根目录后终会把里面的东西移走。
- **Fix:** 新增 `_protected_locations()`，分两类返回：系统目录（`SystemRoot`、`Program Files`、`Program Files (x86)`、`ProgramData`、`$Recycle.Bin`、`System Volume Information`、`Recovery`、`C:\Users\Public`）封禁**整棵子树**；盘符根、`C:\Users`、用户 profile 根**只封禁其本身**。这个区分是必要的——封禁 profile 子树会连带干掉 Documents、Downloads、Pictures 和所有项目目录，恰好废掉产品本身。`_is_protected` 用 `os.path.normcase` 比较以抵抗大小写（`C:/WINDOWS` 否则会绕过 `C:/Windows`），并显式要求分隔符以避免 `C:\WindowsOld` 被前缀误判。错误码 `PROTECTED_LOCATION_BLOCKED`，API 返回 422。
- **为何此前未被发现：** S02 矩阵里「系统路径」这一项从未有过断言；已有的越权测试只覆盖了「另一个 Conversation 的文件 ID」。
- **Regression Test:** 新增 `backend/tests/safety/test_protected_locations.py`（15 项）。修复**之前**直接探测过同一组路径，全部被接受（`接受 'C:\Windows' -> C:\Windows` 等），而测试断言它们必须被拒绝，因此测试在修复前必然失败。注：未采用「回退修复再跑测试」的方式验证，因为临时移除该防护被安全分类器拦截；此处证据是修复前的直接探测输出，不是推断。
- **Status:** FIXED（2026-09-30）。后端全量 270 passed。

## P0-002 — 从任何真实旧库升级都会失败（`cannot commit - no transaction is active`）

- **Severity:** P0
- **Area:** Alembic migration 0012 / 升级路径
- **Expected:** 已安装 0.1.0 的用户升级到新版本后首次启动，数据库自动迁移到 head，会话、文件、方案、审计记录全部保留。
- **Actual:** 迁移 `0012_chat_call_audit` 在关闭外键前执行了一条裸 `bind.exec_driver_sql("COMMIT")`。pysqlite 在**没有活动事务**时 `commit()` 抛 `OperationalError: cannot commit - no transaction is active`（而 `rollback()` 是无害的 no-op，两者不对称）。alembic 不保证此处有事务：前面几条都是 PRAGMA 和 SELECT，pysqlite 的 legacy autocommit 模式不为它们开事务。实测三个真实历史 schema（2026-09-14 / 09-21 / 09-25）升级**全部在 0012 失败**。
- **为什么一直没被发现：** 新装机器走的是 0012 第 45 行的提前返回分支（`0001` 直接执行当前 `contracts/database.sql`，新库已带 `conversation_id` 与 `'chat'`），**永远走不到那行 COMMIT**。而此前所有迁移测试都从当前 schema 建库，同样从不进入旧库重建路径。只有真实升级才会执行它。
- **Fix:** 抽出 `_commit(driver)`，仅在 `driver.in_transaction` 为真时提交；`try` 内的成功提交与 `finally` 里的收尾提交都走它。重建的外键挂起与 `PRAGMA foreign_key_check` 校验逻辑不变。
- **Regression Test:** 新增 `backend/tests/contract/test_legacy_schema_upgrade.py`（6 项）。fixture 是从 git 历史取出的**逐字真实 schema**——`git show 4e2700b/4aeb7cd/8db48ab:contracts/database.sql`——不是测试内构造。测试断言升级到 head、种子数据逐字段留存、`classifications.model_call_id` 未被 `DROP TABLE` 的 `ON DELETE SET NULL` 清空、`'chat'` purpose 可用、`foreign_key_check` 为空，并能用应用自身的 `Database` 重新打开。**已验证测试有牙齿**：临时回退修复后 6 项全红，恢复后全绿。
- **Status:** FIXED（2026-09-30）。后端全量 255 passed。
- **教训：** 「从当前 schema 建库」的迁移测试结构性地覆盖不到旧库重建分支。升级测试的 fixture 必须来自真实历史产物。

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
- **Status:** FIXED（2026-09-30）。`ModelGateway.conversation_chat` 现通过 `_record_chat_attempts` 写入共享 ledger：成功与失败都记，含 `purpose='chat'`、可空 `task_id`、指向会话的 `conversation_id`、token、时延与错误码；重试按 attempt 逐条落账，失败不丢记录。迁移 `0012_chat_call_audit` 为 `model_calls` 增加 `chat` purpose 与可空 `conversation_id`（`ON DELETE SET NULL`）。回归 `test_discussion_calls_are_audited_and_stay_out_of_task_budget` 断言调用被记账且 `task_id IS NOT NULL` 的行数为 0——讨论发生在 Task 创建之前，不会污染按 Task 的预算口径。冻结包原生复测仍属独立的发行验收项。

## P3-001 — AI 聊天回复直接显示 Markdown 标记

- **Severity:** P3
- **Area:** Conversation message rendering
- **Evidence:** 本机冻结包真实 DeepSeek 回复中的 `**分类维度**`、列表标记按原样显示。`ConversationMessage.vue` 用 `<p>{{ message.content }}</p>` 将整段回复作为纯文本呈现。
- **Impact:** 多段列表和强调文字难读；不会导致文件操作错误。
- **Fix:** 新增 `features/conversations/markdown.ts` 手写受限渲染（不引入第三方 Markdown 依赖），`ConversationMessage.vue` 改用 `MessageContent.vue` 渲染，复制按钮仍取原始文本。刻意不支持标题与内联 HTML；链接只允许 http/https，其余协议不产生 `<a>`。
- **Regression Test:** `markdown.test.ts` 9 项 + `message-markdown.test.ts` 5 项，含「原始 HTML 保留为字面字符」「敌意回复不创建任何元素」「绝不产生 `javascript:` 或 `data:` 链接」「文件名中的下划线不被当成强调」；前端全量 67 passed。
- **Status:** FIXED（2026-09-30）。打包版原生观感复测属独立的 UI 验收项（U01–U04）。

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

> **2026-09-30 更正：本条证据中的数字撤回。** 上面引用的 attach/reconcile 耗时是**单次采样**，其中「5000 文件 attach 1.298 秒、reconcile 3.409 秒」**不可复现**。把基准脚本重写为多次重复 + nearest-rank 分布后实测：attach p50 **3.1326s** / p95 7.1728s，reconcile p50 **.7341s** / p95 .8758s。即 attach 的真实 p50 比原记录高出一倍以上——原数字是一次走运的采样。
>
> 「从 32.73 秒降至 1.298 秒」的**定性结论仍然成立**（数量级改善是真实的），但**具体数字不再作为证据引用**。修正后的措辞是：attach 由 32.73 秒降至 p50 3.13s。
>
> 同时，reconcile 在本轮被单独发现并修复了一个更严重的问题：每轮对话都会对整个文件库重新计算 SHA-256，成本是 O(字节) 而非 O(文件数)。在基准的小文本 fixture（每个 33 字节）上这几乎看不出来，但在真实照片库（约 4MB/张）上相当于每条消息重读约 20GB。现已改为 `quick_same`（size + mtime_ns 未变即视为未重写）快速路径，并加了三条回归测试；由于执行器在每次移动前仍会重新哈希，被伪造的 mtime 无法绕过文件操作校验——见 `test_forged_mtime_still_fails_the_pre_move_identity_check`。
>
> 教训：**未经分布的单次计时不应写进验收矩阵或缺陷登记。** 基准脚本的 `method.caveat` 现已写明样本数低于 20 时 p95 退化为最大值。

## P2-004 — 目标路径被按盘上大小写静默改写，文件以占用者的大小写重新发布

- **Severity:** P2
- **Area:** Path policy / destination naming
- **Expected:** 授权目录内已存在 `photo.jpg` 时，指向 `Photo.jpg` 的方案应生成 `Photo (2).jpg`，保留用户原本的拼写。
- **Actual:** `path_policy.ensure_within` 对尚不存在的叶子调用 `Path.resolve()`。Windows 上该调用会按盘上大小写重写路径，于是 `Photo.jpg` 被折叠成 `photo.jpg`——与占用者同名，冲突检测随即认为目标已存在，用户文件最终以**占用者的大小写**发布。
- **Impact:** NTFS 上大小写不敏感，该差异不可见，因此长期未被发现。但在**大小写保留**的目标卷（网络共享、exFAT 卡、同步目录）上这是一次真实的重命名：用户看到的文件名被改成了另一个文件的名字。属数据完整性问题，不是显示问题。
- **Fix:** 包含性检查继续用解析后的形式（防止 junction 或 `..` 绕过授权边界），但**返回**词法绝对路径 `os.path.abspath(path)`，不做大小写规范化。`ensure_within` 之上仍有设备/UNC 前缀拒绝。
- **Regression Test:** `test_s05_case_only_difference_target_is_never_clobbered`（仅大小写不同的目标生成 `Photo (2).jpg` 而非覆盖）、`test_s05_case_only_collision_appearing_after_approval_keeps_both_files`、`test_s05_batch_of_case_differing_names_allocates_distinct_targets`。
- **Status:** FIXED（2026-09-30）。限制：本机只有 NTFS 卷，大小写保留卷上的端到端行为无法在此验证。

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
