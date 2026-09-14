# 官方依据、时效性与架构决策

核实日期：2026-09-12。以下是设计采用的公开一手来源；外部接口会更新，阶段01／05／09应再次核对与实际安装版本相关的部分。没有本项目的Key、运行实例或Windows实机证据时，不能把官方支持写成本项目已经联调成功。

## 1. 来源

| ID | 官方来源 | 在设计中的用途 |
|---|---|---|
| S01 | https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex | Goal的目标、生命周期与证据式完成标准 |
| S02 | https://api-docs.deepseek.com/guides/vision/ | DeepSeek当前视觉模型、图像输入与旧模型映射 |
| S03 | https://api-docs.deepseek.com/quick_start/pricing/ | 可调用模型名、模型版本与JSON能力；不在本包硬编码价格 |
| S04 | https://api-docs.deepseek.com/guides/thinking_mode/ | DeepSeek思考模式参数，适配器专属处理 |
| S05 | https://pywebview.flowrl.com/guide/freezing | Vue静态资源与PyInstaller冻结 |
| S06 | https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution | WebView2运行时检测、在线／离线分发 |
| S07 | https://pywebview.flowrl.com/guide/security.html | localhost REST保护与session token |
| S08 | https://pypdf.readthedocs.io/en/stable/user/extract-text.html | PDF文字提取与OCR不是一回事 |
| S09 | https://huggingface.co/Qwen/Qwen3.8-27B | Qwen3.8-27B模型身份、参数规模、视觉与部署信息 |
| S10 | https://docs.ollama.com/api/openai-compatibility | Ollama部分兼容接口与视觉Chat Completions |
| S11 | https://github.com/SYSTRAN/faster-whisper/blob/master/README.md | CTranslate2转写、本地加载与CPU INT8 |
| S12 | https://sqlite.org/wal.html | WAL的读写并发、单写者与网络文件系统限制 |
| S13 | https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file | Windows路径、保留名与命名限制 |
| S14 | https://pyinstaller.org/en/stable/runtime-information.html | 冻结后资源路径与包运行信息 |
| S15 | https://github.com/RapidAI/RapidOCRDocs/blob/main/docs/install_usage/rapidocr/install.en.md | RapidOCR当前包与ONNX Runtime安装方式 |
| S16 | https://ffmpeg.org/ffprobe.html | 本地音视频元数据与JSON输出 |
| S17 | https://pywebview.flowrl.com/guide/web_engine | Windows EdgeChromium引擎与运行依赖 |
| S18 | https://pyinstaller.org/en/stable/operating-mode.html | onedir分发与目标操作系统构建 |

对于Python／Vue／控件库的具体小版本，本包不编造一组“已验证兼容”的数字。实施时安装、测试、锁定；以锁文件和构建记录为证据。库选型属于本项目设计判断，不是官方推荐整套组合。

## 2. 当前信息纠偏

前期讨论使用的`deepseek-v4-flash-vision-exp`不能继续作为新项目唯一默认模型名。官方目前说明旧模型已下线并由Flash承接，项目预设使用deepseek-flash，仍以运行时能力探测为准。

Qwen3.8-27B确实有官方模型仓库，不需要把它猜成其他型号；但模型能力、量化文件和部署运行时是三层不同问题。本机Ollama／LM Studio／vLLM是否支持特定权重与视觉输入，需要各自实测，不从型号名称直接推定。

模型自报置信度不是经校准的概率；“可撤销”有外部文件未改变等前提；“本地预处理”仍可能把敏感文字或缩略图发送云端；“本地模型”连接局域网服务器不等于完全只在当前电脑。这些说明已融入产品与交互。

## 3. 决策记录

| ID | 决策 | 理由／后果 |
|---|---|---|
| ADR01 | 单用户本地应用，不做SaaS | 避免账号、租户、服务器运维偏离范围 |
| ADR02 | Vue + Python + pywebview | 保留Python处理生态与可定制桌面审阅UI |
| ADR03 | SQLite单库＋单写者 | 足够支撑本地任务，减少Redis／Celery运维 |
| ADR04 | 模型服务外置 | 不把27B权重和GPU环境绑进EXE |
| ADR05 | 解析层、分类层、执行层隔离 | 模型不接触文件移动权限 |
| ADR06 | 两阶段规划，树先冻结 | 防止同义目录膨胀与逐文件随意造目录 |
| ADR07 | 区域相对深度 | 同时满足保留一级结构与默认两级分类 |
| ADR08 | 待确认默认虚拟且原地 | 减少无证据情况下搬乱文件 |
| ADR09 | 高可信为证据门槛，不是概率 | 降低自评分虚高造成的误移动 |
| ADR10 | 不覆盖、不自动去重删除 | 先满足数据安全与可恢复 |
| ADR11 | 操作日志＋检查点恢复 | 数据库与磁盘无法构成共同事务 |
| ADR12 | 默认CPU OCR／可选ASR | 避免与本地27B抢GPU并减少依赖 |
| ADR13 | REST增量轮询，首版不做WebSocket | 任务进度需求够用，部署与鉴权简单 |
| ADR14 | onedir + installer | 资源与依赖清晰，可提供一个安装EXE |
| ADR15 | 分阶段Goal与证据报告 | 控制上下文、成本与虚假完成 |
| ADR16 | 不把普通开源兼容服务当第三家业务 | 首要只做DeepSeek与Qwen；运行时复用transport |

## 4. 外部前提的处理，不重新询问已定需求

本地模型硬件／运行时未知：阶段05通过可配置URL与能力测试解决；缺服务使用显式假服务契约测试，真实联调单独阻塞。

Key未知：应用设置页输入，凭据安全保存；不要求放进Goal、AGENTS或仓库。

Windows构建环境未知：阶段01 doctor记录；当前非Windows时开发跨平台可测部分，阶段09必须在真实Windows验证。

资源下载／签名证书缺失：禁止自动绕过；记录需求与安全获取方式，不让它成为伪造发行就绪的理由。
