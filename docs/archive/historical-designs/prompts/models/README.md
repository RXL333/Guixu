# 模型提示词集成规范

这些是应用运行时提示词，不是交给Codex开发的Goal。每份分system与user payload两部分。应用将结构化JSON安全序列化后作为user内容传入，不用字符串拼接把原文件塞进system。所有动态变量由后端生成，不允许文件内容覆盖系统约束。

使用顺序：00通用边界 → 01自然语言政策（需要时）→ 02视觉描述（需要时）→ 03分类树规划 → 04单文件分类；05仅修复一次不合规结构。不要把六份全部拼到每次请求里。每次附带对应的最小JSON Schema及必要上下文；版本与hash进入缓存键。图片内容以受授权的image_url块附加，路径绝不发送。

模型返回只是建议。Schema验证、当前文件证据集合、类别allowlist、目录名合法性、授权、文件状态、哈希与执行限制均由本地代码再次验证。Prompt不是文件系统安全机制。

policy与视觉输出使用新增的policy-result.schema.json和visual-description.schema.json；树草稿使用taxonomy-draft；分类使用classification-result。model_score不能作为准确率，界面展示的是本地政策计算的审阅等级。
