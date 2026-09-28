# Windows 打包

```powershell
.\scripts\package-windows.ps1
```

脚本执行前端安装与构建、验证、PyInstaller onedir、冻结诊断与 worker 冒烟，然后生成 ZIP、可用时生成 Inno Setup 安装器，并写入 SBOM 与 SHA-256。默认产物统一放在 `artifacts/release/`；再次打包覆盖同名便携包，不另开新的发行目录。完整目录和 ZIP 必须整体交付。

打包资源包括 `contracts/`、运行时必需的 `seed/`、`frontend/dist/`、产品使用说明和第三方声明。业务数据库写在 `%LOCALAPPDATA%\Guixu`，不写入安装目录。
