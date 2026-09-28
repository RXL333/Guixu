# 文件命名功能（2026-09-25）

## 实现

- 在对话中明确说“开始命名”“生成命名方案”“帮我给照片命名”，或点击输入框的“生成命名方案”。普通讨论仍调用聊天模型。首次命名先完成授权目录内容分析。
- 模型只输出文件 ID、文件名主体、证据 ID 和短说明；后端校验模型输出，保留扩展名和原目录，已有目标使用无覆盖避让。缺少可用内容证据的文件保持原名。
- 命名预览写入版本化计划；用户可在“整理预览”查看逐文件原名和新名。批准后由现有文件执行器按源身份、哈希、方案哈希执行并记录；Undo 沿用 move 反向操作。

## 验证

| 命令或场景 | 结果 |
|---|---|
| `uv run pytest tests/safety/test_plan_compiler.py tests/integration/test_post_execution_conversation.py -q` | 30 passed；包含名称校验、无覆盖、首次方案替换、仅批准后执行和字节不变 |
| `python scripts/verify.py all` | exit 0；后端分组 8/151/21/10 passed；前端 44 passed；生产构建成功 |
| `uv run python ../scripts/export_runtime_contract.py` | exit 0；命名 API 已写入运行契约 |
| `python scripts/check_document_links.py` | 27 份文档，0 个断链 |
| Windows 覆盖打包 | exit 0；`artifacts/release-agent-chat/Guixu-0.1.0/Guixu.exe` 和同目录便携 ZIP 已覆盖；冻结诊断和 worker 冒烟通过 |
| 包校验与启动 | EXE SHA-256 `BCD51CCB09933C9989F417D39F5AA3ED4630C4DFBF75C790A2535E5064143A72`，ZIP SHA-256 `6C2B26E4E80A61918F5C7CDFA991943207CAE713516304DE9FEFA2D1D9C72696`，均匹配 `SHA256SUMS.txt`；新版窗口标题“归序 Guixu”，进程响应正常 |

真实 DeepSeek/Qwen 命名质量和真实照片目录的人眼核对尚未运行。本轮不会自动改名用户的照片。本机缺少 Inno Setup，安装器未生成，1.0 发布门不变。
