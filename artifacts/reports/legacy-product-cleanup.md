# PHASE C — Legacy Product Cleanup

日期：2026-09-20  
结论：**PASSED**。本阶段只清理旧产品形态并补齐任务记录删除能力；未实现 Conversation schema、Chat UI、Agent Orchestrator、Tool Calling、增量重规划或对话记忆。

## 1. 修改前的旧产品入口

修改前主导航和路由仍包含分类模板；新建任务暴露 template、fixed categories、多种分类来源及内部技术概念；模板 API/service/startup seed 仍可作为运行时能力；任务记录没有 soft delete、最近删除、批量操作和恢复。

基线命令：`.\backend\.venv\Scripts\python.exe scripts\verify.py all`，退出 0；后端各既有分组通过，前端 16 passed，typecheck/build 退出 0。

## 2. 删除的 UI

- 删除 `TemplatesPage.vue`、`TemplatePicker.vue`、模板卡片/详情/使用/复制/创建/筛选入口。
- 删除旧 `RulesPage.vue` 和规则导航；没有空壳页面。
- 主导航改为工作台、整理记录、最近删除、模型连接、设置。
- `/templates` 作为旧书签兼容路由重定向工作台；`/rules` 不再注册。
- 任务主列表不再展示模板名、规则模式或 classification mode。

## 3. 删除的 API

运行时已删除全部 `/api/v1/templates*` endpoint、模板 import/duplicate DTO、`TemplateService` 与启动 seed。此前 AI-only 阶段已删除 rules API；本阶段确认未恢复。导出的 `contracts/openapi-runtime.json` 不含 templates/rules 路径。

## 4. Deprecated / legacy read-only API

没有保留模板只读 API。旧任务详情、taxonomy 与 plan 继续通过既有 task API 读取持久快照，不需要模板 endpoint。旧静态 `contracts/openapi.json` 是历史设计合同，不是运行时导出；当前合同以 `contracts/openapi-runtime.json` 为准。

## 5. 模板系统处理结果

已删除运行时服务、API、seed、前端 store 调用和全部产品入口。`template_versions`、`tasks.template_snapshot_json` 与旧 source enum 暂留数据库兼容；新任务服务拒绝 template/fixed 请求，repository 创建新任务也不再查询模板表。

## 6. 暂留数据库字段

以下字段/表只用于旧任务历史读取：`template_versions`、`tasks.template_snapshot_json`、`tasks.rules_snapshot_json`、旧 `classification_request_json` 内容，以及 `classification_source` 的 template/fixed enum。taxonomy、classifications、plans、operations、operation_events 不属于待清理旧产品数据，继续作为历史与安全事实保留。

## 7. RuleEngine / universal.types 状态

运行时不存在 RuleEngine、rules route/UI、`classify_universal_types` 或 Plan Compiler 类型 fallback；新任务不会按扩展名、文件名或路径决定类别。`seed/templates.json` 与早期设计/评测资料中的 `universal.types` 仅为历史资料，不被应用启动或新任务读取。

## 8. 新建整理流程

页面统一为“开始一次 AI 整理”：选择文件夹 → 输入可留空的整理要求 → 选择并查看模型连接/text/vision 能力 → 最大深度 1/2/3（默认 2）→ 快速/标准/深入（默认标准）→ 预览移动/复制/只生成报告 → 开始 AI 分析。生产禁用的 direct move 没有重新开放。

## 9. 任务删除实现

`tasks` 新增 `deleted_at`、`deletion_source`、`delete_reason`。默认列表排除软删除记录；删除会增加 revision 并写入 task event。条目菜单提供重命名与删除，确认文案明确“只删除归序中的任务记录，不会删除或移动磁盘上的文件”。

## 10. 批量删除实现

整理记录支持 checkbox、按当前筛选结果全选/取消选择和批量删除。repository 在一个事务中完成整批预检与更新；任一任务缺失或处于危险状态时整批失败。

## 11. 最近删除实现

`/trash` 查询 `view=deleted`，支持查看、多选、批量恢复、单项/批量永久删除。普通任务列表、最近删除和 all 视图由同一 repository 明确区分。

## 12. 恢复实现

恢复只清空 soft-delete 元数据、增加 revision 并写 task event；不调用扫描、执行或 Undo。单项和批量恢复均已覆盖。

## 13. 永久删除规则

只允许永久删除已经 soft delete 且没有 plan 安全记录的应用内部任务。单项和批量永久删除均先全量校验；任一记录仍有 plan/journal/Undo 依赖时返回 `TASK_SAFETY_HISTORY_RETAINED`，不产生部分删除。UI 二次确认明确不会删除磁盘文件、且历史信息可能无法恢复。

## 14. 真实磁盘文件安全验证

`test_task_record_deletion.py` 在临时目录记录相对路径与 SHA-256，覆盖单删、批删、恢复、单项及批量永久删除；操作前后路径、数量、内容 hash 一致。删除 endpoint 不引用 `FileOperationEngine`、executor 或 undo。

## 15. 旧任务兼容测试

测试构造旧 template task 及其 snapshot、taxonomy、category、plan，确认 task 详情、历史 taxonomy、plan 均可打开，且无需模板 API。v2 → v3 迁移会在兼容表仍存在时把只有 `template_key`、缺少 snapshot 的旧任务快照化。

## 16. 当前 AI-only 整理闭环

`backend/tests/integration/test_ai_only_end_to_end.py` 使用临时目录完成选择文件、user instructions、AI Planner、AI Classifier、review、compile、approve、execute；位于全量 92 passed 分组中并通过。未增加本地语义 fallback。

## 17. 后端测试结果

最终命令 `.\backend\.venv\Scripts\python.exe scripts\verify.py all` 退出 0。后端分组：7 passed；92 passed；16 passed；19 passed；15 passed；10 passed。删除/迁移定向测试 10 passed，任务删除文件单独 7 passed。

第一次全量回归曾发现 `test_desktop_security.py` 仍写死 schema v2；同步到 schema v3 后重新运行全量通过。未把失败轮次记为通过。

## 18. 前端测试结果

Vitest：3 files、20 tests 全部通过。覆盖单删确认、筛选后批量选择/删除、最近删除恢复、批量永久删除、危险状态禁用、模板/规则导航消失、旧模板路由重定向及简化新建整理页。

## 19. Typecheck

`npm --prefix frontend run typecheck` 退出 0。

## 20. Production build

`npm --prefix frontend run build` 退出 0；Vite 处理 1710 modules，生成 `frontend/dist`。

## 21. 数据库 migration

schema 版本从 v2 升至 v3；Alembic revision `0003_task_soft_delete.py`。迁移前调用 SQLite backup API 生成非覆盖备份，新增字段和索引采用非破坏性 ALTER/CREATE IF NOT EXISTS；重复初始化不再生成第二份迁移备份。migration 测试确认旧模板快照回填、旧数据可读、Alembic head 为 0003。

## 22. 当前 legacy debt

- `template_versions`、rules 表、旧 snapshot 字段及旧 enum 尚未物理删除，原因是旧库升级和历史查看兼容。
- `AITaxonomyPlanner` 仍可读取已经存在的 template/fixed 历史任务，防止旧的中断任务在查看/恢复时崩溃；新建入口无法进入这些分支。
- 早期设计文档、静态 `contracts/openapi.json`、seed/evaluation fixture 仍含模板或 `universal.types` 术语，均已标为历史或在本报告限定为非运行时资料；后续 schema cleanup 才能删除。
- 既有 pytest 在 Windows reparse 临时目录回收时偶发 warning；另有第三方 deprecation 与刻意触发的 decompression-bomb warning，不影响测试退出码。

## 23. 下一阶段 Conversation Schema 推荐切入点

下一阶段应从独立的 Conversation/Message schema 与生命周期开始，将 conversation 关联到现有 task，而不是替换 Task、Planner、Classifier、Plan、Execution、History 或 Undo。继续复用本阶段形成的 active/deleted task 查询与持久安全日志边界。该工作不属于 PHASE C，本阶段没有实现。

## 完成标准核对

- [x] 单删、批删、最近删除、恢复、受限永久删除
- [x] 删除不改变磁盘路径、数量或 hash
- [x] RUNNING / PAUSE_REQUESTED / RECOVERY_REQUIRED 与活跃 worker 不能危险删除
- [x] 已执行任务 soft delete 保留 plan/journal/Undo 依赖；永久删除被阻止
- [x] 模板和自动规则从主产品、导航、API、新任务 runtime 消失
- [x] fixed categories 不再是 UI 入口；新任务只接受 auto plan + user instructions
- [x] RuleEngine 与 universal.types 未进入运行时
- [x] 旧任务、数据库升级和 AI-only 闭环通过
- [x] 后端、前端、typecheck、production build 通过
- [x] PROJECT_STATUS 与本报告已更新
