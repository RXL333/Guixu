# 阶段 05 验收报告：双模型适配、隐私授权与预算

日期：2026-09-13  
环境：Windows 11 x64；Python 3.12.10；本地 SQLite；隔离的本机 HTTP 假服务

## 结论

阶段 05 的可离线实现与协议故障测试 **PASS**；阶段总体标记 **BLOCKED_EXTERNAL**，原因仅为没有用户配置并授权的 DeepSeek Key 与已启动的 Qwen 服务，AI01～AI03 未运行。假 HTTP 服务的结果没有写成真实模型能力或语义质量。

实现了 DeepSeek 与 Qwen 业务适配器、统一 OpenAI-compatible transport、Windows Credential Manager、逐字段能力探测、模型连接 API/UI、最小化 `OutboundEnvelope`、任务级 consent、调用/token/费用未知预算、最多三次尝试与一次 JSON repair。模型输出仍必须通过阶段 04 的 schema、file/taxonomy/evidence/category 校验，模型不能提供磁盘路径或执行操作。

## AI01～AI12

| 编号 | 结果 | 证据 |
|---|---|---|
| AI01 | BLOCKED_EXTERNAL | 未提供 DeepSeek Key；未发送任何真实内容或探测请求 |
| AI02 | BLOCKED_EXTERNAL | 同上；仅以内置 1×1 PNG 对假服务验证视觉协议 |
| AI03 | BLOCKED_EXTERNAL | 未发现用户显式配置的 Qwen 服务；未扫描局域网或常见端口 |
| AI04 | PASS | 第一次坏 JSON 后只允许一次 repair；第二次仍坏即 `MODEL_OUTPUT_INVALID`，修复不重发原正文/媒体 |
| AI05 | PASS | 401 只请求一次；429 读取 `Retry-After`；网络/5xx 总尝试不超过 3 |
| AI06 | PASS | `qwen_local` 禁止 cloud trust；loopback URL 不能改成远端；无云回退实现 |
| AI07 | PASS | 文本、视觉、JSON、认证、可达、取消分别记录；假服务视觉 400 显示 unsupported |
| AI08 | PASS | base URL、model ID、runtime/provider 任一变化后能力恢复 unknown |
| AI09 | PASS | retry 与 repair 分别写 `model_calls` 并计入 max_calls；input/output 预算发出前保守预留 |
| AI10 | PASS | 无匹配 task/profile/data_types/scope_hash consent 时 `PRIVACY_CONSENT_REQUIRED`；撤销使用 task revision CAS |
| AI11 | PASS | 数据库只存请求 hash/usage/status/时延，不存 Key、正文、base64 或思维链；请求校验错误也移除 input 值 |
| AI12 | PASS | loopback、可信私网与 DeepSeek 云端分别校验；可信局域网解析到公网时拒绝 |

## 安全实现摘要

- DeepSeek 默认 `https://api.deepseek.com`、`deepseek-flash`；专属 `thinking` 字段只在 DeepSeekAdapter 添加。实现依据 2026-09-13 核验的官方 [Vision 文档](https://api-docs.deepseek.com/guides/vision/)。
- Ollama/LM Studio/vLLM/llama.cpp 作为 Qwen 外部运行时预设，共用受限 transport，不复制分类业务逻辑。Ollama 部分兼容语义依据官方 [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)，LM Studio 端点依据官方 [OpenAI Compatibility](https://lmstudio.ai/docs/developer/openai-compat)。
- `follow_redirects=False`、`trust_env=False`；不使用隐式代理。DeepSeek 限 HTTPS 官方域；loopback 只接受 localhost/127.0.0.1/::1；trusted_lan DNS 解析结果必须全部为私有或 link-local 地址。
- Key 使用当前 Windows 用户的 Credential Manager；API 只返回 `has_secret`。自动化用随机临时凭据完成写/读/删回环。
- `OutboundEnvelope` 不序列化 FileProfile metadata，因而不含绝对路径、用户名、设备字段或 GPS；只按 consent 选择 evidence 类型和字符预算。
- 费用表未配置时 `estimated_cost_micros/currency` 保持 null，UI/报告不得显示 0 元。

## 模型连接 UI

`/models` 已连接真实本地 API，支持 Qwen/DeepSeek 预设、服务地址、模型 ID、信任范围、Key 密码输入、逐项能力状态和空态。连接测试只用固定文本、固定 JSON 与内置测试像素。

最终 Playwright 截图：

- `output/playwright/phase-05-models-1024.png`
- `output/playwright/phase-05-models-1280.png`
- `output/playwright/phase-05-models-1440.png`

三种宽度无浏览器 console warning/error。首轮发现无效 CSS 变量导致控件边框缺失，修正后重新生成了全部最终截图。

## 命令与结果

| 命令 | 退出结果 |
|---|---:|
| `uv lock` | 0；httpx 移入运行时依赖，锁文件更新 |
| `python scripts/verify.py models` | 0；9 passed |
| `uv run --all-extras pytest -q`（backend） | 0；108 passed，2 个已知 warning |
| `npm --prefix frontend run typecheck` | 0 |
| `npm --prefix frontend run test -- --run` | 0；1 passed |
| `npm --prefix frontend run build` | 0；1694 modules transformed |
| Playwright 1024/1280/1440 截图与 console 检查 | 0；0 error，0 warning |

## 外部阻塞与恢复点

- AI01/AI02：仅当用户在应用设置中提供 DeepSeek Key、明确 consent 并同意测试样本/预算后运行。
- AI03：仅当用户明确配置已启动的 Qwen 服务后运行；应用不会自动下载 27B 权重、修改 CUDA 或扫描 LAN。
- 下一阶段读取 `prompts/codex/06_FULL_UI.md`，完成六导航、任务向导、三栏审阅、执行/撤销预览、历史和设置的完整真实 API 界面。
