# 开发环境与启动

项目要求 Windows x64、CPython 3.12、uv、Node/npm；原生窗口需要 WebView2。后端依赖以 `backend/uv.lock` 为准，前端以 `frontend/package-lock.json` 为准。

```powershell
.\scripts\doctor.ps1
uv --directory .\backend sync --all-extras
npm.cmd --prefix .\frontend ci
.\scripts\run-dev.ps1
```

原生桌面入口：`.\scripts\run-desktop.ps1`。开发服务器使用本地 token；生产入口只监听 `127.0.0.1`。

不要自动安装 CUDA、Qwen 权重、ffmpeg、ASR 模型或全局 Python。旧版模板/RuleEngine 迁移记录见 [归档](../archive/legacy-organizer/LEGACY_PRODUCT_CLEANUP.md)。

继续阅读：[测试](testing.md)、[打包](packaging.md)、[发布](release.md)。
