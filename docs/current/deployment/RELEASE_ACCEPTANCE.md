# Guixu 1.0 Release Acceptance

2026-09-28 本地千问阻断修复补充：`qwen3-vl:4b-instruct` 经本机 Ollama 对三张隔离合成 JPG 完成首次预览；人工确认一项 AI 建议后生成 v2 `move` 方案，源图不变、执行操作为 0。后端 228 passed、前端 53 passed，同名便携包覆盖重建并通过冻结诊断。最终打包版原生确认建议与批准执行尚未复测；整体 **NOT RELEASE READY**。见 `artifacts/reports/phase-n-local-qwen-vision-fix.md`。

版本目标：`1.0.0`
候选阶段：Feature Freeze / pre-RC1
基线 commit：`b6ef4ed7dba24519bd7d4f03c4e042dc1f499eea`
最后更新：2026-09-30

2026-09-30 回归与性能复核：当前工作树后端完整 **249 passed / 1 skipped**（83.17s）、前端 **67 passed**、`vue-tsc -b` + 生产构建 exit 0。新增 `backend/tests/safety/test_filesystem_and_storage_edges.py`（15 passed / 1 环境性 skip）关闭 S05 与 S15，收窄 S06、S07 的缺口，S16 补上唯一会删掉外键引用的那次迁移用例。性能脚本重写为多次重复 + nearest-rank 分布后，5,001 项 reconcile 由 p50 3.2465s/p95 3.6674s 降至 **p50 .7341s/p95 .8758s**（全库重哈希已改为 `quick_same` 快速路径，见 DECISION_LOG 2026-09-29）。同时修复 `path_policy.ensure_within` 会在目标尚不存在时按盘上大小写改写路径、导致文件被以占用者大小写重新发布的真实缺陷。**仍为 NOT RELEASE READY**：U01–U04 打包版视口/DPI、B07 RC1、B09 安装器、B10/Clean Windows 干净环境，以及 C05/C07/C12/C17 的打包版真实模型链未关闭。详见 `artifacts/reports/phase-o-release-readiness.md`。

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

## 0.9.0 门禁范围（GitHub 公开下载）

> **2026-09-30 变更：发布方式确定为 GitHub 公开仓库 + 用户自行下载。** 这与原先假定的「受控分发 / 安装器」是两套不同的要求，门禁随之重写：
>
> - **安装器（B09）不再是发布前提。** 分发物是解压即用的 portable ZIP。Inno Setup 脚本保留在 `packaging/Guixu.iss`，等有签名证书时再做。
> - **干净 Windows（B10）从阻塞降为强烈建议。** 判定规则原本明确"不接受在开发机重跑"；在新模型下，本机 portable 包的实测启动、冻结诊断与重启恢复构成 B11/B06 的证据，干净机验证推迟到 0.9.x 迭代。
> - **代码签名明确放弃**，改为 README 中写明 SmartScreen 行为与绕过方法。
> - **许可证从"待选"变成硬前置**：GitHub 上没有 LICENSE 就是保留所有权利，别人无法合法使用。已选 **MIT**。
> - **B12（README / CHANGELOG / LIMITATIONS / Release Notes）从"RC 后补"升级为必须完成**——公开下载的人只能靠这些文档判断能不能用、怎么用。

下方矩阵保留全部验收记录，但**不是每一行都阻塞 0.9.0**。范围在此显式约定，避免"测不完"被当成"不能发"，也避免把没测的项目悄悄算成通过。

### 0.9.0 必须通过

以下任一项未绿，即 **NOT RELEASE READY**：

- **缺陷**：登记 open P0 = 0、open P1 = 0。
- **安全链 S01–S17 全部**。这是 `AGENTS.md` 的硬边界，不参与裁剪；PARTIAL 不算通过。
- **核心对话链 C01–C20 全部**。C07（自然语言不绕过批准）按安全项处理。
- **真实模型 D01–D03**（成功路径必须有真实证据）、**D05/D07/D11**（传输契约与取消路径必须由回归覆盖）。
- **规模 P01–P04、P08**。P01–P03 必须给出 p50/p95 而非单次采样；P04 覆盖证据缓存；P08 覆盖 10 轮以上的一致性。
- **发布 B01–B08、B11、B12**——其中 B12（README/CHANGELOG/LIMITATIONS/Release Notes）在公开分发下是必须完成项。
- **模态 Image、Text/Markdown、PDF、Office**。PDF/Office 的**解析层**已实现并有回归（`test_pa02`~`test_pa04`、`test_pa10`），门禁要求的是**真实模型端到端**：PDF/Office 走完整 Conversation→分类→执行链。Audio/Video 已 `SKIPPED_WITH_REASON`，不属于承诺范围。
- **MIT LICENSE 文件存在**；**git 历史无已知密钥特征**；**portable ZIP 可解压启动**并附 `SHA256SUMS.txt`。

### 0.9.0 之后（不阻塞本次发布）

| 项目 | 推迟理由 | 期间的替代约束 |
|---|---|---|
| **U01–U04** 打包版视口/多 DPI | 需要反复手动操作桌面端，投入产出比低于把安全链做完 | 关键操作在默认 100% 缩放下可点击；布局使用弹性尺寸而非固定像素 |
| **U05–U08** 真实状态 UI 验收 | 同上 | 各状态有对应组件与测试覆盖，真实观感在 0.9.x 迭代补 |
| **B09 安装器** | 无签名证书时安装器价值有限，且增加一条失败路径 | 分发 portable ZIP，解压即用；`packaging/Guixu.iss` 已备好待用 |
| **B10 / Clean Windows** | 无干净环境 | 本机 portable 包实测启动 + 冻结诊断 + 重启恢复作为 0.9.0 证据；干净机验证列入 0.9.x |
| **代码签名** | 无证书 | README 写明 SmartScreen 提示与"更多信息 → 仍要运行"的绕过步骤 |
| **P05–P07**（100/300/500 条消息滚动性能） | 体验优化而非安全或正确性；消息列表已分页加载 | 长会话打开不得丢失或重复消息（P08 覆盖） |
| **U09 / U10** 全量可访问性 | 需要可用性测试流程与人工评审 | 关键操作可点击且有文本说明；不引入无法辨识的颜色作为唯一状态区分 |
| **非 Windows 平台** | 产品定位为 Windows 桌面文件整理器；测试套件依赖 Win32 句柄、Credential Manager、reparse point、长路径与跨卷取消 | 无 |
| **D04/D06/D08/D09/D10/D12 的真实供应商故障注入** | 401/429/5xx 无法确定性制造 | 相同代码路径已由 MockTransport 回归覆盖，契约必须 PASS |

裁剪不等于删除：这些项目在下方矩阵中仍保留原始状态行，便于后续接手时看到"测过什么、缺什么"。

> **关于 S06 与 S07 的环境限制（不视为可裁剪项）。** 这两项的残余缺口不是"体验优化"，而是本机环境原理上无法构造：S06 需要启用 Windows 长路径（注册表 `LongPathsEnabled`，需管理员 + 重启）；S07 需要真实的 ACL deny，而以当前用户命名的 deny ACE 会挡住撤销它自身所需的 ACL API，不提权无法清除。这两项在 0.9.0 前会尽力补齐可验证部分，未补齐的部分必须在 README 的已知限制中写明，不得标为 PASS。

> **2026-09-30 更正。** 本节初版曾把「PDF 内容解析」与「Office 内容解析」列为放弃项，前提是"未实现"。该前提有误：`infrastructure/parsers/documents.py` 已实现 pypdf / python-docx / python-pptx / openpyxl 与本地 RapidOCR，且有回归覆盖。已实现且已有测试的功能不能靠"声明不支持"卸责，两项已移回「1.0 必须通过」，矩阵中 `NOT_TESTED` 的行同时改为 `PARTIAL` 并写明实际缺口是**真实模型端到端**而非解析能力。详见 `POST_1_0_BACKLOG.md` 的更正说明。

> **2026-09-30 更正（性能数字）。** 下方 P01–P03 曾记录单次采样的耗时，包括「5,000 项 attach 1.298s、reconcile 3.409s」。**这些数字不可复现，且不应作为门禁依据**：单次采样无法区分信号与噪声，`attach` 的真实 p50 是 3.13s，比记录的 1.298s 高一倍以上。`scripts/run_phase_n_performance.py` 已重写为多次重复 + nearest-rank 分布，并在 `method.caveat` 中写明「样本数低于 20 时 p95 退化为最大值」。P01–P03 三行已整体替换为 5 次重复的 p50/p95。教训记入 `DECISION_LOG.md`：**未经分布的单次计时不应写进验收矩阵**。

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
| S02 | `..` / parent / system path / other Conversation | PARTIAL | **本轮发现并修复 P1-006**：目录授权此前对系统路径毫无检查，`C:\Windows`、`C:\Windows\System32`、`C:\Program Files`、`C:\Program Files (x86)`、`C:\ProgramData`、`C:\Users\Public` 及任意盘符根全部可被注册为 source 授权。`canonicalize_directory` 现分两类封禁——系统目录封禁整棵子树，盘符根/`C:\Users`/profile 根只封禁其本身（封禁 profile 子树会连带干掉 Documents、Downloads，恰好废掉产品）。新增 `test_protected_locations.py` 15 项，含大小写变体 `C:/WINDOWS` 与近似前缀 `WindowsOld` 的误判防护。`..` 本身由 `resolve()` 归一化后仍受上述检查约束（非逃逸路径仍可授权）。跨 Conversation 的文件 ID 拒绝有 `test_conversation_file_api_rejects_file_outside_authorized_folder` 覆盖；「junction 指向授权目录外」场景已由 S03 本轮新增的执行边界测试覆盖（`test_s03_a_source_reached_only_through_a_junction_is_refused`）。四个分支均有断言，转 PASS |
| S03 | symlink/junction/reparse | PARTIAL | **扫描侧**：`test_fs07_symlink_or_reparse_is_not_followed`，扫描器拒绝遍历 reparse point。**动作侧（本轮新增）**：覆盖「junction 已经躺在授权目录里，方案、过期数据库行或竞态改名可能把操作指向它」这一类——`test_s03_a_junction_in_the_destination_is_never_written_through`（目标树内的 junction 绝不被穿透写入）、`test_s03_a_source_reached_only_through_a_junction_is_refused`（仅经 junction 可达的源被拒）、`test_s03_a_plain_subdirectory_of_the_destination_is_unaffected`（对照组：真实子目录不受影响，防止规则过宽）。两个拒绝用例把 build+approve+execute 包在同一个 `pytest.raises(PathPolicyError)` 里：拒绝实际发生在**方案编译期**而非执行期，即编译阶段就挡住、不触碰磁盘；断言写成阶段无关，是为了让「编译期拒绝」与「批准后 junction 才出现」两种情况共用同一不变量。测试用 `mklink /J` 建 junction（无需管理员），失败时 skip 而非误报通过。**残留缺口**：与 S01 的注入载荷组合、与重启后的过期行组合 |
| S04 | Approval bypass phrases | **PASS** | 新增 `test_approval_bypass.py`（12 项）。**不变量**：对话 turn 里的任何自然语言都不得移动文件，执行只能由用户看得见的两次显式 HTTP 调用（`/approve` 带 plan hash，再 `/execute`）到达。覆盖 `test_s04_no_bypass_phrase_in_a_turn_moves_a_file`（8 种短语参数化：确认执行/直接开始/全部同意/你自动批准/别问我了/我授权你/英文祈使句/已决定开始）、`test_s04_repeating_a_bypass_phrase_never_escalates`（同短语连发 4 次，每次后都断言无 execution round 且文件在原位——防「第三次才算确认」这类倒计时式缺口）、`test_s04_execute_without_an_approval_is_refused`（跳过 approve 直接 execute，即使带正确 plan hash 也 409；随后正常 approve+execute 仍 200，证明拒绝的是请求而非污染了方案）、`test_s04_a_plan_hash_belonging_another_plan_is_refused`（用 v1 的 hash 批准 v2 → 409 `PLAN_HASH_MISMATCH`，v2 自身 hash 仍可批准）、`test_s04_a_pending_plan_still_needs_approval_after_a_restart`（关闭 TestClient 后在同一 data_dir 全新建 app，三句「我之前已经同意了」类短语均不移动文件，且方案重启后仍可正常批准——重启重置的是**审批**不是方案）。断言直接查磁盘与 `list_execution_rounds`，不依赖响应文案 |
| S05 | target exists / case collision / same name | PASS | `test_filesystem_and_storage_edges.py` 新增 3 项：`test_s05_case_only_difference_target_is_never_clobbered`（仅大小写不同的目标生成 `Photo (2).jpg` 而非覆盖）、`test_s05_case_only_collision_appearing_after_approval_keeps_both_files`（审批后出现的大小写冲突记 CONFLICT/TARGET_APPEARED，双方文件均留存）、`test_s05_batch_of_case_differing_names_allocates_distinct_targets`（两个授权根下仅大小写不同的源分得不同目标）。本轮同时修复 `path_policy.ensure_within` 的真实缺陷：原先对尚不存在的叶子做 `resolve()` 会按盘上大小写改写返回路径，使 `Photo.jpg` 被静默以占用者 `photo.jpg` 的大小写重新发布。限制：大小写保留型卷（网络共享/exFAT）本身无环境可测，NTFS 下该差异不可见 |
| S06 | invalid Windows segment / long path | PARTIAL | `test_fs06_rejects_invalid_windows_category_names` 参数化 10 种非法名均拒绝；新增 `test_s06_category_segment_length_boundary_is_sixty_characters`（60 字符边界通过）与 `test_s06_over_length_segment_rejects_the_whole_plan_before_any_disk_change`（超长整份方案在落盘前拒绝）；`test_s06_target_path_beyond_windows_limit_never_loses_the_source` 验证超出 MAX_PATH 的目标安全失败且源文件留存。**残留缺口**：`test_s06_max_depth_nested_long_category_path_is_created_and_published` 在本机被 skip——本卷未启用长路径，执行器的 `.<名>.guixu-part-<uuid>` 暂存名比目标长约 50 字符，229 字符的目标在暂存阶段即达 280 字符。即"超限时的失败行为"已验证，"贴近上限时的成功行为"在本机无法验证 |
| S07 | read-only / permission denied / locked | PARTIAL | `test_fs15_locked_source_is_not_forced_or_lost` 与 `test_fs15_read_only_source_can_be_safely_copied_without_change` 通过；新增 `test_s07_unreadable_source_is_conflicted_and_never_deleted` 与 `test_s07_unwritable_destination_fails_the_operation_without_touching_the_source`，覆盖拒绝后 journal 记 CONFLICT 且源文件不被删除/不被改动。**重要限制**：这两项在 `read_identity`/`identity_matches` 的系统调用边界上注入 PermissionError，**不是真实 ACL deny**；真实 deny ACE 需要提权才能撤销（一个 deny ACE 会挡住撤销它自身所需的 API），因此"真实 OS 拒绝"这一半仍未测 |
| S08 | external move/rename/modify/missing/new | PASS (dev integration) | `test_workspace_reconciliation_detects_external_changes_and_new_files` 实测 rename/move/modify/missing/new 五类并核对状态 |
| S09 | stable file identity rename/move/undo/restart | **PASS** | 新增 `test_undo_restart_identity.py`（6 项）。**不变量**：undo 只作用于它自己移动过的那个文件，且仅当该文件未发生变化——身份是 `(file_id, sha256)` 这一对，行记录「哪个文件」、哈希确认「是否还是同一份内容」。重启 = 关闭 `Database` 后在同一路径重建，不共享任何 Python 对象，因此无法靠内存「记住」。覆盖 `test_s09_undo_after_a_restart_puts_every_file_back`（重启后 undo 全量回位，且是**原 file ID** 回到原路径，不是重新扫描得来）、`test_s09_undo_after_a_restart_still_refuses_a_file_the_user_edited`、`test_s09_undo_never_moves_an_impostor_left_at_the_organized_path`（**本文件的核心用例**：用户把整理后的文件改名拿走、并在原路径放一个不同的新文件；按路径匹配的 undo 会把这个冒名文件搬回原位毁掉它，而身份是哈希，因此必须拒绝——断言冒名文件哈希未变、用户自己的文件仍在、改名后的原位置未被创建）、`test_s09_undo_refuses_to_overwrite_a_file_the_user_created_at_the_original_path`（`AGENTS.md` 明令不覆盖既有文件）、`test_s09_a_change_between_preview_and_execute_is_caught_after_a_restart`（预览 READY → 重启 → 用户改文件 → 再 approve/execute 仍拒 `UNDO_SOURCE_MODIFIED`；断言写成 approve+execute 一并包住，因为实测拒绝发生在**批准阶段**比执行更早）、`test_s09_identity_survives_a_restart_that_also_interrupted_a_turn`（turn 中途被打断后 `audit_startup` 记 1 次 INTERRUPTED，undo 仍能识别文件）。**本项为补覆盖，未发现产品缺陷** |
| S10 | repeated execute | PASS (dev integration) | `test_op03_move_is_no_clobber_and_repeat_is_idempotent` 与 `test_persistent_approval_events_and_repeat_execute` 重复执行不重放已提交操作 |
| S11 | repeated undo confirm | PASS (dev integration) | `test_partial_undo_and_double_confirm_are_idempotent` 重复确认复用同一 round，不二次恢复文件 |
| S12 | Execution crash 8/20 | PASS | `test_execution_process_crash_after_eight_moves_recovers_remaining_twelve`：真实临时目录与独立子进程，8 COMMITTED + 12 PLANNED；重启恢复后 20 COMMITTED、Conversation round COMPLETED，未重放已提交文件 |
| S13 | Undo crash 4/10 | PASS | `test_undo_process_crash_after_four_restores_resumes_six_without_replay`：独立子进程真实退出，重启观察到 4 UNDONE + 6 PLANNED，恢复后 10 UNDONE 且无重复操作 |
| S14 | Analysis crash 31/50 | PASS (dev integration) | `test_first_analysis_vision_crash_after_31_resumes_only_19_after_restart`：独立进程在 31 个视觉证据提交后 `os._exit(91)`；重启后 31 个视觉证据复用，只对剩余 19 个文件请求视觉分析，完成 50 项分类并恢复 Conversation PlanVersion/提议消息，50 个源文件 hash 不变。Classifier 另对 3 个已缓存视觉证据补齐分类，因此共请求 22 个分类结果；不是重复视觉分析。Fake gateway，发行包恢复未测 |
| S15 | SQLite rollback/unexpected close/concurrency | PASS | Semantic Cache 同键 single-flight 并发测试通过；`test_filesystem_and_storage_edges.py` 补齐 6 项：`test_s15_database_configures_wal_busy_timeout_and_full_synchronous`（连接 PRAGMA 实际生效）、`test_s15_rolled_back_transaction_leaves_no_rows_and_keeps_the_file_writable`（回滚无残留行且文件未损坏）、`test_s15_two_writers_on_one_file_lose_no_commits`（两写者提交均不丢）、`test_s15_busy_timeout_holds_a_second_writer_until_the_first_commits`、`test_s15_optimistic_revision_conflict_has_exactly_one_winner`（乐观锁恰好一个赢家）、`test_s15_uncommitted_write_is_discarded_after_a_real_process_exit` 与 `test_s15_committed_write_survives_a_real_process_exit`（独立子进程 `os._exit` 后未提交丢弃、已提交留存） |
| S16 | Migration from existing schema | PASS | 新增 `backend/tests/contract/test_legacy_schema_upgrade.py`（6 项）。fixture 是从**本仓库 git 历史**取出的逐字真实 schema——`git show 4e2700b/4aeb7cd/8db48ab:contracts/database.sql`，对应 2026-09-14（22 表）、09-21（30 表）、09-25（36 表）三个真实年代，不是测试内构造。每个年代验证：升到 head 后种子数据逐字段留存、`classifications.model_call_id` 未被 `DROP TABLE` 的 `ON DELETE SET NULL` 清空、`'chat'` purpose 与 `conversation_id` 可用、`foreign_key_check` 为空、且能用应用自身 `Database` 重新打开；另验证重复 stamp + upgrade 幂等、不产生重复 schema 对象。**本项挖出并修复了 P0-002**（详见缺陷登记）：迁移 0012 的裸 `COMMIT` 使**任何真实旧库升级都在 0012 失败**，而此前所有迁移测试都从当前 schema 建库，新装机器走提前返回分支，因此结构性地覆盖不到该路径。已验证回归测试有牙齿（回退修复 6 red / 恢复 6 green）。另有 `test_v2_to_v7_migration_is_backed_up_and_repeatable` 检查备份、升级、重复初始化与 template snapshot；`test_legacy_task_remains_unlinked_after_v4_schema` 检查旧 Task 不自动链接 Conversation |
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
| P01 | 500 files | PARTIAL | Windows backend 501-entry fixture，5 次重复取 nearest-rank：scan p50 .0253s/p95 .0343s、persist .0401/.0439、attach .2256/.6547、projection .0093/.0348、reconcile .0523/.0851、open .0027/.0030、cache lookup .0600/.0853ms、RSS +13.68MB、SQLite integrity ok。**后端已满足 p50/p95 要求**；UI render 未测，故仍为 PARTIAL |
| P02 | 1000 files | PARTIAL | Windows backend 1001-entry fixture，5 次重复：scan p50 .0673s/p95 .0965s、persist .0995/.1273、attach .6310/1.4443、projection .0184/.0249、reconcile .1085/.1414、open .0056/.0079、cache lookup .0686/.0862ms、RSS +9.22MB、SQLite integrity ok。UI render 未测 |
| P03 | 5000 files | PARTIAL | Windows backend 5001-entry fixture，5 次重复：scan p50 .2962s/p95 .3793s、persist .5056/.6459、attach **3.1326/7.1728**、projection .1349/.1536、reconcile **.7341/.8758**、open .0654/.0778、cache lookup .0704/.0823ms、RSS +48.72MB、SQLite integrity ok。reconcile 已由 O(字节) 改为 O(文件数)，全库重哈希问题（见 DECISION_LOG 2026-09-29）已修复；**最慢阶段现为 attach**，且它是每会话一次性的导入动作，不是每轮成本。UI render 未测 |
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
| B01 | Backend full tests | PASS | 当前工作树完整回归 exit 0：**249 passed / 1 skipped / 2 warnings / 83.17s**。skip 为 `test_s06_max_depth_nested_long_category_path_is_created_and_published`，原因是本卷未启用长路径且执行器暂存名使目标超限，属环境限制而非缺陷 |
| B02 | Frontend tests | PASS | 当前工作树 `npm run test:run` exit 0，**9 files / 67 tests passed**；ModelsPage 的 RouterLink 未注册 warning 已通过 `global.stubs` 消除 |
| B03 | Typecheck | PASS | 当前工作树 `npm run build` 内含 `vue-tsc -b`，exit 0，1744 modules transformed |
| B04 | Production build | PASS | 当前工作树 `npm run build` + PyInstaller onedir exit 0 |
| B05 | Packaging failure propagates | PASS | 受控 npm exit 7 后脚本立即失败，外层 exit 1；同时兼容 Windows PowerShell 5 |
| B06 | Frozen diagnose/worker | PASS | 当前本机 onedir exit 0 |
| B07 | RC1 version/name/metadata/SHA256 | NOT_TESTED | 尚未生成 1.0.0 RC1 |
| B08 | Release content excludes dev assets/secrets | PARTIAL | 当前 onedir/portable zip 均 434 files；扫描各 301,780,357 bytes，无 node_modules/tests/maps/.env 和已知 DeepSeek/GitHub/AWS/PEM/Bearer/inline credential 签名命中；仍为已知模式扫描，不能排除任意格式的未知凭据 |
| B09 | Setup installer | SKIPPED_WITH_REASON | 0.9.0 不分发安装器。GitHub 公开下载场景下分发物是解压即用的 portable ZIP；`packaging/Guixu.iss` 已备好，等有签名证书时再做 |
| B10 | Clean Windows extract/install smoke | SKIPPED_WITH_REASON | 无干净环境。0.9.0 以本机 portable 包实测启动 + 冻结诊断 + 重启恢复作为证据；干净机验证列入 0.9.x |
| B11 | Restart packaged application | PASS (saved session restore) | 本机 `release-phase-n` EXE 实际关闭并重启，恢复同一持久 Conversation、已有消息、48 个稳定文件引用及 96 项当前文件列表；未对该用户真实照片目录发起模型请求或文件操作。重启后继续 refinement/执行/Undo 仍由 C17 及组合验收单独覆盖 |
| B12 | README/CHANGELOG/LIMITATIONS/Release Notes | PARTIAL | 公开下载场景下为**必须完成项**。README 已有 837 行中英双语（功能、隐私设计、便携包、系统要求）；仍需补：0.9.0 版本说明、未签名 EXE 的 SmartScreen 提示与绕过步骤、API key 配置位置、数据与数据库存放路径、已知限制清单。CHANGELOG 需补 0.9.0 条目 |

## 多模态矩阵

| Modality | 状态 | 1.0 预期 |
|---|---|---|
| Image | PARTIAL | 真实 DeepSeek 合成 JPG Conversation/vision 及 parser 自动化有证据；完整 image modality 样本矩阵未完成 |
| Text/Markdown | PARTIAL | 真实 DeepSeek text/planning 和同扩展名按内容分类回归有证据；完整格式样本矩阵未完成 |
| PDF | PARTIAL | 解析已实现（pypdf 分层抽样 + pypdfium2 本地 RapidOCR 扫描件），`test_pa02_text_pdf_scanned_pdf_and_encrypted_pdf`、`test_pa09_stratified_pdf_coverage` 覆盖文本/扫描/加密与抽样边界；**缺真实模型端到端**：PDF 走完整 Conversation→分类→执行链尚无证据 |
| Office | PARTIAL | DOCX/PPTX/XLSX 已实现（python-docx/python-pptx/openpyxl 只读），`test_pa03_docx_table_and_pptx_titles`、`test_pa04_xlsx_does_not_execute_formula` 覆盖表格、标题与公式不执行；`test_pa10` 覆盖 zip bomb 限额；**缺真实模型端到端** |
| Audio | SKIPPED_WITH_REASON | 当前无捆绑 ASR；仅 metadata/partial，写入限制 |
| Video | SKIPPED_WITH_REASON | 当前无捆绑 ffmpeg/ASR；仅可用能力/partial，写入限制 |

## Release Decision Rule

判定规则按上文「0.9.0 必须通过」执行：

1. 缺陷登记 open P0 = 0 且 open P1 = 0。
2. S01–S17、C01–C20、D01–D03 与 D05/D07/D11、P01–P04 与 P08、B01–B08 与 B11/B12 全部为 PASS。
3. Image、Text/Markdown、PDF、Office 四类模态通过（含 PDF/Office 的真实模型端到端链）；Audio/Video 的 `SKIPPED_WITH_REASON` 状态维持不变。
4. 公开分发前置条件齐备：MIT `LICENSE` 存在；`git log --all -p` 扫不到已知密钥特征；portable ZIP 可解压启动并附 `SHA256SUMS.txt`；README 写明系统要求、SmartScreen 行为、API key 配置方式与数据存放位置。

任一项不满足即 **NOT RELEASE READY**。「0.9.0 之后」中的项目不参与判定，但也不得被写成 PASS。

**当前状态：NOT RELEASE READY。** 缺陷登记 open P0/P1 均为 0（P0-002 已修复），S05/S15/S16 已转 PASS。未完成门集中在：S01–S04、S06、S07、S09、S17 的残余 PARTIAL；C05/C07/C12/C17 的打包版真实模型链；D01–D03 的发行包复测；B07 版本与哈希、B12 文档。未执行的场景一律不标记为通过。
