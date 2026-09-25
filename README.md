# 归序 Guixu

归序是一个 local-first 的 Windows AI 文件整理器：只读扫描并提取内容证据，由 AI 生成受限的“类别 ID + 证据”，经人工审阅和计划 hash 批准后，才由安全执行器复制或移动。目标冲突永不覆盖，操作持久记录并可在磁盘事实允许时撤销。

当前版本：`0.1.0 dev`。源码闭环和 Windows onedir 构建已实现；1.0 最终验收仍为 **NOT RELEASE READY**，以 [当前验收矩阵](docs/RELEASE_ACCEPTANCE.md) 和 [阶段报告](artifacts/reports/guixu-1.0-final-acceptance.md) 为准。请勿因生成了 EXE 就直接对唯一副本或个人根目录试用。

## 快速入口

- 用户操作：[docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- 开发、测试与打包：[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- 架构与安全：[docs/02_ARCHITECTURE.md](docs/02_ARCHITECTURE.md)、[docs/08_SAFETY.md](docs/08_SAFETY.md)
- 实现架构快照：[docs/IMPLEMENTATION_ARCHITECTURE.md](docs/IMPLEMENTATION_ARCHITECTURE.md)
- 接口与契约：[docs/07_API.md](docs/07_API.md)、[contracts/openapi.json](contracts/openapi.json)
- 逐阶段真实结果：[PROJECT_STATUS.md](PROJECT_STATUS.md)、[artifacts/reports](artifacts/reports)
- 已知限制：[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)

## 开发启动

要求 Windows x64、Python 3.12、uv、Node/npm：

```powershell
.\scripts\doctor.ps1
.\scripts\run-dev.ps1
```

原生桌面入口：

```powershell
.\scripts\run-desktop.ps1
```

完整验证与 Windows onedir/便携包构建：

```powershell
python .\scripts\verify.py all
.\scripts\package-windows.ps1
```

构建脚本只在当前项目的 `artifacts/build`、`artifacts/release` 和 `artifacts/test-workspaces` 下产生测试／发行文件。安装版默认写入当前用户目录，业务数据使用 `%LOCALAPPDATA%\Guixu`，卸载默认保留数据。

## 不可绕过的边界

- AI 不返回路径、不执行代码、不移动文件。
- 未授权不上传文件全文或媒体；Key 不写数据库、日志、报告或浏览器持久存储。
- `direct_move` 在发布门未满足前保持关闭。
- 不自动下载 Qwen/ASR 大模型、CUDA、ffmpeg 或驱动；缺组件显示 unavailable/partial。
- 仅用备份副本、临时目录或 `artifacts/test-workspaces` 验证。
