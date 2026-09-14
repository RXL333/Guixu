# 技术架构与模块实现设计

## 1. 选择：Python 桌面壳 + 本地 Web UI

最终形态是 `Guixu.exe` 打开自己的窗口，不要求用户另开浏览器。Vue前端编译为静态资源，FastAPI仅绑定 `127.0.0.1` 的随机端口，pywebview 使用 EdgeChromium 打开这个受保护的本地地址。启动、服务退出与窗口关闭由一个 Python 主进程协调。

不选 Electron，是为避免在 Python 后端之外再维护完整 Node桌面主进程；不选纯 PySide，是因为本项目对可定制的文件审阅与视觉设计要求较高；不选 Tauri，是为避免第一版引入 Rust与 Python sidecar 的额外发布复杂度。这是本项目取舍，不是对这些技术的一般优劣结论。

pywebview可承载构建后的 Vue资源并用 PyInstaller冻结，Windows EdgeChromium依赖 WebView2 Runtime；参考 S05、S06。不能回退到旧 MSHTML渲染器后仍声称功能正常。

## 2. 依赖边界

```text
Vue UI ── authenticated REST ── FastAPI routes
  │                                  │
  └─ narrow DesktopBridge            └─ Application services
      (目录选择／窗口／打开位置)           │
                                         ├─ Domain policies
                                         ├─ TaskCoordinator
                                         ├─ ParserRunner ── parser subprocess
                                         ├─ ModelGateway ── DeepSeek / Qwen service
                                         ├─ PlanCompiler
                                         └─ OperationExecutor ── authorized filesystem
                                                   │
                                             SQLite + operation journal
```

Domain 不导入 FastAPI、Vue或具体模型 SDK。UI不拼实际磁盘目标路径；它只提交类别选择与受授权的目录 ID。ModelAdapter既不能访问执行器，也不能执行模型返回的代码。

### 2.1 模块与明确接口

| 模块 | 输入 | 输出／职责 | 禁止承担 |
|---|---|---|---|
| SourceRegistry | 原生选择的目录 | source_grant、canonical_root | 静默注册任意前端路径 |
| Scanner | ScopeSpec、过滤器 | FileSnapshot流 | 全量正文解析与默认全文件哈希 |
| MetadataService | 文件句柄／安全路径 | FileMetadata | 上传云端 |
| RuleEngine | Snapshot／Profile、规则快照 | exclude／force／hints／conflict | 执行 shell或路径移动 |
| ParserRegistry | 模态、扩展名、组件能力 | ParserSpec | 把未支持标成成功 |
| ParserRunner | ParserJob、资源预算 | FileProfile、警告与覆盖度 | 长期占有数据库事务 |
| PrivacyGate | 出站候选、授权、预算 | 允许的 OutboundEnvelope或拒绝 | 自行向其他服务转发 |
| ModelGateway | Envelope、ModelProfile | 标准响应与用量 | 直接写分类目录 |
| PolicyCompiler | 用户说明与限制 | ClassificationPolicy | 执行用户／文件内容里的指令 |
| TaxonomyPlanner | 分层样例、Policy、已存在节点 | TaxonomyDraft | 无上限新增目录 |
| Classifier | FileProfile、已批准树 | ClassificationResult | 输出绝对路径作为目的地 |
| ReviewService | 人工类别／批量编辑 | 版本化 ReviewDecision | 修改旧操作日志 |
| PlanCompiler | 快照、人工决策、目标区域 | 不可变 ExecutionPlan | 实际移动文件 |
| OperationExecutor | 已批准 plan_hash | 逐项操作结果与日志 | 重新问 AI怎样放文件 |
| RecoveryService | 操作日志与磁盘状态 | safe resume／conflict | 推测并删除不明文件 |
| TaskCoordinator | 用户命令、检查点 | 有限状态推进 | 内存中保存唯一进度 |

方法名属于项目接口，可按 Python命名规范实现；参数／结果用 Pydantic／dataclass明确类型，不能用无约束字典串联全部业务。

## 3. 运行时与并发模型

主线程运行 pywebview事件循环。Uvicorn在受控线程启动，只有一个 worker；不要使用 `--reload` 或多 worker 发布。FastAPI lifespan创建 TaskCoordinator，它用 asyncio编排任务、调用 httpx异步模型接口。

所有数据库写入通过单个 writer执行队列和短事务完成，读取使用短生命周期 Session。SQLite开启 foreign_keys、WAL、busy_timeout=5000、synchronous=FULL。外部模型请求、文件复制和解析期间不得持有数据库事务。WAL支持读写并发但仍只有一个写者，数据库保存在本机磁盘，不放网络共享目录；依据 S12。

默认一个活动任务；元数据 I/O最多 4个线程；解析最多 2个子进程，但 OCR／ASR重型工作默认 1个；云 API并发 2，本地模型并发 1；实际文件操作始终串行。用户能调低上限，调高需经过压力验证，第一版不要暴露二十个难懂的性能旋钮。

解析工作用独立 worker入口：源代码时 `python -m guixu.worker`，冻结后 `Guixu.exe --worker ...`。入口先判断 worker模式，再初始化 GUI，避免子进程弹出新窗口。使用 `if __name__ == '__main__'` 和 freeze_support；父进程限制单作业时间、临时目录和输出大小，必要时终止自己创建的进程树。进程隔离是故障隔离，不是完整恶意文件沙箱。

## 4. 生命周期

启动：解析参数 → 单实例锁 → 数据目录可写检查 → 数据库迁移／迁移前备份 → 清理可证实的过期自有临时文件 → 扫描未结束操作 → 启动本地 API → 健康就绪 → 打开窗口。

窗口关闭时有活动任务：提供「安全暂停并退出／返回」。选退出后禁止派发新作业，当前文件执行到安全检查点，持久化状态，停止子进程、HTTP客户端和服务。不得把任务偷偷留在后台常驻。

异常退出：下次启动显示恢复卡片，状态进入 RECOVERY_REQUIRED，由 RecoveryService检查文件真实位置和哈希；不自动重复移动。操作日志恢复完成后，用户再选择继续、只看报告或撤销已完成项。

## 5. 任务状态机

`status` 描述生命周期，`phase` 描述当前工作。合法 status：DRAFT、RUNNING、PAUSE_REQUESTED、PAUSED、AWAITING_TAXONOMY_APPROVAL、AWAITING_EXECUTION_APPROVAL、RECOVERY_REQUIRED、COMPLETED、COMPLETED_WITH_ISSUES、CANCELLED、FAILED。phase：SETUP、SCAN、EXTRACT、PLAN、CLASSIFY、PREVIEW、EXECUTE、REPORT、UNDO。

| 命令／事件 | 前置状态 | 结果 |
|---|---|---|
| start | DRAFT | RUNNING / SCAN |
| 自动规划完成 | RUNNING / PLAN | AWAITING_TAXONOMY_APPROVAL |
| approve_taxonomy | 等待树批准且版本一致 | RUNNING / CLASSIFY |
| 分类完成 | RUNNING / CLASSIFY | AWAITING_EXECUTION_APPROVAL / PREVIEW，或 report_only直接生成报告 |
| execute | 执行计划有效且授权哈希一致 | RUNNING / EXECUTE |
| direct_move资格满足 | 树固定、启动授权有效、全部前置条件通过 | 经计划编译后执行，不跳过日志 |
| pause | RUNNING | PAUSE_REQUESTED，再到 PAUSED |
| resume | PAUSED且检查点仍有效 | RUNNING / 原 phase |
| cancel | 非终态 | 安全停调度后 CANCELLED，已完成操作保留 |
| crash recovery | 启动发现未闭合操作 | RECOVERY_REQUIRED |
| finalize | 所有候选已落入终态 | COMPLETED或COMPLETED_WITH_ISSUES |
| undo | 已有可撤销操作且没有活动执行 | RUNNING / UNDO，结果汇总后回到完成态 |

每次转移使用 expected_revision乐观锁；状态与 task_event在一个事务中写入。用户重复点击不会创建第二个执行任务。事件在当前 phase有效，不能从 DRAFT直接执行。

## 6. 前后端通信

第一版采用 REST + 增量轮询，不引入 WebSocket。活动任务每 1秒请求 events?after_seq，后台页降至 3秒，终态停止。事件每批返回最多 200条，包含 seq、phase、计数、警告、时间；原始文件内容不放进事件。

进度展示按阶段分别计算，不用一个伪精确百分比覆盖扫描和未知长度的解析。扫描显示已发现数；分类显示 completed/eligible；复制显示当前字节与项目数。预计剩余时间不足样本时显示「估算中」。

批量列表用后端分页，默认100、最大500；文件表虚拟滚动或固定行高。全文搜索首版仅搜文件名、类别、已提取摘要，不宣称全库语义检索。

## 7. 桌面 API 安全

pywebview产生的 session token仅放内存，前端请求头使用 `X-Guixu-Session`，后端常量时间比较。入口静态资源不包含生产 token，不能提供未认证的“获取 token”HTTP接口。

后端同时验证 Host为本次绑定地址端口，限制 Origin为本应用源，拒绝跨站来源。生产无通配 CORS；开发仅允许明确配置的 Vite源。所有改变状态的请求要求 token；读任务、文件预览和模型配置同样受保护。不要认为绑定 localhost就天然安全。参考 S07。

DesktopBridge只暴露 select_directory、register_typed_directory、reveal_registered_file、open_approved_external_url和窗口控制。路径注册经过与扫描相同的 canonical／reparse校验，返回临时 grant ID；不暴露 run_command、read_any_file或任意 evaluate_js给前端。

媒体预览通过认证 POST创建短期、单文件、只读 preview_ticket，再用这个有限权限 ticket进行 Range读取；全局 session token不放URL。ticket默认60秒，可刷新；响应不缓存、日志不记录票据。严禁把原始 HTML、SVG脚本或 Office活动内容作为可执行页面打开；PDF预览使用渲染位图与文本。

## 8. 数据、缓存、资源与可迁移性

默认目录：`%LOCALAPPDATA%\Guixu\`，下设 app.sqlite3、cache/profiles、cache/thumbnails、cache/transcripts、jobs、models/ocr、models/asr、logs、backups。模型服务由用户自行部署，其大型 Qwen权重不归应用管理。

安装资源和用户数据完全分离，禁止写入 `_internal` 或程序安装目录。可在设置页迁移应用数据目录，但只能在无活动任务时进行，迁移前关闭 DB、备份并校验；第一版不把 SQLite迁往网络路径。

缓存键分两层：解析缓存为 content_hash + parser_version + parse_options_hash；分类缓存另加 file_context_hash + taxonomy_hash + rules_hash + prompt_version + model_profile_hash + privacy_policy_hash。相同内容但文件名／区域上下文不同，可以共享无上下文的解析结果，不能直接共享最终去向。

正文／转写缓存默认7天、缩略图30天、总缓存软上限2 GiB；日志30天、任务元数据保留直到用户删除。执行日志不因普通缓存清理被删除。用户清除历史前需说明会影响撤销，删除记录不删除原始文件。

## 9. 建议代码目录

```text
backend/
  pyproject.toml
  src/guixu/
    main.py                 # GUI与worker入口分派
    desktop/                # 窗口、桥、单实例、启动
    api/                    # 路由、认证、请求／响应契约
    application/            # 用例、协调器、预览、批准与恢复
    domain/                 # 类型、规则、策略、状态机、路径政策
    infrastructure/
      db/                   # SQLAlchemy模型／repository／writer
      filesystem/           # 扫描、句柄、哈希、no-clobber操作
      parsers/              # 文本、PDF、Office、图像、音视频
      models/               # transport、deepseek、qwen、capabilities
      secrets/              # Windows凭据存储
      resources/            # 离线资源包验证
    worker/                 # 独立解析作业入口
  migrations/
  tests/{unit,integration,contract,safety}/
frontend/
  src/{app,layouts,pages,components,stores,services,types,styles}/
  tests/
resources/{icons,templates,prompts}/
scripts/                    # doctor、verify、build、sample-data
packaging/                  # PyInstaller spec、Inno Setup
contracts/                  # 与运行时一致的导出契约
artifacts/                  # 本地报告和截图，不含密钥
```

不把业务流程塞进一个巨型 main.py，不把 UI路由直接映射到 shutil.move，不把 parser子进程当作持久业务主进程。
