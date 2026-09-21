# AI-only PHASE 8：计划批准与执行状态机

日期：2026-09-19  
状态：PASSED

## 根因与修复

- 原实现只在 API 参数中携带 task revision，计划表没有保存 `plan_basis_revision` 与批准时 revision，无法准确区分“任务变了”与“计划批准状态变了”；前端批准后也没有重新读取并核对计划。
- 数据库 schema 升级到 v2，计划持久化 `plan_basis_revision` 与 `approved_task_revision`；提供带 SQLite 一致性备份的 v1→v2 运行时迁移及 Alembic `0002`。
- 批准时原子核对 task revision、plan basis revision、plan ID、plan hash 和 validated 状态。单纯 validated→approved 不修改计划 hash，也不使计划自身过期。
- 执行前再次核对 approved 状态、批准 revision、当前 task revision、plan ID 和 hash。
- taxonomy/classification/review 变化会 supersede 旧计划；源文件和目标事实仍由确定性执行器在操作前验证。
- 前端按推荐顺序执行：获取最新 task → 批准 → 再取同一 plan → 核对 ID/hash/approved → 执行。
- API 客户端保留结构化错误 code；执行页分别解释 `PLAN_NOT_APPROVED`、`PLAN_STALE`、`PLAN_HASH_MISMATCH`、`REVISION_CONFLICT` 及文件/目标类错误。

## 验证

- 临时目录完整 `compile → bad hash reject → approve → GET verified plan → execute → undo`：通过，真实文件仅在执行阶段移动并可撤销。
- 人工 review 改变后旧 plan 被 supersede，批准返回 `PLAN_STALE`：通过。
- `backend/.venv/Scripts/python.exe -m pytest -q tests/integration/test_safe_operations_api.py tests/integration/test_operation_journal.py tests/contract/test_database.py`：退出 0，20 passed（1 个第三方 deprecation warning）。
- `npm run test:run -- --reporter=dot`：退出 0，13 passed。
- `npm run typecheck`：退出 0。

## 安全说明

- 测试只使用 pytest 临时目录，没有读取或移动用户个人文件。
