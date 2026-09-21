# AI-only PHASE 5：AI 分类树规划器

日期：2026-09-19  
状态：PASSED

## 完成

- 新增统一 `AITaxonomyPlanner`，`auto_plan` 和模板模式均依据本地解析后的内容证据请求模型规划分类树。
- 模板仅作为规划指导；不再把模板节点直接当成本地分类结果。
- `fixed_categories` 只固定用户给出的类别，文件归属仍必须由 AI 分类。
- 分类树输出执行稳定 ID、路径字符、深度、同级数和总节点数校验，并记录 `AI_PLANNER_*` 审计事件。
- 规划完成后任务进入可批准的分类树状态，不移动文件。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q tests/classification/test_ai_planner.py tests/classification/test_classification.py -vv`：退出 0，12 passed。
- `npm run test:run -- --reporter=dot`：退出 0，12 passed。
- `npm run typecheck`：退出 0。

## 外部阻塞

- 未提供真实 DeepSeek Key；真实云端规划尚未运行。
- 未检测到可用本地 Qwen 服务；真实本地规划尚未运行。
