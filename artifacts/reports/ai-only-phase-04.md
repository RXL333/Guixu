# AI-only PHASE 4：模型能力与视觉输入

日期：2026-09-15  
状态：PASSED

## 完成

- 模型 profile 增加任务能力 gate：所有 AI 任务要求 text/json_mode=supported；包含图片时额外要求 vision=supported。
- unknown 能力返回 `AI_CAPABILITY_UNVERIFIED`，unsupported/error 返回 `AI_CAPABILITY_MISMATCH`。
- 扫描后按全部 eligible 文件模态验证，不受前 500 项分页限制；失败记录 `AI_CAPABILITY_MISMATCH` 事件。
- 图片分类实际读取 Parser 生成的受控 derivative，以 data URL 传给兼容视觉接口；最多 3 张、单张上限 5 MiB、仅允许安全图片后缀。
- derivative 必须获得 `derivative_images` task consent；无 derivative 不允许图片 AI 分类。
- 模型 system prompt 明确禁止仅凭扩展名分类，继续禁止路径、命令、代码与 tool call。

## 验证

- `backend/.venv/Scripts/python.exe -m pytest -q tests/models/test_models.py tests/classification/test_classification.py`：退出 0，16 passed。
- 新增测试证明 text-only 模型被阻止、受控 JPEG derivative 真正进入请求、请求中不含本地 derivative 路径。
- `npm run test:run -- --reporter=dot`：退出 0，12 passed。
- `npm run typecheck`：退出 0。

## 外部阻塞

- 未提供真实 DeepSeek Key；真实云视觉调用未运行。
- 未检测到用户本地 Qwen 服务；本地真实视觉调用未运行。
