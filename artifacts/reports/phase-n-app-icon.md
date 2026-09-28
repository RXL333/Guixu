# 应用图标替换（2026-09-25）

用户提供的原图保存在 `packaging/assets/source-icon.png`，SHA-256 为 `6396e3da253ae1a6a0c216c60869f0a79f274677fa6383af70d6217e2917209a`。`scripts/generate_app_icon.py` 根据原图前景轮廓去除外围白底，生成透明的 `guixu-icon.png`、16/24/32/48/64/128/256 像素 Windows `guixu.ico`、页面 `app-icon.png` 和 `favicon.png`。

PyInstaller EXE 使用 `guixu.ico`；pywebview WinForms 从 EXE 提取窗口图标。Inno Setup 的 `SetupIconFile` 使用同一个 ICO，桌面和开始菜单快捷方式继承 EXE 图标。前端 favicon 与侧栏品牌标识改用生成的 PNG，旧 SVG 已移除。

| 验证 | 结果 |
|---|---|
| `uv run --all-extras python ../scripts/generate_app_icon.py` | exit 0；已目视核对生成的 1024 与 64 像素 PNG |
| ICO 帧检查 | 16、24、32、48、64、128、256 均存在；PNG 透明角像素 alpha 0 |
| `python scripts/verify.py all` | exit 0；前端 44 passed、production build 成功 |
| Windows 便携包覆盖构建 | exit 0；覆盖 `artifacts/release-agent-chat/Guixu-0.1.0` 和 `Guixu-portable-x64-0.1.0.zip`；冻结诊断与 worker 冒烟通过 |
| 包内核查 | EXE 图标已提取核对，见 `artifacts/reports/app-icon-exe.png`；前端图标资源存在，EXE 与 ZIP 哈希均匹配 `SHA256SUMS.txt` |

本机没有 Inno Setup 6，安装器未生成；现有 1.0 发布门状态不变。
