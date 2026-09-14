# 开发、验证与打包

## 工具链

- Windows x64
- CPython 3.12
- uv（后端以 `backend/uv.lock` 为准）
- Node/npm（前端以 `frontend/package-lock.json` 为准）
- 可选 Inno Setup 6（生成安装程序）
- WebView2 Evergreen Runtime（原生窗口）

```powershell
.\scripts\doctor.ps1
uv --directory .\backend sync --all-extras
npm.cmd --prefix .\frontend ci
```

不要自动安装 CUDA、Qwen 权重、ffmpeg、ASR 模型或全局 Python。新增依赖先核对官方文档，再用锁文件记录实际解析版本。

## 启动

开发前后端：`.\scripts\run-dev.ps1`。原生 pywebview：`.\scripts\run-desktop.ps1`。开发服务器使用显式本地 token；生产入口生成随机 token、仅监听 `127.0.0.1`、不启用 reload/devtools/mock/typed grants。

## 验证

```powershell
python .\scripts\verify.py all
uv --directory .\backend run --all-extras pytest -q
```

测试必须只用 pytest 临时目录或 `artifacts/test-workspaces`。阶段 08 的许可样本与基准可由以下命令重建，但发布结果生成后不得为提高指标而修改 gold：

```powershell
python .\scripts\create_acceptance_samples.py
python .\scripts\run_phase08_benchmarks.py
```

## Windows 构建

```powershell
.\scripts\package-windows.ps1
```

脚本顺序为 npm ci/build → 全量验证 → PyInstaller 6.22.3 onedir → 冻结资源/AppData诊断 → 同 EXE worker 实测 → 完整目录 ZIP → 若存在 ISCC 则 Inno Setup → SBOM/SHA-256。

产物：

- `artifacts/release/Guixu-0.1.0/`：必须整体交付的 onedir。
- `artifacts/release/Guixu-portable-x64-0.1.0.zip`：完整便携目录压缩包。
- `artifacts/release/Guixu-Setup-0.1.0-unsigned.exe`：仅当 Inno Setup 实际成功时存在。
- `artifacts/release/SBOM.json`、`SHA256SUMS.txt`。

`.spec` 将 contracts、seed、frontend/dist、RapidOCR 数据和 PyInstaller 自动发现的 DLL 放入 `_internal`。运行时资源从冻结的 `__file__`/`_MEIPASS` 定位，数据库只写 AppData。冻结 worker 使用 `Guixu.exe --worker`，不会递归启动 GUI。

Inno 安装为 per-user（`PrivilegesRequired=lowest`），默认目录 `%LOCALAPPDATA%\Programs\Guixu`；卸载不删除 `%LOCALAPPDATA%\Guixu`。WebView2 在线/离线资源均未随仓库下载：在线使用 Microsoft Evergreen 页面，离线需另行取得官方 x64 Standalone Installer 并记录版本/hash/许可。

## 数据库版本

`schema_metadata` 是运行时版本门，当前版本 1。未来新增迁移必须先调用 `Database.backup_for_migration()`，验证备份 `integrity_check`，再在单个版本步骤中迁移；失败时保留备份并禁止文件操作。Alembic 仍用于开发环境全新/受控迁移。

## 发布纪律

Windows 包必须在 Windows x64 构建。安装、首次启动、中文路径、纯规则离线、样本 copy/move/undo、恢复、升级/卸载保留数据要在干净用户环境逐项留证。没有证书就标注未签名；脚本存在不等于 EXE/安装器通过。
