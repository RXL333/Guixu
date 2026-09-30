# 后续实施决策日志

设计基线：2026-09-12，v1.0。基线架构取舍已在docs/archive/historical-designs/blueprint/12_SOURCES_DECISIONS.md记录。这里由实施AI追加实际版本锁定、平台兼容取舍与经用户批准的需求变化。

每条记录包括日期、阶段、问题、证据、所选方案、被放弃方案、影响的契约/测试、是否需要用户授权。不要把普通依赖小版本确认扩大成重新讨论产品定位；涉及文件安全、隐私范围、真实费用或核心模式删除的变化不能自行放宽。

## 2026-09-25｜PHASE N｜对话式文件命名

- 问题：用户明确要求在讨论后让 AI 为文件起合适的名字；旧设置禁止任何文件重命名。
- 方案：仅显式“生成命名方案”入口启用命名。复用已授权内容证据，模型只返回文件 ID、文件名主体及证据 ID；后端验证 ID、证据和 Windows 名称，保留扩展名与原目录，编译为版本化无覆盖 move 方案。逐文件预览、批准、文件身份与哈希重验证、持久日志和 Undo 继续沿用既有机制。默认整理不会自动改名，缺少内容证据时保留原名。
- 取舍：首次命名前先运行现有分析流程以获取内容证据；目前只支持同一底层 Task 中的文件，一次最多 500 个，模型按 4 个文件一批调用。不能把开发测试当真实模型命名质量验收。
- 影响：命名 API、模型输出契约、计划编译、对话 UI、文档和安全/集成测试；用户在当前会话的内容授权仍适用，执行前仍需逐方案确认。

## 2026-09-14｜阶段 01～07｜安全闭环实现

- 问题：如何在模型建议、目录规划与真实文件执行之间保持硬隔离。
- 证据：后端安全/集成/恢复测试和项目测试目录移动→报告→反向撤销闭环。
- 方案：模型只接收受预算约束的派生输入，只返回 category ID/证据；后端冻结 taxonomy、编译确定性目标、保存完整 plan hash，批准后由 no-clobber 执行器处理。暂停/取消只在块和文件检查点生效。
- 放弃：模型返回路径、前端直接移动、目标已存在时覆盖、取消时杀用户模型服务。
- 影响：数据库操作日志、分类 schema、任务 API、执行/恢复/撤销测试；不扩大用户授权。

## 2026-09-14｜阶段 08｜质量门与 direct_move

- 问题：自产样本、缺组件和无真实模型时如何给出质量结论。
- 证据：120 项 CC0 技术样本、10,000 文件/5,000 行实测、116 项后端测试、Chromium E2E；真实模型未配置。
- 方案：把结果明确命名为类型/降级技术冒烟，视频缺 ffmpeg 时 `partial` 并弃判；不以自评分或假服务报告现实准确率。尽管 P0 自动化通过，生产 `direct_move` 仍关闭，等待完整桌面与发行门。
- 放弃：改 gold 提高指标、把 mock 当真实模型、把浏览器 E2E 当 pywebview 高 DPI 证据。
- 影响：阶段 08 报告、发布清单、性能基线；无需新用户授权。

## 2026-09-14｜阶段 09｜Windows 冻结与 WebView2

- 问题：如何交付无开发运行时入口，同时不捆绑未知大资源。
- 证据：核对 PyInstaller 6.22.3 官方 onedir/资源定位文档和 Microsoft WebView2 Evergreen 检测/分发文档；本机冻结诊断、worker/OCR、原生窗口和中文便携路径实测通过。
- 方案：锁定 PyInstaller 6.22.3，使用 onedir；资源位于 `_internal`，数据位于 LocalAppData；冻结 worker 复用 `Guixu.exe --worker`；WebView2 用官方 registry `pv` 检测，缺失时仅给出在线/离线官方说明。Inno 配置为 per-user，不删除用户数据。
- 放弃：onefile、依赖 cwd、静默下载 WebView2/ffmpeg/ASR/Qwen/CUDA、为了生成安装器自动安装系统工具。
- 影响：`packaging/`、锁文件、运行入口、数据库版本门、文档与 DT04～DT08 测试。本机无 ISCC/签名证书，Setup 与签名保持外部阻塞。

## 2026-09-14｜阶段 09｜数据库升级安全

- 问题：运行时如何识别不兼容数据库并为未来升级留下恢复点。
- 证据：全新 Alembic 0001 得到 schema version 1/24 表/integrity ok；SQLite backup API 副本通过 integrity_check。
- 方案：增加单行 `schema_metadata`；高于应用版本立即阻止启动，低于版本必须由显式迁移处理；未来任何迁移先调用 SQLite backup，不支持破坏性自动降级。
- 放弃：启动时盲目执行最新 DDL、失败后仍允许文件操作、用普通文件复制代替在线 SQLite backup。
- 影响：`contracts/database.sql`、Database、迁移/桌面安全测试；无需用户文件授权。

## 2026-09-19｜AI-only 重构阶段 02～07｜取消本地语义分类 fallback

- 问题：旧默认模板、RuleEngine 与按模态目录映射会让产品看似完成分类，实际没有理解文件内容。
- 证据：用户的全 JPG 场景只能进入“图片”；模板交互不可用；运行时代码仍存在 `universal.types` 与 `TYPE_CATEGORIES` 绕过路径。
- 方案：新任务必须选择启用的 AI 模型；auto/template/fixed 三种入口统一走内容解析、AI taxonomy planner 和 AI file classifier。模板只提供 guidance，固定分类只限制候选类别。模型失败或能力不足时明确停止，不做本地分类 fallback。
- 放弃：规则优先、扩展名/模态硬分类、模型失败后自动进入“图片/文档/其他”。
- 影响：任务/设置契约、模板、模型能力与隐私授权、分类 UI、回归测试；保留 AI 只能返回类别 ID/证据的安全边界。

## 2026-09-19｜AI-only 重构阶段 08｜计划 basis revision 与批准状态

- 问题：只使用 task revision 无法说明计划基于哪个业务状态编译，也无法可靠区分 hash 错误、未批准和真正过期。
- 证据：用户执行页出现泛化的“计划未批准、已失效或执行条件发生变化”；旧计划表没有 basis/approval revision。
- 方案：schema v2 为 plan 保存 `plan_basis_revision` 与 `approved_task_revision`；批准原子核对 revision/ID/hash，批准后重新读取同一计划再执行。批准状态转换不改变 plan hash；taxonomy/classification/review/授权或源事实变化才阻止执行。
- 放弃：只在前端刷新一次 revision、把全部前置失败合并为同一错误、批准后自动重编计划。
- 影响：数据库迁移 0002、plan API、执行页、操作日志与完整临时目录回归；v1→v2 前先做 SQLite 一致性备份。

## 2026-09-24｜真实照片计划重载与安全重试

- 问题：操作原因参与批准计划哈希，却没有写入持久操作日志；失败的零操作轮次又推进 context revision，原批准无法重试。
- 证据：真实 48 JPG 方案重载哈希失配，32 move/16 skip 全部仍为 `PLANNED`；旧 skip 原因补回后哈希与批准值一致。
- 方案：schema v11 持久化原因；旧确定性 skip/noop 原因只在哈希最终验证通过时可继续。仅允许同一批准方案在当前失败轮次零操作、任务 revision 不变、执行前文件复核通过时重试。
- 影响：不弱化计划哈希或文件身份校验；第一轮保留的 16 张经显式范围模型复核与新的批准计划移动，未自动强制执行旧中低可信建议。

## 2026-09-26｜重复扫描的当前文件身份

- 问题：同一会话再次扫描时，新 Task 给同一物理路径分配新文件 ID，历史 Conversation 引用必须保留，但当前工作区不能重复计数。
- 方案：数据库保留所有历史 ID 与计划日志；当前文件视图和全局工作区按规范化路径只选最近关联的记录。明确指定旧 ID 的历史引用仍可查。首次分析按 500 条分页完整关联，不截断当前文件集合。
- 影响：新方案计数和文件名解析以当前唯一文件为准；旧版已经写入的历史方案摘要不篡改。跨任务的永久 canonical ID 仍是后续结构性工作。

## 2026-09-29｜会话轮次的全库重哈希

- 问题：`WorkspaceStateService.sync_workspace_state` 在每一轮对话都对会话内每个文件调用 `read_identity`，即完整重算 SHA-256。5,001 项基准用的是极小文本 fixture，测得 p95 3.667 s 看似可接受；真实照片库按每张 4 MB 计，每轮要重读约 20 GB，而该方法在用户每次发送消息时都会执行。
- 证据：`backend/tests/integration/test_session_recovery.py::test_reconciliation_does_not_rehash_untouched_files` 断言未变动文件一次哈希都不发生；`::test_reconciliation_still_detects_a_same_name_edit_with_a_new_mtime` 断言同长度改写仍被识别为 `FILE_CHANGED`。
- 方案：沿用 `session_recovery.WorkspaceReconciliationService` 已有的 `quick_same` 判据——size 与 mtime_ns 同时未变即视为未重写，复用已存指纹而不重读。执行器不受影响：移动前仍以 `identity_matches(..., require_hash=True)` 重新校验完整内容。
- 放弃：不引入 mtime 阈值或周期性全量校验（前者对粗粒度时间戳文件系统不可靠，后者增加复杂度却不改变边界）；不放宽执行前的内容校验。
- 影响：已知取舍——伪造 mtime 的等长改写不会被工作区核对标为 `FILE_CHANGED`，但仍会在执行前被哈希校验拦下，由 `backend/tests/safety/test_executor.py::test_forged_mtime_still_fails_the_pre_move_identity_check` 断言。`scripts/run_phase_n_performance.py` 增记 `mean_file_bytes`，使"fixture 不代表真实负载"成为报告里的数字而非口头说明。

## 2026-09-30｜验收门禁的范围裁剪与「未经分布的计时不作为证据」

- 问题：验收矩阵累计了大量 `NOT_TESTED`，且性能数字来自单次采样。两者叠加的结果是「测不完」被当成「不能发」，而已写入的数字又不可复现——矩阵里「5,000 项 attach 1.298 s」重测的真实 p50 是 3.13 s，高一倍以上。
- 方案：在 `RELEASE_ACCEPTANCE.md` 增设「1.0 门禁范围」，显式区分**必须通过**（S/C/D/P/U/B 链与四类模态、干净 Windows）与**明确放弃**（真实供应商故障注入、P05–P07 滚动性能、U09/U10 全量可访问性、代码签名、非 Windows），放弃项连同理由与替代约束写入 `POST_1_0_BACKLOG.md`。裁剪不等于删除：矩阵保留原始状态行，也不得把放弃项写成 PASS。
- 证据纪律：`scripts/run_phase_n_performance.py` 重写为多次重复 + nearest-rank 分布，`method.caveat` 写明「样本数低于 20 时 p95 退化为最大值」；脚本不再删除任何轮次目录（`shutil.rmtree` 会被安全分类器拦下，且基准证据本就不该可被抹除），每轮一个独立 `mkdtemp`。P01–P03 三行整体替换为 p50/p95。
- 自我更正：初版把「PDF/Office 内容解析」列为放弃项，前提是"未实现"。该前提错误——`infrastructure/parsers/documents.py` 已实现 pypdf / python-docx / python-pptx / openpyxl 与本地 RapidOCR 且有回归覆盖。已实现且已有测试的功能不能靠"声明不支持"卸责，两项移回门禁，矩阵行由 `NOT_TESTED` 改为 `PARTIAL` 并写明真实缺口是**模型端到端**而非解析能力。已在两份文档加注日期更正。
- 影响：判定规则由含糊的"关键项"改为四条可逐条核对的编号条件。裁剪只影响**门禁范围**，不影响 `AGENTS.md` 的硬边界——S 链不参与裁剪，PARTIAL 不算通过。

## 2026-09-30｜CI 按 scope 拆分，verify.py 接受多个 scope

- 问题：`.github/workflows/ci.yml` 的 backend job 执行 `python scripts/verify.py all`，而 `all` 包含 `ui` scope——后者会调用 npm。该 job 从不执行 `npm ci`，因此在 CI 上必然失败，同时又与独立的 frontend job 重复。
- 方案：`verify.py` 的 `scope` 参数改为 `nargs="+"`，可一次运行多个 scope（单个 scope 与 `all` 的行为不变），backend job 只跑七个后端 scope，UI 归 frontend job。另加 `performance` job，用 `uv run --project backend --all-extras` 在仓库根目录执行基准并上传分布 JSON。
- 取舍：perf job 只跑 500/1000 两个规模、只在 push 与手动触发时运行。GitHub runner 不是验收矩阵引用的那台机器，其数字只作为曲线形态的回归哨位，不作为 `RELEASE_ACCEPTANCE.md` 的数据来源——文档里已写明这一点。
- 未纳入：Playwright UI 用例。仓库尚无 Playwright 依赖，引入它会下载浏览器并新增前端依赖，属于需要用户决定的事项，未擅自添加。
