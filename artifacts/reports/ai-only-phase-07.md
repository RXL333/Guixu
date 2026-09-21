# AI-only PHASE 7：模板、新建任务与分类树流程

日期：2026-09-19  
状态：PASSED

## 完成

- 模板卡片支持鼠标、hover、键盘焦点和 Enter/Space 查看详情；详情展示适用模态、AI 能力要求、建议分类结构与正反示例。
- “使用此模板”会带 `template_key` 进入新建任务；“复制并自定义”生成用户模板版本并提供 JSON 编辑保存。
- 新建任务默认选择“AI 智能整理”，并提供模板指导与用户固定类别两种模式；三者都由 AI 判断文件归属。
- 新建任务增加用户整理要求、模型能力状态、1～3 级深度、分析强度、处理方式与显式内容出站授权。
- 创建任务后先按同一隐私预算生成并提交 scope hash 授权，再启动 AI 分析；未勾选授权不能提交。
- 分类树批准前支持重命名、增加、删除、调整父级并保存为新版本；旧草稿标记为 superseded。
- 分析页显示 AI Planner 与批次分类事件，不再把过程描述成“本地分类”。
- 首页产品表达改为“AI 读懂内容后整理”，移除“纯类型报告”定位。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q tests/classification/test_ai_planner.py tests/classification/test_ai_file_classifier.py tests/classification/test_classification.py`：退出 0，15 passed。
- `npm run test:run -- --reporter=dot`：退出 0，13 passed。
- `npm run typecheck`：退出 0。
- `npm run build`：退出 0，Vite production build 成功。

## 外部阻塞

- 真实 DeepSeek/Qwen 调用与 pywebview 人工交互仍未运行；将在对应阶段按条件补证。
