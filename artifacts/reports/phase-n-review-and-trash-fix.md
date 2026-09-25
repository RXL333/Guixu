# PHASE N｜逐文件方案、图片预览与对话永久删除修复

日期：2026-09-25。

## 问题与处理

1. 会话右侧的“整理预览”原先只显示计划摘要，没有读取版本化核心计划中的逐文件操作。现在按当前或选中的历史版本读取不可变计划，列出每个文件的原位置、移动/复制目标或保留状态，并可搜索。
2. “当前文件”原先只显示图标，没有调用图片预览。现在对会话绑定目录中的 JPG、PNG、GIF、WebP、BMP 签发短时预览票据；文件列表及计划条目均可打开图片。请求路径必须位于会话授权目录，未授权、越界及不支持的格式会被拒绝。
3. “最近删除”原先只列 Task，删除后的 Conversation 无法从界面恢复或永久删除。现在单独列出已删除对话，永久删除时清理对话消息、方案和引用；核心 Task、Plan、Operation/Event 日志保留，照片不动。仍需先软删除，才能永久删除。

## 验证记录

| 命令或检查 | 结果 |
|---|---|
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/integration/test_first_analysis.py::test_first_turn_scans_real_evidence_and_only_creates_full_preview backend/tests/security/test_preview_tickets.py -q` | exit 0，3 passed；覆盖逐文件目标与授权图片票据 |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/integration/test_conversational_undo.py::test_permanent_conversation_delete_keeps_executed_file_journal backend/tests/integration/test_first_analysis.py::test_first_turn_scans_real_evidence_and_only_creates_full_preview -q` | exit 0，2 passed；覆盖有执行日志及 Undo 预览的对话永久删除 |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | exit 0，204 passed / 2 warnings |
| `npm run test:run -- --silent`（frontend） | 最终 exit 0，5 files / 43 passed；初次运行因预览按钮名称与 5000 文件选择测试重复而 1 failed，修正后重跑通过 |
| `npm run build`（frontend） | exit 0，Vue typecheck 与 Vite build 通过 |
| `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/package-windows.ps1 -SkipTests -SkipInstaller -ReleaseDirectory 'artifacts\release-agent-chat'` | exit 0；覆盖原 onedir 与 portable ZIP，冻结诊断及 worker 冒烟通过 |
| `backend/.venv/Scripts/python.exe scripts/audit_release_secrets.py artifacts/release-agent-chat/Guixu-0.1.0 artifacts/release-agent-chat/Guixu-portable-x64-0.1.0.zip` | exit 0；各扫描 434 项，已知密钥签名和开发资产 0 命中 |
| `git diff --check` | exit 0；仅 LF/CRLF 提示 |

便携包：`artifacts/release-agent-chat/Guixu-portable-x64-0.1.0.zip`，SHA-256 `767FA39982BDB64354C1024B2B025FF612C9931EF27FE4B8B04647627FBF2FF6`。桌面程序：`artifacts/release-agent-chat/Guixu-0.1.0/Guixu.exe`，SHA-256 `7EC8E2CDE494CA4ED50330529D3A03F0D109369239749E8B28C15A14B850CCB4`。

三张用户截图的临时文件在本轮已不存在，因此未做截图逐像素对照。已用后端 API、前端交互测试、生产构建及冻结诊断验证；真实桌面界面点击与安装器未验收。
