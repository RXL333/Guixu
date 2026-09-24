# PHASE F 首次整理分析真实冒烟报告

更新时间：2026-09-24

## 结论

真实 DeepSeek 配置已完成一次成功的首次分析闭环。请求从已授权目录扫描 5 个合成图片文件，经过本地解析和缓存证据、DeepSeek 视觉 taxonomy planner、DeepSeek 视觉 classifier、预览计划编译，最终生成唯一的 `FULL / PROPOSED` PlanVersion v1。没有执行文件操作。

## 运行隔离与输入

- 隔离数据库：`artifacts/test-workspaces/phase-f-real-deepseek-20260924-120906/data/app.sqlite3`
- 合成源目录：同目录下的 `source/`
- 输入：5 个 JPG（湖面、森林、城市、花朵、海岸场景）；文件只用于测试，不包含用户个人资料。
- 模型：本机已启用的 DeepSeek profile，secret 由 Windows Credential Manager 提供；本报告不记录 key、请求正文或原始响应。
- 执行方式：`preview_move`，没有调用 FileOperationEngine 的真实移动。

## 结果证据

最终成功任务：`cae45fbb-b4d0-4ae3-b200-284633dc103b`。

| 检查项 | 结果 |
| --- | --- |
| HTTP 首次 turn | 200 |
| 进度阶段 | `scan_started` → `scan_completed` → `evidence`/planner → `taxonomy` → `classification` → `preview` → `complete` |
| AI 类别 | 4 |
| 输入文件 | 5 |
| 受影响文件 | 5 |
| 保留文件 | 0 |
| PlanVersion | 仅 v1，`FULL / PROPOSED` |
| `baseline_execution_round_id` | `NULL` |
| ExecutionRound | 0 |
| 磁盘文件变化 | `false` |
| 助手消息 | `PLAN_PROPOSAL`，包含实际文件/类别/保留计数 |

## 真实模型与证据核验

- `model_calls` 为 1 次 `planning` + 1 次 `classification`，均 `response_status=ok`。
- `file_evidence` 中有 5 条 `CLOUD_MODEL / deepseek / VISUAL_DESCRIPTION`，确认图片输入使用真实视觉模型；没有启用本地语义分类替代路径。
- 同一任务还保留了本地 Pillow / RapidOCR 解析证据，供模型受控使用。
- 端到端耗时约 33 秒；各模型调用的具体延迟由 `model_calls.latency_ms` 持久化。

## 安全核验

对 5 个源文件在请求前后计算 SHA-256，并核对路径与文件数量：全部保持不变。任务没有 ExecutionRound、没有执行 journal 写入动作、没有调用 undo，也没有删除真实文件。

## 失败修复记录

1. 首次真实请求发现自然语言“这些文件”会被旧引用解析器误判为歧义；首次分析入口现将无显式 file id 的“这些文件”安全解释为当前已授权 scope，显式引用仍走 resolver。
2. 旧数据库的 `model_calls.purpose` CHECK 约束只接受 `planning` / `classification` 等枚举；运行时名称在审计写入边界映射到兼容枚举，不改变模型调用语义。
3. 跨任务复用 FileProfile 时旧记录不保存缩略图路径；解析服务现从应用缓存重新水合缩略图路径，确保真实视觉调用不会因为缓存复用失败。

## 当前限制

- 本报告是隔离目录上的真实 smoke，不代表已对任意用户目录执行移动；生产仍须由用户在预览后明确批准。
- DeepSeek 网络调用依赖本机启用 profile、有效 secret、能力探测和隐私授权；不可用时 API 返回明确错误，不回退到本地语义规则。
- 通用 Agent Orchestrator、对话式 replanning、Tool Calling 和真实执行仍属于后续阶段。
