# Real Conversational Undo Smoke

日期：2026-09-22

命令：

`uv --directory .\backend run pytest -q tests/integration/test_conversational_undo.py::test_real_twenty_file_conversational_undo_smoke`

结果：`1 passed in 1.12s`，exit 0。

场景：临时目录创建 20 个真实文本文件；Round 1 将 20 个文件移动到整理目录；Round 2 只将 5 个文件移动到局部调整目录；“撤销刚才那次调整”解析到 Round 2，生成 5 项 preview。Approval 前 5 个文件仍在局部调整目录；确认后 5 个文件恢复到 Round 1 位置，其余 15 个路径保持不变。随后又将其中 2 个文件移动到新分类并形成 Round 4，证明 Conversation 可继续。

验证：全部 inverse operation 来自 Round 2 的真实 COMMITTED Journal；stable file ID 保持；未调用模型、Vision、Planner 或 Classifier；原 Round 2 与新 Undo round 均保留。

