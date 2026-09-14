# 阶段 09 验收报告：Windows 打包与可复现交付

日期：2026-09-14  
环境：Windows 11 10.0.22631 x64；Python 3.12.10；PyInstaller 6.22.3；Node 24.11.1；WebView2 Runtime 152.0.4191.66

## 结论

阶段 09 为 **BLOCKED_EXTERNAL（Windows onedir/portable 已验证，安装器与干净机矩阵未完成）**。

真实 Windows x64 PyInstaller onedir 已生成，原生 pywebview 窗口能加载 Vue 静态资源，数据写入隔离的项目测试目录，关闭后释放并以 0 退出。同一冻结 EXE 的 worker、中文 TXT 和包内 RapidOCR/ONNX Runtime 图片解析均实际通过。完整 onedir ZIP 在中文提取路径下再次运行诊断成功，不依赖启动工作目录，也不包含 `python.exe` 或 `node.exe`。

本机没有 Inno Setup 6，故没有生成 `Guixu-Setup-0.1.0-unsigned.exe`，不能把 `.iss` 当成安装器。没有代码签名证书，EXE 的 Authenticode 状态为 `NotSigned`。无 Python/Node 的干净 Windows 用户、Windows 10/Server/LTSC、高 DPI/多显示器、安装/升级/卸载仍需外部测试，所以版本保持 `0.1.0 dev`，生产 `direct_move` 继续关闭。

## 实现内容

- `packaging/Guixu.spec`：Windows x64 onedir，收录 contracts、seed、Vue dist、用户文档、RapidOCR 模型与 PyInstaller 发现的 DLL；不捆绑 Qwen/CUDA/ffmpeg/ASR。
- `scripts/package-windows.ps1`：验证目标路径 → npm ci/build → 全量测试 → onedir → 冻结诊断 → 同 EXE worker → ZIP → 可选 ISCC → SBOM/SHA-256。递归输出只限项目 `artifacts`。
- `packaging/Guixu.iss`：per-user、`PrivilegesRequired=lowest`、LocalAppData 安装目录、卸载保留用户数据；检测 WebView2 registry `pv`，缺失时明确说明在线 Evergreen 与离线 Standalone 区别，不静默下载。
- 冻结入口使用 `Guixu.exe --worker`，不再错误地以 `-m guixu.worker` 回到 GUI；窗口关闭事件停止 uvicorn、关闭数据库并释放单实例锁，修复冻结进程残留。
- 运行时资源从冻结根定位；业务数据默认 `%LOCALAPPDATA%\Guixu`。只有同时设置测试模式与测试目录时才允许测试重定向。
- 数据库增加 `schema_metadata` version 1、新版本拒绝启动和 SQLite backup API；备份经 `integrity_check` 测试。全新 Alembic `0001` 产生 24 张表。
- 生成 `contracts/openapi-runtime.json`、实现架构快照、用户/开发手册、CHANGELOG、KNOWN_LIMITATIONS、THIRD_PARTY_NOTICES、SBOM 与发行校验值。

## 冻结产物证据

| 项目 | 实际结果 |
|---|---|
| onedir | `artifacts/release/Guixu-0.1.0/`；434 文件；301,370,350 bytes |
| 主 EXE | `Guixu.exe`；SHA-256 `A6D0D437F4B9BB929FFFFEECA8AB07E5FBE603419EB7367F410B28C040C3E0EB` |
| portable ZIP | `Guixu-portable-x64-0.1.0.zip`；SHA-256 `9273371C305CE5B38213DB210D4F78FBFC2CE1FAD3841E2978BE54DDE854E286` |
| 冻结诊断 | exit 0；`frozen=true`、frontend present、resource root=`_internal`、数据库在测试目录且不在安装目录 |
| 冻结文本 worker | exit 0；中文路径/内容，status=`ready`；未启动 GUI |
| 冻结 OCR worker | exit 0；status=`ready`；capabilities=`Pillow, exif-stripped-thumbnail, RapidOCR-CPU` |
| 原生窗口 | title=`归序 Guixu`；WebView2 加载；测试 DB 创建；CloseMainWindow 后 15 秒内正常退出 0 |
| 中文路径解压 | ZIP 解压至 `中文便携-*` 后 `--diagnose` exit 0；静态资源和文档存在 |
| 签名 | `NotSigned`；没有证书，不伪造签名 |
| 安装器 | `BLOCKED_EXTERNAL`；本机 `ISCC.exe` 不存在，未生成 Setup EXE |

自动化 WM_CLOSE 时 WebView2 输出一次 `Failed to unregister class Chrome_WidgetWin_0 (1411)`，但窗口关闭、后端退出和进程码均正常；保留为兼容观察项，不据此宣称多系统兼容。

## 命令与实际结果

| 命令／操作 | 退出结果 |
|---|---:|
| `uv add --dev pyinstaller==6.22.3` | 0；版本写入 pyproject 与 uv.lock |
| `.\scripts\package-windows.ps1` | 0；全测试、onedir、诊断、worker、ZIP、SBOM/hash 通过；明确 warning：Inno Setup 不存在 |
| 最终 `uv run pyinstaller ... packaging/Guixu.spec` | 0；Windows onedir 成功 |
| `uv run --all-extras pytest -q` | 0；119 passed，2 个已知 warning |
| `python scripts/verify.py all` | 0；后端各范围与前端 typecheck/8 tests/build 全通过 |
| 全新 `uv run alembic -x db=<project-test-db> upgrade head` | 0；integrity=`ok`、revision=`0001`、schema version=1、24 表 |
| 最终冻结诊断/TXT worker/OCR worker | 0 / 0 / 0 |
| 最终原生窗口启动与正常关闭 | 0；title/DB/frontend/exit 全部核对 |
| ZIP 中文目录重新解压与诊断 | 0；不依赖构建工作目录 |

### 2026-09-14 维护重建

计划批准幂等恢复与模型连接删除功能合入后重新执行全量验证与 `scripts/package-windows.ps1 -SkipTests`。后端 121 passed，前端 typecheck/11 tests/build 通过；重建后的 onedir 为 434 文件、301,371,902 bytes，`Guixu.exe` SHA-256 为 `A9C412C780DC65A569B738D5B6A1A7439F0C848400A385C9280047BFD4D45FC2`，portable ZIP SHA-256 为 `77E6216B64294E048ED927C9E997CC7428259B9284A7BFD10FB39FC19D2EC393`。本轮打包脚本内冻结诊断与中文 worker 均 exit 0；原生窗口、冻结 OCR 和中文解压路径沿用上方阶段验收基线，未伪记为本轮重跑。

## 尚需外部完成

1. 在安装 Inno Setup 6 的受控 Windows 构建机运行脚本并生成 Setup EXE，再核验安装日志与 hash。
2. 在无 Python/Node 的干净 Windows 用户逐项验收安装、首次启动、纯规则 report_only、copy/move/undo、强制关闭恢复、升级和卸载保留数据。
3. 用 Windows 10/Server/LTSC、高 DPI/多显示器及 WebView2 缺失环境验证提示和安装路径。
4. 提供签名证书后签名并重新生成校验值；当前所有产物明确未签名。
5. 用户选定项目自身发布许可证，并复核 SBOM 中第三方许可证后才可公开分发。
6. 真实 DeepSeek/Qwen、ffmpeg/ffprobe/ASR、物理卷断开与云占位仍沿用阶段 08 的外部阻塞。
