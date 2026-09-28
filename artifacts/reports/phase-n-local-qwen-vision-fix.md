# 本地千问图片整理阻断修复（2026-09-28）

## 问题与修复

- 本机 Ollama `qwen3-vl:4b-instruct` 的文本和视觉探测通过，但首次整理三张图片在分类响应校验中断。诊断只检查了响应字段名、文件 ID 与视觉描述长度，没有记录图片、提示词或完整模型输出。
- 根因包含多处小模型结构波动：一次请求含多图时漏写视觉描述；类别树重复 ID 或超过层级限制；单图分类省略 `abstain`、`file_id`、`evidence_ids`，或引用未提供的证据 ID；复杂修复响应有时仍漏视觉描述。
- 本地视觉分类改为每次一张图片。分类只允许批准的类别 ID；单输入单输出且模型省略文件 ID 时由程序绑定，显式错误 ID 仍拒绝。缺省 `abstain` 按类别是否为空确定；新图片缺省证据列表为空，随后只保存实际视觉描述产生的受控证据。虚构证据 ID 被剔除并添加 `insufficient_evidence` 警告。视觉描述缺失时重发已授权导出图；仍缺失时仅询问该图片的可见内容，再进行完整校验。所有补问均受原隐私授权和调用预算限制。
- 规划器在模型输出阶段验证类别图、唯一 ID 和层级限制；非法树进入一次修复。提示词明确当前设置的深度、兄弟节点与节点数上限。空的视觉刷新集合现在保持为空，不会被误当作“重新发送全部图片”。
- 真实模型的低/中可信度建议原先全部被安全门槛保留原位，对话界面却没有确认入口。现在逐文件预览显示建议分类、依据和可信度；用户预览图片后可逐项勾选确认。服务器只接受该文件当前分类结果中的白名单类别，保存人工审核并生成新版本方案；确认分类不会执行移动，执行仍需再次批准。无法分类的图片继续保持原位。
- 类别规划新增小批量上限并拒绝示例占位 ID，单图响应支持 `classification` 包装格式；仍拒绝错误文件 ID、非法类别、未经授权的目标路径和缺失的视觉事实。

## 验证

| 验证 | 结果 |
|---|---|
| `uv --directory .\backend run --all-extras pytest -q` | exit 0；228 passed，2 warnings |
| `npm test -- --run`（frontend） | exit 0；53 passed；`npm run typecheck` exit 0 |
| `uv --directory .\backend run --all-extras python ..\scripts\run_local_qwen_first_preview.py` | 本机真实 Ollama、三张合成 JPG：生成 v1 预览与 AI 建议；人工确认一项后生成 v2 `move` 操作，0 条执行操作，源图哈希一致；exit 0 |
| Windows 同名便携包构建 | `scripts/package-windows.ps1 -SkipTests -SkipInstaller -ReleaseDirectory artifacts\release-agent-chat` exit 0；冻结诊断与包核对通过，原包路径已覆盖；详见 `phase-n-local-qwen-package.log` |

真实模型最后一次调用账本见 `phase-n-local-qwen-first-preview.json`，只含调用用途、状态与错误码；脚本使用临时数据库和生成样本，不触碰个人照片。早期打包版已通过原生界面的本地千问首次预览；本次最终包的“逐项确认→新方案→批准执行”尚未做原生界面复测，因此不能宣称正式上线闭环通过。小模型的类别质量仍须逐张核对，安装器和其他正式上线门槛仍独立阻塞。
