# 阶段05｜DeepSeek与本地千问

```text
/goal 完成归序阶段05双模型适配、隐私出站控制与预算。先读docs/05_AI_PIPELINE.md、07_API.md、08_SAFETY.md、12_SOURCES_DECISIONS.md、模型提示词/schema和PROJECT_STATUS。模型官方能力随版本变化，只针对相关官方资料做必要核验，不扩大成无边界调研。

用统一httpx transport实现DeepSeekAdapter与QwenLocalAdapter。DeepSeek初始推荐deepseek-flash，model_id可改；当前专用thinking字段只留在DeepSeek适配层。本地接OpenAI-compatible、Ollama/LM Studio等用户明确配置服务，接口差异靠预设与能力探测，不把OpenAI-compatible当所有参数相同。

实现Windows凭据保存、无密钥回显、URL变更能力失效、逐项探测文本/视觉/JSON/取消、出站PrivacyGate与首次授权预览。只上传经过许可的必要文本/派生图/帧；原始音视频不直传。本机模式禁云回退/下载/隐式代理，LAN必须独立信任标签。

接通policy、视觉描述、taxonomy、classification与最多一次repair。输出必须通过JSON schema、evidence allowlist、category allowlist和任务归属验证。总尝试3次封顶，401/403不重试，429遵循Retry-After；修复与重试均计预算。缓存绑定模型/模板/输入/规则/隐私版本。

至少两种本机HTTP假服务验证协议和异常。真实DeepSeek文本/图片及Qwen文本/图片联调只有在用户已配置并授权时运行专用样本；无Key/服务不阻塞离线功能，不猜密钥、不偷偷调用其他模型、不伪造成功。

通过AI04～AI12；有条件通过AI01～AI03。报告phase-05.md分开列假服务与真实API、模型实际ID、能力、usage、隐私数据范围，不能泄漏Key或原内容。更新PROJECT_STATUS并保留恢复入口。
```
