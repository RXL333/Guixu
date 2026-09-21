# AI-only PHASE 10：DeepSeek 真实联调

日期：2026-09-19  
状态：PARTIAL_EXTERNAL（真实文本语义分类冒烟通过；完整应用链路与视觉分类待补证）

## 2026-09-19 补充验证

- 用户明确提供一次性测试 Key，并授权在项目测试目录内发起真实请求。
- Key 仅经交互进程标准输入传入；未写入源码、数据库、环境文件、凭据管理器、日志或本报告。
- 测试入口：`artifacts/test-workspaces/real-deepseek-test/run_deepseek_test.py`。
- 模型：`deepseek-chat`；端点由项目适配器限制为 `https://api.deepseek.com`。
- 输入是两个同为 `.txt` 的合成文本：网络课程实验内容与操作系统实验内容；不包含用户个人文件或真实路径。

## 结果

- 真实请求退出码：`0`，一次请求成功，无重试。
- 延迟：`888 ms`；输入 `169` tokens，输出 `71` tokens。
- 模型将网络样本返回为 `course.network`，将操作系统样本返回为 `course.os`。
- 返回值通过本地 JSON、精确 file ID、受限 category ID 与非空 evidence 校验，证明该 Key 当前可鉴权，且项目 DeepSeek 传输适配器可完成受限文本语义分类。
- 本次没有运行图片视觉分类、批量质量评测、应用内凭据保存、隐私授权 UI 或从扫描到执行的完整桌面闭环，因此不能据此把 PHASE 10 或发布门标记为全部通过。

## 剩余补证

- 在模型连接页通过 Windows 凭据管理器保存有效 Key，并执行 capability probe。
- 仅对项目临时目录运行真实文档规划、批量分类、审阅、批准、执行与撤销闭环。
- 使用许可明确的图片样本验证视觉能力；运行带金标准的语义质量评测。
