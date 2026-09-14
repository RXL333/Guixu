# 归序发布就绪判定

更新时间：2026-09-14（阶段 09 最终）

## 判定

**NOT READY FOR PUBLIC RELEASE — VERIFIED WINDOWS DEV BUILD**

源码与 Windows x64 onedir/portable 已真实构建并在本机通过冻结诊断、worker、OCR、原生 WebView2 启动/关闭和中文解压路径验证。P0 自动化安全门通过，未发现覆盖、越权路径、未授权出站、Key 泄漏或绕过批准。

但安装器、签名、干净 Windows 用户矩阵、真实模型质量和部分外部组件/故障环境仍无证据。当前不是 beta/release，生产 `direct_move` 保持关闭，只能用备份副本或项目测试目录。

## 可运行产物

| 产物 | 状态 | 说明 |
|---|---|---|
| `artifacts/release/Guixu-0.1.0/` | VERIFIED_LOCAL | Windows x64 onedir，必须整体交付；维护版 434 文件，301,371,902 bytes |
| `artifacts/release/Guixu-0.1.0/Guixu.exe` | VERIFIED_LOCAL / UNSIGNED | 维护重建后冻结诊断与 worker 通过；SHA-256 `A9C412C780DC65A569B738D5B6A1A7439F0C848400A385C9280047BFD4D45FC2` |
| `artifacts/release/Guixu-portable-x64-0.1.0.zip` | VERIFIED_LOCAL | 维护重建产物；SHA-256 `77E6216B64294E048ED927C9E997CC7428259B9284A7BFD10FB39FC19D2EC393` |
| `Guixu-Setup-0.1.0-unsigned.exe` | NOT BUILT | 本机没有 Inno Setup 6；`.iss` 存在不计作安装器 |
| `SBOM.json` / `SHA256SUMS.txt` | GENERATED | 锁文件依赖清单与逐文件/归档 hash；发布前需人工许可证复核 |

## 已通过的发布门

- 后端 121 passed；前端 typecheck、11 tests、production build；统一验证 exit 0。
- 真实 C:→D: 跨卷 copy/verify/publish/delete 未 skip；no-clobber、锁、竞态、恢复、撤销冲突通过。
- 新 SQLite schema version 1、Alembic `0001`、24 表与 `integrity_check=ok`；迁移备份 API 测试通过。
- 10,000 文件扫描和 5,000 行查询；浏览器 100 页/10,000 全选/搜索/console 验证。
- 冻结资源不依赖 cwd；数据与缓存不写安装目录；同一 EXE worker 不递归启动 GUI。
- WebView2 152.0.4191.66 本机可用；缺失检测、官方在线/离线说明和 per-user Inno 配置已实现。
- OCR 资源确实打包且冻结图片解析 `ready`；未捆绑 Qwen/CUDA/ffmpeg/ASR。

## 发布阻塞

1. **Installer**：需要 Inno Setup 6 构建真实 Setup EXE，并在干净用户环境验证安装/升级/卸载保留数据。
2. **Signature/license**：没有代码签名证书；项目自身许可证未声明；第三方 SBOM 需人工复核。
3. **Clean environments**：无 Python/Node 的 Windows 10/11、Server/LTSC、高 DPI/多显示器、WebView2 缺失路径未覆盖。
4. **Real models**：无用户授权的 DeepSeek Key/Qwen 服务，未运行现实语义金标准与公平对比。
5. **Media/resources**：ffmpeg/ffprobe 和已校验本地 ASR 缺失，视频/语音增强为 partial/弃判。
6. **Dedicated failure systems**：物理卷断开、云占位和第三方同步客户端冲突未测试。

## 晋级条件

只有上述安装/签名许可/干净机核心矩阵完成，且真实模型或明确承诺范围的规则-only 质量门通过后，才能评估 beta。所有必需桌面与发布证据完成前不能标记 release，也不能开放生产 `direct_move`。
