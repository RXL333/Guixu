# 后续实施决策日志

设计基线：2026-09-12，v1.0。基线架构取舍已在docs/12_SOURCES_DECISIONS.md记录。这里由实施AI追加实际版本锁定、平台兼容取舍与经用户批准的需求变化。

每条记录包括日期、阶段、问题、证据、所选方案、被放弃方案、影响的契约/测试、是否需要用户授权。不要把普通依赖小版本确认扩大成重新讨论产品定位；涉及文件安全、隐私范围、真实费用或核心模式删除的变化不能自行放宽。

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
