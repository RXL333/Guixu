# 首次分析旧设置兼容与消息展示（2026-09-27）

## 现场证据

- 截图所示会话选中了本地千问 `qwen3-vl:4b-instruct`，20 张照片在当前文件面板可见。
- 只读查询本机 `%LOCALAPPDATA%/Guixu/app.sqlite3`：该会话没有新 Task 或模型调用；`default_settings` 中包含旧字段 `classification_mode`。
- 对该已存 JSON 调用当前 `TaskSettings.model_validate`，得到唯一错误 `classification_mode / extra_forbidden`。首次分析在创建 Task 前读取该设置并直接失败；API 将 ValueError 显示为笼统的“首次整理分析无法完成”。本轮未对用户照片目录执行任何整理操作。
- 前端此前把“请按下面的用户讨论记录提取明确的整理要求……”连同历史消息作为 `/turns` 的 `content` 提交，后端又把它保存为用户消息；重试时历史消息再次拼接，导致截图中的提示词重复。

## 修复

- 已存设置兼容读取仅移除历史 `classification_mode`，然后继续完整校验；新的 TaskSettings 输入仍拒绝该字段和其他未知字段。设置查看、分类语言更新及首次分析共用该兼容读取。
- 首次整理 API 新增可选 `requirements_context`；`content` 只保存用户可见的指令，讨论上下文及提取指令只用于本轮分析。前端排除旧版已保存的内部前缀消息，并去除相同指令的重复项。
- 没有自动改写本机数据库或历史聊天记录。

## 验证与产物

| 命令 | 结果 |
| --- | --- |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/test_settings.py backend/tests/integration/test_first_analysis.py::test_first_turn_scans_real_evidence_and_only_creates_full_preview -q` | 4 passed，exit 0 |
| `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` | 222 passed，2 warnings，exit 0 |
| `npm run test:run`（frontend） | 50 passed，exit 0 |
| `npm run build`（frontend） | 类型检查及生产构建通过，exit 0 |
| `scripts/package-windows.ps1 -SkipTests -SkipInstaller -ReleaseDirectory artifacts/build/model-selector-stage` | 冻结诊断和 worker 冒烟通过；初次 ZIP 因 EXE 短暂被占用而失败。重试 ZIP 压缩及元数据生成成功。 |

用户关闭归序后，已覆盖原便携包 `artifacts/release-agent-chat/Guixu-0.1.0/Guixu.exe` 与 ZIP，哈希与暂存包一致：EXE SHA-256 `7C2AF3EDC15AB0431A3385302D715B79863ADD0BCC045CCEF2A29704130FA4A8`；ZIP SHA-256 `6C82DF99560F2936B748960672CA34B8B83FCA6673C108C66A6B3F8E6063577C`。旧版包留在 `artifacts/build/model-selector-stage/previous-Guixu-0.1.0-20260927`，没有直接递归清理。真实本地千问对 20 张照片的完整分析与方案质量尚未验证，发布判定仍为 NOT RELEASE READY。
