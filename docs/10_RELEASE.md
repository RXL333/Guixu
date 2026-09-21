# Windows打包、资源与发布

> **历史流程提示：** “纯规则/模板”发行验收路径已废弃；当前新任务只走 AI-only 流程。

## 1. 两个交付层次

开发交付：源代码、锁文件、迁移、契约、测试、操作说明、阶段报告。

用户交付：`Guixu-Setup-x.y.z.exe`安装程序，以及可选的`Guixu-portable-x64-x.y.z.zip`目录便携包。应用运行入口是Guixu.exe；不是要求用户自己启动前后端。

首发使用PyInstaller onedir再用Inno Setup打安装包，不优先onefile。这样调试依赖、ffmpeg、OCR／ASR资源和更新更清晰。发行目录可能有`_internal`与resources，它们属于程序，不能只把Guixu.exe单独发给别人。pywebview冻结方式依据S05，PyInstaller资源定位依据S14。

## 2. 构建约束

Windows x64包必须在Windows x64构建与测试，不把Linux上生成的文件宣称为Windows可用EXE。构建使用干净虚拟环境，只装锁定的运行依赖；前端先npm ci和build，输出frontend/dist，打包时加入应用只读资源路径。

资源定位基于包内文件位置／importlib.resources，不依赖启动工作目录。用户数据只能写platformdirs决定的应用数据位置。调试与生产分开：生产禁用reload、开发token、远程devtools、Vite服务、MockProvider和样例文件自动注入。

入口处理worker参数与freeze_support，防止打包后的解析器递归启动GUI。ffmpeg路径取自已验证资源，不依赖用户PATH中未知同名程序。

## 3. WebView2与环境诊断

启动检查WebView2 Runtime；缺失时提供明确说明与安装入口，不静默回退旧渲染器。在线安装采用微软官方Evergreen bootstrapper，离线发行可配套完整离线安装程序；具体发行文件、版本与许可随构建记录，不在蓝图中伪造已下载资源。依据S06。

默认按当前用户安装，不要求管理员权限。若运行时安装需要更高权限，应请求系统正常授权或提供手动安装说明，不绕过UAC。

## 4. OCR、ASR、媒体与大模型分层

基础发行包含文本／现代Office／PDF／图片元信息功能、受许可与版本校验的OCR运行组件和可用的小型OCR资源、ffmpeg／ffprobe。构建时必须验证这些真实资源能被找到，不能只把Python包名放进requirements就宣称资源完整。

ASR作为显式资源组件，可选随离线增强包提供；缺失时音频仍能metadata归档，但依赖语音内容的分类必须partial或待确认。安装／导入前显示磁盘占用、版本、来源、许可和SHA-256。faster-whisper只加载已验证本地目录，不使用会自动触发下载的模型短名。依据S11。

Qwen3.8-27B服务和权重独立部署，不包含在Guixu安装程序。不要求用户为了运行文件整理UI先安装CUDA、PyTorch或几十GB权重。

组件包规范：manifest.json包含component_id、version、platform、arch、relative_files、每文件sha256、license_source、entry_paths。导入拒绝绝对路径、`..`、symlink和解压超限。首版不接受资源包中的任意执行安装脚本，不自动安装未知驱动。

## 5. 升级与卸载

启动检测数据库版本，迁移前使用SQLite backup API备份。迁移失败显示恢复诊断，禁止执行文件操作。软件不默认联网自更新，可后续增加有签名的升级流程；首版通过新安装包升级。

卸载默认保留用户数据和历史，单独可选清除缓存与设置；不删除用户整理目录。清除历史会失去应用内撤销索引，需明确确认。Key通过凭据存储接口删除，不是删一个文本配置就假定已经移除。

## 6. 发布检查清单

在干净Windows测试用户下安装 → 无Python／Node启动 → 目录选择 → 纯规则report_only → copy与撤销 → move与撤销 → 中文路径 → 关闭并恢复 → 离线资源加载 → 缺资源说明 → Key持久存储 → 云／本地能力探测（有服务时） → 卸载保留数据。

打包产物附SHA256SUMS、第三方依赖清单、许可通知、支持范围、已知限制和验收报告。代码签名需要实际证书，未签名就说明可能有系统信誉提示，不伪造签名或宣称绕过安全提示。

## 7. 版本完成标签

`dev`：技术闭环开发中，禁止建议用户用真实文件。

`beta`：自动化安全测试通过，但真实模型／桌面兼容范围仍在收敛；建议备份副本试用。

`release`：本设计的安全、桌面与打包必需项均有证据；性能与分类指标诚实列出，不默认扩展到未测系统和文件格式。
