# Legacy Product Cleanup 迁移说明

自 2026-09-20 起，新任务只接受 `auto_plan + user_instructions`。分类模板、fixed categories 配置器与 RuleEngine 不再是运行时产品能力。

为保证旧任务和安全审计可读，当前数据库暂留 `template_versions`、`tasks.template_snapshot_json`、`tasks.rules_snapshot_json` 以及 `TaskSettings.classification_source` 的旧枚举值。它们属于 **legacy read compatibility**：应用不再 seed 模板、不注册模板 API，新任务服务拒绝 template/fixed 请求，repository 也不再为新任务读取模板表，前端不展示相关入口。schema v3 迁移会为仅保存 `template_key` 的旧任务补齐当时可用的模板快照。

旧任务已经持久化的 taxonomy、classification、plan、operations 和 operation events 是历史真相；打开历史不依赖模板服务。不得为“清理”而级联删除仍承担 plan/journal/undo 安全性的记录。

任务记录删除使用 `deleted_at` soft delete。普通列表隐藏、最近删除可恢复；单项和批量永久删除只允许没有 plan 安全记录的已删除任务，整批预检失败时不会部分删除，并且任何删除任务 API 都不得调用真实文件执行器或 Undo。
