# AI-only PHASE 12：Windows 桌面与发行产物

日期：2026-09-19  
状态：BLOCKED_EXTERNAL（onedir/portable 与冻结诊断通过；可见桌面人工验收、安装器和签名未完成）

## 已通过

- `scripts/package-windows.ps1 -SkipTests -SkipInstaller`：退出 0。
- 前端 production build：退出 0，1712 modules transformed。
- PyInstaller 6.22.3 Windows x64 onedir：构建成功。
- 冻结 `Guixu.exe --diagnose`：退出 0；`frozen=true`、Vue frontend present、数据库位于项目测试目录且不在安装目录、WebView2 Runtime `153.0.4234.32`。
- 冻结中文 TXT parser worker：由打包脚本运行，退出 0。
- portable ZIP：构建成功。

## 产物

- onedir：`artifacts/release/Guixu-0.1.0/`，434 files，301,392,607 bytes。
- `Guixu.exe` SHA-256：`399A4ACA10315928E0CE5F26BEBBF5C483027BF0FF96978B16CAF5C2FD067000`。
- portable ZIP：`artifacts/release/Guixu-portable-x64-0.1.0.zip`，144,082,963 bytes。
- ZIP SHA-256：`A8298CCDEB75BA45CF287CFE47F24F28DB84E94A36011F346D73D50B090B9E4A`。
- SBOM 与 `SHA256SUMS.txt` 已由打包脚本重建。

## 未通过／外部阻塞

- 隐藏窗口 smoke 能启动进程并在项目测试目录创建数据库，但隐藏模式没有可检查的主窗口句柄；等待后强制结束，exit `-1`。因此本轮不能声明可见 pywebview 完整人工流程通过。
- 本机未安装 Inno Setup 6（`ISCC.exe` 不存在），未生成 Setup EXE。
- `Guixu.exe` Authenticode 状态为 `NotSigned`，没有签名证书。
- 未进行无 Python/Node 干净机、Windows 10/Server/LTSC、高 DPI/多显示器、安装/升级/卸载验收。

## 真实性说明

- 版本继续保持 `0.1.0 dev`，不会把 onedir/portable 误称为已验证安装器或正式 0.2.0。
