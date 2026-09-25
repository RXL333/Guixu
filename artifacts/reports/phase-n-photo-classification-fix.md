# PHASE N｜真实照片整理阻断修复

日期：2026-09-24。范围：`D:\Media\Photos\Nikon_z50照片\测试`。用户消息中的 `Nikon\_z50照片` 与本机实际目录 `Nikon_z50照片` 不同；应用已有授权绑定后者。

## 根因与修复

1. 最新 48 JPG 方案已经完成分类并获批准，但 `operations.reason` 未持久化。16 项安全跳过操作的原始原因是 `UNSUPPORTED_OR_UNDECIDED`；重载后变为 `null`，使批准计划哈希失配。旧失败轮次 48 项均为 `PLANNED`，没有移动照片。
2. 首次执行失败的轮次推进了会话 context revision，原批准方案再次执行会报 `PLAN_CONTEXT_STALE`。现在仅在失败轮次仍是当前轮次、同一方案、所有 operation 均为 `PLANNED` 且 Task revision 未变化时，复用该轮次重试。每次执行仍先进行文件状态重验证。
3. schema v11 / Alembic 0011 增加 `reason`；旧 skip/noop 只做确定性恢复，随后仍以原批准哈希检验。不能复原的旧计划继续被拒绝。应用升级前自动生成 SQLite 一致性备份。

## 命令与结果

| 命令或检查 | 结果 |
|---|---|
| `python -m pytest backend/tests/integration/test_operation_journal.py backend/tests/contract/test_database.py -q` | exit 0，20 passed |
| `python -m pytest backend/tests/integration/test_first_analysis.py backend/tests/integration/test_post_execution_conversation.py -q --disable-warnings` | exit 0，16 passed |
| `python -m pytest backend/tests/integration/test_first_analysis.py::test_first_plan_can_be_explicitly_approved_and_executed -q --disable-warnings` | exit 0，1 passed；覆盖零操作失败后重试 |
| 旧真实数据库的隔离副本迁移后 `verify_plan_hash` | 48 项，true；16 个 skip 原因恢复一致；临时目录清理曾报 Windows 文件占用，但迁移校验已完成 |
| 真实会话首个 API 重试 | HTTP 409 `PLAN_CONTEXT_STALE`，照片 48/48、哈希不变；据此补上安全重试路径 |
| 修复后 `POST /api/v1/conversations/{id}/plan-versions/{id}/execute` | HTTP 200；原 ExecutionRound #1 `COMPLETED` |
| 真实操作日志与磁盘核对 | 32 `move/COMMITTED`，16 `skip/SKIPPED`；前后 JPG 都为 48，文件名及各文件 SHA-256 不变；根目录保留 16 JPG |
| 剩余 16 张的显式范围复核 | 分类模型调用 1 次成功；生成 DELTA v2，16 项 move；批准和执行 API 均 HTTP 200，ExecutionRound #2 `COMPLETED` |
| 最终真实目录核对 | 两轮共 48 张 `move/COMMITTED`；根目录 JPG 为 0，递归 JPG 48；文件名与逐文件 SHA-256 映射不变 |
| `powershell -ExecutionPolicy Bypass -File .\scripts\package-windows.ps1 -SkipTests -SkipInstaller -ReleaseDirectory artifacts\release-photo-fix` | exit 0；production build、PyInstaller、frozen diagnose 与 worker 冒烟通过 |
| `python -m pytest backend/tests -q --disable-warnings` | 首次 exit 1：旧数据库版本断言 10；更新为 11 后重跑 exit 0，201 passed / 2 warnings |
| `npm.cmd run test:run`（frontend） | exit 0，5 files / 39 tests passed |
| `git diff --check` | exit 0；仅有工作树 LF/CRLF 提示 |

测试输出存在既有 pytest Windows reparse 临时目录清理警告和 Node engine 警告，均未使以上验证失败。未运行全量回归；新冻结包尚未进行可见桌面人工操作验收。Inno 安装器、签名与干净机验收仍未完成。

## 产物与恢复点

- 桌面程序：`artifacts/release-photo-fix/Guixu-0.1.0/Guixu.exe`
- 便携包：`artifacts/release-photo-fix/Guixu-portable-x64-0.1.0.zip`
- SHA-256：EXE `249BB37FFC2793F9E52D2BDC84A71867DFBA215A3F1EE67C3C9FFB7420F5056E`；ZIP `9E63F781775D1B28578052DE347E3DF44029CBD8C0E0B6D5E29BDEC13D35001F`。
- 当前用户数据库：`%LOCALAPPDATA%/Guixu/app.sqlite3`，schema v11；升级前备份位于其 `backups/` 子目录。
- 当前真实照片目录：48 张全部在分类子目录；根目录无 JPG。第一轮安全保留的 16 张通过第二轮显式范围模型复核、版本化 DELTA 方案及批准后移动。两个执行轮次均为 `COMPLETED`，两个核心计划均为 `finished`。
