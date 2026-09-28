# PHASE C Legacy Product Cleanup 实施计划

## 目标与范围

清理模板、固定分类和旧规则等产品入口；新增任务记录的软删除、批量删除、最近删除、恢复和受限永久删除；简化仍可工作的 AI-only 一次性整理入口。禁止实现 Conversation、Chat、Agent Orchestrator 或新推理架构。

## 关键决策

- 任务删除只修改应用数据库可见性，不调用 FileOperationEngine、Undo 或任何真实文件 API。
- `tasks` 增加非破坏性 soft-delete 字段；正常列表默认排除，最近删除单独查询。
- RUNNING、PAUSE_REQUESTED、RECOVERY_REQUIRED 任务拒绝删除；用户先通过既有 cancel/recover 流程使其稳定。
- 永久删除对存在 plan/operation 安全记录的任务一律阻止，避免级联破坏 journal/undo；只允许清理无执行安全依赖的已 soft-delete 记录。
- 模板表、旧任务 snapshot 和历史字段暂留只读兼容；应用启动不再 seed，新任务/API/UI 不再读写模板。
- 新任务强制 `auto_plan`，只接收 `user_instructions`；底层旧 enum/字段暂留兼容，fixed/template 不再是新产品入口。

## 依赖顺序

1. 锁定全量测试 baseline，并审计 UI/API/schema/runtime 引用。
2. 增加 schema v3、SQLite 自动备份迁移和 repository 删除语义。
3. 增加单删、批量删、最近删除、恢复、重命名及受限永久删除 API 与安全测试。
4. 移除模板 runtime/API/前端入口，保留历史 snapshot/schema 只读兼容。
5. 简化新建整理页面和导航，新增任务记录选择/删除/恢复 UI。
6. 更新契约与测试，运行后端、前端、typecheck、build 和 AI-only 临时目录闭环。
7. 更新 PROJECT_STATUS 与阶段报告；停止，不进入下一阶段。

## 主要影响模块

- 数据库：`contracts/database.sql`、`backend/src/guixu/infrastructure/db/database.py`、migration v3、`repository.py`。
- API：`backend/src/guixu/api/schemas.py`、`app.py`、`application/tasks.py`。
- 前端：`services/api.ts`、`HistoryPage.vue`、`NewTaskPage.vue`、`App.vue`、`router.ts`、相关样式与测试。
- 兼容：旧 task 的 `classification_request_json`、`template_snapshot_json`、taxonomy/plan/operation tables 继续可读。

## 验收

- 单删/批删/最近删除/恢复/受限永久删除均有后端与前端覆盖。
- 删除各状态任务不改变临时目录中文件的路径、数量和 SHA-256。
- 执行中/恢复中任务被拒绝；已执行任务 soft delete 后 journal/undo 仍在。
- 新 UI/新 API 不再依赖模板；旧 template task 详情、taxonomy、plan/执行状态仍可读取。
- RuleEngine、`universal.types` 和 fixed/template 主入口不复活。
- 全量 verify、typecheck、production build、AI-only 端到端测试通过。
