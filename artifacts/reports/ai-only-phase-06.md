# AI-only PHASE 6：批量 AI 文件分类器

日期：2026-09-19  
状态：PASSED

## 完成

- 分类树批准后切换为批量 AI 分类，不再调用本地规则或模态映射。
- 批大小来自模型 profile；含图片的批次限制为最多 8 项，降低视觉上下文和预算风险。
- 每批记录 `AI_CLASSIFY_BATCH_STARTED/COMPLETED/FAILED`，模型失败不会伪造分类或回退本地规则。
- 图片必须返回视觉描述；描述以 `visual_caption` 证据持久化后才能成为分类依据。
- 同扩展名文档可以依据正文进入不同类别；全 JPG 流程通过受控 derivative 与视觉描述完成分类。
- 新增已批准分类树的重试分类 API；只有所有 eligible 文件均有 AI 结果后才进入执行前审阅状态。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q tests/classification/test_ai_file_classifier.py -vv`：退出 0，2 passed。
- `backend/.venv/Scripts/python.exe -m pytest -q tests/classification/test_ai_planner.py tests/classification/test_classification.py tests/models/test_models.py`：退出 0，20 passed。

## 已知失败与后续

- 旧集成测试仍假设 `universal.types` 和无模型模板任务存在，定向集成命令为 4 failed / 2 passed；这些是 AI-only 契约迁移项，不能标为回归通过，将在 PHASE 9 改写。
- 真实 DeepSeek/Qwen 批处理仍因外部服务不可用而未运行。
