# AI-only PHASE 2：移除本地语义分类

日期：2026-09-15  
状态：PASSED

## 完成

- 删除运行时 `RuleEngine`、RuleService、规则 API、规则中心页面与“审阅结果转扩展名规则”。
- 删除 `classify_universal_types` 与 plan compiler 的 `TYPE_CATEGORIES` 模态目录 fallback。
- 删除 `classification_mode` 及 rules_first/ai_first/rules_only 设置契约。
- 新任务必须选择启用的 AI model profile；`universal.types` 明确返回 `LEGACY_TEMPLATE_NOT_ALLOWED`。
- `universal.types` 不再出现在模板列表；旧 seed/数据库记录仅供历史兼容。
- 无 approved taxonomy 时禁止编译计划，返回 `TAXONOMY_NOT_APPROVED`。
- 新任务页默认 auto_plan 且不携带 template key；无模型不能提交。
- 原测试文件保留并改为 AI-only 架构回归。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q tests/unit/test_settings.py tests/classification/test_classification.py`：退出 0，10 passed。
- `npm run test:run -- --reporter=dot`：退出 0，12 passed。
- `npm run typecheck`：退出 0。

## 未完成 / 后续

- 全量旧 integration 测试仍需在后续阶段迁移到 fake AI 主链路。
- Planner、vision input、consent UI 与 batch classifier 尚未实现；当前切断 fallback 后相关任务会显式停止，而非伪装成功。
