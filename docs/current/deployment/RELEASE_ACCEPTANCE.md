# Guixu 1.0 Release Acceptance

2026-09-28 本地千问阻断修复补充：`qwen3-vl:4b-instruct` 经本机 Ollama 对三张隔离合成 JPG 完成首次预览；人工确认一项 AI 建议后生成 v2 `move` 方案，源图不变、执行操作为 0。后端 228 passed、前端 53 passed，同名便携包覆盖重建并通过冻结诊断。最终打包版原生确认建议与批准执行尚未复测；整体 **NOT RELEASE READY**。见 `artifacts/reports/phase-n-local-qwen-vision-fix.md`。

版本目标：`1.0.0`
候选阶段：Feature Freeze / pre-RC1
基线 commit：`b6ef4ed7dba24519bd7d4f03c4e042dc1f499eea`
最后更新：2026-09-24

2026-09-28 追加复核：当前工作树后端完整 222 passed、前端 52 passed，生产构建、便携包已知密钥签名扫描、437/437 哈希和 ZIP 完整性通过。真实 DeepSeek 源码集成首次整理与执行后 DELTA 隔离 smoke 均 exit 0；本机打包版新建会话、三图列表/预览、本地千问两轮聊天及重启恢复通过。但本地千问三张合成 JPG 的真实整理因 `VISION_DESCRIPTION_MISSING` 停止，登记 open P1-005；没有生成 Plan 或文件操作。5,001 项 attach 测得 12.424 s 和 3.922 s，波动尚无 p95。发行态完整链、干净 Windows、安装器、多 DPI、签名/许可证仍缺验收。**NOT RELEASE READY**。详见 `artifacts/reports/release-audit-2026-09-28.md`。

2026-09-26 复核补充：当前工作树后端全量 218 passed、前端 47 passed/typecheck/build 通过；真实 DeepSeek 5 张合成 JPG v1→v2→审批→执行→重启读取再次通过；本机 `0.1.0` 冻结包新建会话、文件列表、图片预览及重启读取通过。冻结包真实 DeepSeek 普通聊天两轮成功，且未自动生成方案或操作文件；同时发现聊天调用未写入 `model_calls`（P2-003）。已知签名扫描和 437 项 SHA-256 清单通过。安装器、干净 Windows、发行包真实模型整理全链及下表部分矩阵仍缺证据，结论保持 **NOT RELEASE READY**。逐项命令、退出结果和限制见 `artifacts/reports/release-audit-2026-09-26.md`。

## 状态定义

- `NOT_TESTED`：当前基线尚未运行或证据不足。
- `PASS`：在注明的基线和环境上有直接证据。
- `FAIL`：已复现不满足验收条件。
- `BLOCKED`：缺少外部环境、凭据、工具或硬件，无法在当前环境完成。
- `PARTIAL`：有直接证据通过了明确子场景，但该验收项包含的其他范围尚未验证。
- `SKIPPED_WITH_REASON`：不属于 1.0 承诺范围并写明原因。

Fake Model、真实 DeepSeek、真实文件系统、手工 UI、packaged application 与 clean machine 证据必须分别记录，不能互相替代。

## Release Gate

| Gate | 状态 | 当前证据 / 下一证据 |
|---|---|---|
| Feature Freeze 生效 | PASS | 只允许 bug/test/security/performance/packaging/UI fix；未来需求进入 `POST_1_0_BACKLOG.md` |
| 已知 P0 = 0 | NOT_TESTED | 已知登记为 0，但 crash/scope/clean-machine 完整门尚未跑完 |
| 已知 P1 = 0 | PASS | 缺陷登记当前 open P1=0；更广的 crash/security/concurrency 门仍单独验收 |
| Core Conversation E2E | PARTIAL | 当前源码真实 5-JPG v1→v2→diff→批准→执行→重启读取通过一次；post-execution/Undo、发行态及其他核心场景尚缺 |
| Real DeepSeek | PARTIAL | 本轮 7 次 planning/classification/repair 调用全部成功；完整首轮组合已通过一次，不代表错误/限流/稳定性矩阵通过 |
| Filesystem safety | PASS | `python scripts/verify.py all` exit 0，含 safety + integration 127 passed；crash/clean-machine 独立门仍按矩阵追踪 |
| Undo | PASS | 对话式 Undo 临时文件集成通过；10 项真实文件操作在子进程恢复 4 项后强制退出，启动恢复标为 RECOVERY_REQUIRED，续跑仅处理剩余 6 项。Undo + OperationJournal + Execution crash 定向组合 24 passed |
| Recovery | PARTIAL | Undo 4/10、Execution 8/20、Analysis 31/50 均已通过真实子进程崩溃→重启→续跑；发行包组合恢复仍未测试 |
| Packaged Windows app | PASS (local package) | 当前源码已重建 onedir/portable；production build、PyInstaller、frozen diagnose/worker smoke 退出 0。Clean Windows/installer 另为 BLOCKED |
| Clean Windows | BLOCKED | 当前无干净 Windows VM/主机 |
| Installer | BLOCKED | 当前构建机无 Inno Setup 6 |
| Signature / public license | BLOCKED | 无签名证书；项目许可证尚未选定 |

## 功能与组合验收矩阵

| ID | 场景 | 测试类型 | 状态 | 通过标准 / 当前证据 |
|---|---|---|---|---|
| C01 | 新建 Conversation、目录、模型、持久化 | Integration + packaged | PARTIAL | API 创建/重启持久化由 conversation data-model integration 覆盖；当前新冻结包尚未完成创建后重启 smoke |
| C02 | 首次真实 DeepSeek Text/Vision 分析 | Real model + real FS | PASS | 本轮真实 E2E 首次生成 v1 并继续完成后续流程；5 个合成 JPG，仅临时目录 |
| C03 | v1 后修改要求生成 v2 | Integration + real model | PASS | 本轮真实 E2E 生成 parent=v1 的 FULL v2 和 diff；执行前磁盘 hash 不变 |
| C04 | v1/v2/v3 parent/hash/revisions | Integration | PASS (dev integration) | `test_plan_versions_diff_approval_execution_and_restore` 验证 v1/v2/v3/v4 版本保留、parent、hash、版本号及 revision 绑定 |
| C05 | Plan Diff | Integration + UI | PARTIAL | 后端集成验证 taxonomy/file target diff；前端 workspace 测试覆盖历史预览/恢复入口，但未逐字段断言 UI diff 内容 |
| C06 | Restore old version as new version | Integration | PASS (dev integration) | 同一集成测试恢复 v1 为 v4，`restored_from_version_id=v1`，不覆盖历史版本；前端安全恢复入口测试通过 |
| C07 | 自然语言“开始整理”不绕过批准 | Security + UI | PARTIAL | 首次自然语言仅产生预览，显式批准后才执行的后端回归通过；前端无端到端真实桌面验收 |
| C08 | 首轮批准与 Execution #1 | Real model + temp FS | PASS | 本轮真实 5-JPG 完整脚本 exit 0；审批前 hash 不变，审批后 Execution #1 COMPLETED |
| C09 | 执行后 Conversation ACTIVE | Integration | PASS (dev integration) | `test_post_execution_local_delta_and_three_rounds` 执行后保持 ACTIVE，继续生成并执行后续轮次，context pointers 与版本/round 历史一致 |
| C10 | 局部 refinement / Affected Scope | Integration + real model | PASS (current-source real smoke) | 2026-09-24 当前源码 DeepSeek smoke 在 20 个合成文件上解析为 LOCAL/building scope，精确 10 个 building 候选、10 份 evidence 复用且 0 刷新；候选外 10 个文件逐一验证原路径和 SHA-256 不变 |
| C11 | DELTA Plan / Execution #2 | Real model + real FS | PASS (current-source real smoke) | 真实 DeepSeek 1 次分类调用生成 DELTA（2 项操作），临时真实文件目录中 ExecutionRound #2 COMPLETED；执行前后文件数 20 不变、候选外 10 个文件路径及 SHA-256 不变，Conversation 保持 ACTIVE。发行包重启后续跑另由 C17 验收 |
| C12 | File selection 5 files | Integration + UI | PARTIAL | `test_ui_selection_focus_snapshot_and_conversation_isolation` 已精确选择 5 个 stable file ID，验证引用解析及 `AffectedScopeResolver` 的候选 ID 与所选集合完全一致；完整 Plan compile/approve/execute 和真实桌面 UI 链仍未验收 |
| C13 | “这个/刚才那些/上次移动”引用 | Integration | PASS (dev integration) | `test_ui_selection_focus_snapshot_and_conversation_isolation`、`test_recent_message_exact_duplicate_ambiguity_and_priority`、`test_latest_plan_and_actual_execution_references` 覆盖 focused file、recent message、latest plan/execution 与 conversation isolation |
| C14 | Semantic Cache 20 image second taxonomy | Real DeepSeek | PARTIAL | 历史真实 20-file refinement 有 10 项 evidence reuse；20 张图片改 taxonomy 且 Vision calls 接近 0 尚未完成 |
| C15 | Semantic Cache 19 hit / 1 refresh | Real DeepSeek + real FS | PARTIAL | 单图重启缓存与内容变更无效化测试通过；真实 20-file 19 hit/1 refresh 未完成 |
| C16 | Restart persistence | Integration + real model | PASS | 本轮重启读回 ACTIVE Conversation、5 messages、2 plans、1 execution、5 file refs；Cache 全量恢复及 packaged 仍未测 |
| C17 | Restart 后继续 refinement | Packaged + real model | NOT_TESTED | 新 Plan/Execution 正常 |
| C18 | Conversational Undo latest round | Real FS | PASS | 20-file 多轮 smoke 与本轮 10-file 子进程 crash-resume 均通过 |
| C19 | Undo approval boundary | Integration + real FS | PASS | `test_latest_undo_requires_preview_and_preserves_history`：预览后、批准前文件仍在整理目录；明确 approve/execute 后才恢复 |
| C20 | Conversation soft delete disk invariance | Integration + real FS | PASS (dev integration) | 新增 `test_conversation_soft_delete_preserves_disk_journal_and_undo`：真实临时目录中已执行 2 文件后软删除，逐路径 SHA-256 不变，operation/event journal 与 completed round 保留；恢复后仍可生成 Undo 预览且磁盘不变。API 删除/恢复由 conversation data model integration 覆盖 |

## 安全与故障矩阵

| ID | 场景 | 状态 | 通过标准 / 当前证据 |
|---|---|---|---|
| S01 | Prompt injection 文件内容 | PARTIAL | `test_cl05_to_cl08_result_boundaries_and_review_band` 验证恶意 evidence 要求输出路径时仍被类别 allowlist 拒绝；尚未覆盖多种文件载荷与执行调用链 |
| S02 | `..` / parent / system path / other Conversation | PARTIAL | ConversationFile API 对来自其他 Conversation 授权目录的文件 ID 整批拒绝，`test_conversation_file_api_rejects_file_outside_authorized_folder` 通过；`..`、系统路径、junction/reparse 的完整组合仍待验收 |
| S03 | symlink/junction/reparse | PARTIAL | Windows `test_fs07_symlink_or_reparse_is_not_followed` 通过，扫描器拒绝遍历 reparse point；Conversation 引用与执行边界的组合场景仍待覆盖 |
| S04 | Approval bypass phrases | PARTIAL | 自然语言首次请求只产生 FULL proposal、磁盘不变；错误 plan hash 审批被拒绝。短语/重试/重启组合仍待覆盖 |
| S05 | target exists / case collision / same name | PARTIAL | 已验证已有同名目标生成稳定后缀、批量冲突按 file ID 确定性处理，且审批后出现目标时保留双方文件；大小写碰撞组合仍待覆盖 |
| S06 | invalid Windows segment / long path | PARTIAL | `test_fs06_rejects_invalid_windows_category_names` 参数化 10 种非法名均拒绝；超长路径边界仍未测 |
| S07 | read-only / permission denied / locked | PARTIAL | 当前 Windows `test_fs15_locked_source_is_not_forced_or_lost` 与 `test_fs15_read_only_source_can_be_safely_copied_without_change` 通过；真实 ACL permission-denied/journal 组合未测 |
| S08 | external move/rename/modify/missing/new | PASS (dev integration) | `test_workspace_reconciliation_detects_external_changes_and_new_files` 实测 rename/move/modify/missing/new 五类并核对状态 |
| S09 | stable file identity rename/move/undo/restart | PARTIAL | Workspace reconcile 在 rename/move 后通过原 file ID 更新已跟踪文件；Undo 与 restart 的全组合未测 |
| S10 | repeated execute | PASS (dev integration) | `test_op03_move_is_no_clobber_and_repeat_is_idempotent` 与 `test_persistent_approval_events_and_repeat_execute` 重复执行不重放已提交操作 |
| S11 | repeated undo confirm | PASS (dev integration) | `test_partial_undo_and_double_confirm_are_idempotent` 重复确认复用同一 round，不二次恢复文件 |
| S12 | Execution crash 8/20 | PASS | `test_execution_process_crash_after_eight_moves_recovers_remaining_twelve`：真实临时目录与独立子进程，8 COMMITTED + 12 PLANNED；重启恢复后 20 COMMITTED、Conversation round COMPLETED，未重放已提交文件 |
| S13 | Undo crash 4/10 | PASS | `test_undo_process_crash_after_four_restores_resumes_six_without_replay`：独立子进程真实退出，重启观察到 4 UNDONE + 6 PLANNED，恢复后 10 UNDONE 且无重复操作 |
| S14 | Analysis crash 31/50 | PASS (dev integration) | `test_first_analysis_vision_crash_after_31_resumes_only_19_after_restart`：独立进程在 31 个视觉证据提交后 `os._exit(91)`；重启后 31 个视觉证据复用，只对剩余 19 个文件请求视觉分析，完成 50 项分类并恢复 Conversation PlanVersion/提议消息，50 个源文件 hash 不变。Classifier 另对 3 个已缓存视觉证据补齐分类，因此共请求 22 个分类结果；不是重复视觉分析。Fake gateway，发行包恢复未测 |
| S15 | SQLite rollback/unexpected close/concurrency | PARTIAL | Semantic Cache 同键 single-flight 并发测试通过；SQLite rollback/unexpected close 与多写者事务恢复矩阵仍未跑 |
| S16 | Migration from existing schema | PARTIAL | `test_v2_to_v7_migration_is_backed_up_and_repeatable` 检查备份、升级、重复初始化与 template snapshot；`test_legacy_task_remains_unlinked_after_v4_schema` 检查旧 Task 不自动链接 Conversation。当前用例未从真实历史 schema 文件升级，需补真实旧 DB fixture |
| S17 | secret/log audit | PARTIAL | 新增 no-secret regression 检查 SQLite 与 `caplog` 均无 API key、Authorization/Bearer、base64 URL 或 private body；重跑 `test_ai06_ai10_ai11_ai12_privacy_and_no_secret_leak` 1 passed。当前 logging callsites 静态检查仅记录 cache file/evidence IDs 与 kind/state；Windows Credential Manager 与 packaged runtime logs 尚未覆盖 |

## DeepSeek 矩阵

| ID | 场景 | 状态 | 说明 |
|---|---|---|---|
| D01 | Real Text | PASS | 历史真实 smoke 与本轮 20-file DeepSeek refinement 有证据；非完整 RC 通过 |
| D02 | Real Vision | PASS | 历史 `deepseek-flash` evidence 有证据；非完整 RC 通过 |
| D03 | Real Conversation Agent | PASS | 当前源码真实 DeepSeek v1→v2→审批→执行→重启恢复一次通过；重启后继续/Undo 及异常矩阵仍未通过总体 gate |
| D04 | invalid key / 401 | PARTIAL | transport 测试验证 401 不重试；真实 DeepSeek invalid-key 情景未测 |
| D05 | timeout / connection failure | PASS (transport contract) | 新增 MockTransport 回归：模拟读取超时，验证有界 3 次尝试、`MODEL_NETWORK_ERROR` 与 retryable；不代表真实供应商故障注入 |
| D06 | 429 / Retry-After | PARTIAL | mock transport 验证遵循 Retry-After 并按预期重试；真实供应商限流未测 |
| D07 | 5xx / rejected request | PASS (transport contract) | 新增 MockTransport 回归：503 后恢复成功；持续 503 时有界 3 次尝试并返回 `MODEL_SERVER_ERROR`，保留状态码且标记 retryable；不代表真实供应商故障注入 |
| D08 | malformed JSON / missing field | PARTIAL | contract 测试验证一次 repair/重问及证据约束；真实供应商异常输出未测 |
| D09 | invalid tool-like content | PARTIAL | taxonomy 输出路径/深度越界测试拒绝不安全类别；真实模型注入与执行链未测 |
| D10 | vision unsupported | PARTIAL | 分类器缺少已验证 Vision capability 时明确阻止；真实不支持模型未测 |
| D11 | cancelled request | NOT_TESTED | 状态可恢复，不产生假 Plan |
| D12 | AI-only no local semantic fallback | PARTIAL | 同扩展名文档内容分类与受限 planner 用例通过；未覆盖完整格式/发行态矩阵 |

## 性能与规模矩阵

| ID | 数据规模 | 状态 | 必须记录 |
|---|---|---|---|
| P01 | 500 files | PARTIAL | Windows backend 501-entry fixture：scan .094s、persist .041s、attach .131s、reconcile .320s、open .003s、cache lookup .029s、RSS +12.10MB、SQLite integrity ok；UI render 未测 |
| P02 | 1000 files | PARTIAL | Windows backend 1001-entry fixture：scan .217s、persist .079s、attach .256s、reconcile .644s、open .005s、cache lookup .057s、RSS +8.22MB、SQLite integrity ok；UI render 未测 |
| P03 | 5000 files | PARTIAL | Windows backend 5001-entry fixture：scan .933s、persist .411s、attach 1.298s、reconcile 3.409s、open .042s、cache lookup .284s、RSS +43.54MB、SQLite integrity ok；UI render 未测，P2-001 已修复 |
| P04 | 500 files / 450 evidence cache | NOT_TESTED | parser/vision skips、decision calls、hits/misses |
| P05 | 100 messages | NOT_TESTED | open/scroll/references/cards |
| P06 | 300 messages | NOT_TESTED | 同上 |
| P07 | 500 messages | NOT_TESTED | 同上 |
| P08 | 10+ Conversation turns | NOT_TESTED | revisions/current plan/latest execution/references 一致 |

## UI 与可访问性矩阵

| ID | 场景 | 状态 | 说明 |
|---|---|---|---|
| U01 | 1440×900 / 100% | NOT_TESTED | packaged desktop |
| U02 | 1366×768 / 100% | NOT_TESTED | 无溢出/遮挡 |
| U03 | 1280×720 / 100% | NOT_TESTED | 关键操作可点击 |
| U04 | 125% / 150% scaling | NOT_TESTED | Windows 原生 DPI |
| U05 | Empty/No Folder/Normal/Analyzing | NOT_TESTED | 真实状态 |
| U06 | References/Plan/Diff/Approval/Running/Success | NOT_TESTED | 真实状态 |
| U07 | Post-execution/Undo/Conflict/Recovery/Scope/Model error | NOT_TESTED | 真实状态 |
| U08 | Long filename / 5000 list | NOT_TESTED | windowing/lazy/batch |
| U09 | Tab/Enter/Shift+Enter/Esc/focus trap | NOT_TESTED | 键盘可达 |
| U10 | disabled/tooltip/contrast/reduced motion | NOT_TESTED | 可访问性回归 |

## Build 与发布矩阵

| ID | 场景 | 状态 | 说明 |
|---|---|---|---|
| B01 | Backend full tests | PARTIAL | 最近一次完整回归 exit 0：198 passed / 2 summarized warnings / 78.29s；之后新增的 timeout/5xx transport 用例定向 `2 passed`。按用户要求未重复运行全套，因此没有声称新增测试后的完整总数 |
| B02 | Frontend tests | PASS | 当前工作树 `npm run test:run` exit 0，5 files / 39 tests passed；ModelsPage 单测有未注册 RouterLink 的 Vue warning |
| B03 | Typecheck | PASS | 当前工作树打包执行的 `npm run build` 内含 `vue-tsc -b`，exit 0 |
| B04 | Production build | PASS | 当前工作树 `npm run build` + PyInstaller onedir exit 0 |
| B05 | Packaging failure propagates | PASS | 受控 npm exit 7 后脚本立即失败，外层 exit 1；同时兼容 Windows PowerShell 5 |
| B06 | Frozen diagnose/worker | PASS | 当前本机 onedir exit 0 |
| B07 | RC1 version/name/metadata/SHA256 | NOT_TESTED | 尚未生成 1.0.0 RC1 |
| B08 | Release content excludes dev assets/secrets | PARTIAL | 当前 onedir/portable zip 均 434 files；扫描各 301,780,357 bytes，无 node_modules/tests/maps/.env 和已知 DeepSeek/GitHub/AWS/PEM/Bearer/inline credential 签名命中；仍为已知模式扫描，不能排除任意格式的未知凭据 |
| B09 | Setup installer | BLOCKED | Inno Setup 6 不存在 |
| B10 | Clean Windows extract/install smoke | BLOCKED | 无干净环境 |
| B11 | Restart packaged application | PASS (saved session restore) | 本机 `release-phase-n` EXE 实际关闭并重启，恢复同一持久 Conversation、已有消息、48 个稳定文件引用及 96 项当前文件列表；未对该用户真实照片目录发起模型请求或文件操作。重启后继续 refinement/执行/Undo 仍由 C17 及组合验收单独覆盖 |
| B12 | README/CHANGELOG/LIMITATIONS/Release Notes | NOT_TESTED | RC gate 后更新 |

## 多模态矩阵

| Modality | 状态 | 1.0 预期 |
|---|---|---|
| Image | PARTIAL | 真实 DeepSeek 合成 JPG Conversation/vision 及 parser 自动化有证据；完整 image modality 样本矩阵未完成 |
| Text/Markdown | PARTIAL | 真实 DeepSeek text/planning 和同扩展名按内容分类回归有证据；完整格式样本矩阵未完成 |
| PDF | NOT_TESTED | 文本 PDF；扫描 PDF 按 OCR 能力 |
| Office | NOT_TESTED | DOCX/PPTX/XLSX 当前解析边界 |
| Audio | SKIPPED_WITH_REASON | 当前无捆绑 ASR；仅 metadata/partial，写入限制 |
| Video | SKIPPED_WITH_REASON | 当前无捆绑 ffmpeg/ASR；仅可用能力/partial，写入限制 |

## Release Decision Rule

只有 P0=0、P1=0、C02-C19 核心链、S01-S17 安全链、D01-D12 DeepSeek、B01-B11 发布链满足目标且 clean environment PASS，才能写 `RELEASE_READY`。当前登记 open P1=0，但仍有 crash/security/UI/installer/clean Windows 等未完成门；决策仍为 **NOT RELEASE READY**。本轮按用户要求减少重复测试，未把未执行场景标记 PASS。
