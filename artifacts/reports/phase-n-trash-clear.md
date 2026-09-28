# 最近删除清空修复与本机处理（2026-09-25）

## 原因和处理

截图对应本机应用数据中 15 条已删除任务及 6 条已删除对话。原“永久删除记录”会拒绝有 Plan 或 ConversationFile 安全依赖的任务；批量接口遇到一条受保护记录即整体返回 409。保留此安全约束，新增 `POST /api/v1/trash/clear` 和“清空最近删除”按钮。

清空时先永久删除已删除对话，随后永久删除无安全依赖的任务；需要计划/执行/撤销依据的任务标记为 `trash_cleared`，仅从最近删除列表移出。响应分别返回永久删除任务、保留安全记录和永久删除对话的数量，`disk_files_changed=false`。重复调用返回零计数。既有单条/批量永久删除的安全阻断保持不变。

## 本机数据结果

清空前使用 SQLite backup API 生成 `%LOCALAPPDATA%\Guixu\backups\before-trash-clear-20260925-135555.sqlite3`，备份 `PRAGMA integrity_check=ok`。执行后：7 条任务和 6 条对话永久删除；8 条任务保留安全历史并从列表移出；最近删除任务/对话均为 0。清空前后方案数量均为 16，操作记录均为 723；清空后数据库 `integrity_check=ok`。没有访问或移动照片文件。

## 验证与发行

| 命令 | 结果 |
|---|---|
| `uv run --all-extras pytest tests/integration/test_task_record_deletion.py -q` | 8 passed，exit 0 |
| `npm.cmd test -- --run tests/workflow-ui.test.ts` | 18 passed，exit 0 |
| `python scripts/verify.py all` | exit 0；前端 44 passed，production build 成功 |
| `uv run --all-extras python ../scripts/export_runtime_contract.py` | exit 0，`contracts/openapi-runtime.json` 已更新 |
| `.\scripts\package-windows.ps1 -SkipTests -SkipInstaller -ReleaseDirectory 'artifacts\release-agent-chat'` | exit 0；覆盖原 onedir/ZIP，冻结诊断和 worker 冒烟通过；`SBOM.json` 与 `SHA256SUMS.txt` 生成 |

本次覆盖 `artifacts/release-agent-chat/Guixu-0.1.0/` 与同目录便携 ZIP，不生成安装器。新版 `Guixu.exe` 已重新启动；可见界面的人工点击复核未执行。真实模型与干净 Windows 环境仍按原发布门追踪。
