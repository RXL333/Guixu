# 维护验收报告：模板选择与 AI 分类入口

日期：2026-09-15

## 根因

- 分类模板页原先只有展示卡片，没有点击事件，因此无法把模板带入任务。
- 新建任务页把 `template_key` 硬编码为 `universal.types`。该模板是确定性的模态分类模板，所以无论用户选择什么，结果都只能按图片、文本、文档等类型划分。
- 截图中的执行提示来自执行接口对未批准、已失效计划、hash 不一致或执行条件变化的统一安全拒绝。此前版本在重复点击、批准请求中断或使用旧 EXE 时会反复触发；幂等批准与 revision 刷新修复已在上一份维护报告中记录。

## 修复

- 模板卡片支持鼠标、Enter、Space 选择，并跳转到带模板 ID 的新建任务页。
- 新建任务页读取 URL 模板、允许选择 24 套模板，并把真实 `template_key` 持久化到任务。
- 需要模型的模板显示明确提示；选择模型连接后，后端会把已授权的文件证据交给模型，返回受限类别 ID 与证据。无模型时明确失败，不伪造 AI 成功。
- `universal.types` 仍保留为无需模型的纯规则模板。

## 验证

| 命令 | 结果 |
|---|---|
| `npm run typecheck` | 0 |
| `npm run test:run -- --reporter=dot` | 0；12 passed |
| `npm run build` | 0；1714 modules transformed |
| `scripts/package-windows.ps1 -SkipTests -SkipInstaller` | 0；onedir 与 portable ZIP 重建成功 |

本轮未调用真实 DeepSeek Key 或本地 Qwen 服务；真实模型质量仍需用户提供授权服务后验证。测试和打包未操作用户个人文件。
