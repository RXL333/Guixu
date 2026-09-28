# 会话审计四项修复（2026-09-26）

## 修改

1. 重新扫描同一物理路径时，保留不同 Task 的历史文件 ID 和日志；当前文件列表、全局工作区计数与精确文件名解析按规范化路径选最近一次关联记录。旧版历史方案摘要不改写。本机只读数据库核对：旧会话 96 条历史引用，当前唯一路径 48 条。
2. 首次分析以每页 500 条读取全部扫描结果并一次关联，而非只关联第一页；新增 501 项分页边界测试。实际 501 文件完整桌面流程仍待性能验收。
3. 新会话允许选择最多 3 张图片，在明确确认后缩成最长边 1024 像素的无元数据 JPEG，连同问题发送给已验证视觉能力的当前模型。后端再次校验授权目录、格式、大小和同意标记；普通聊天仍不扫描整目录、不生成方案或移动文件。
4. 图片预览支持 Escape 关闭并将焦点还给触发按钮；桌面版“打开当前目录”通过会话已保存的授权源目录调用 Explorer，拒绝已删除会话和无效目录。

## 验证

| 命令或场景 | 退出结果 |
|---|---|
| `uv run pytest -q --disable-warnings` | exit 0；218 passed，2 warnings |
| `npm run test:run -- --reporter=dot` | exit 0；47 passed |
| `npm run build` | exit 0；Vue TypeScript 与 Vite 生产构建通过 |
| `uv run python ..\scripts\export_runtime_contract.py` | exit 0；已更新 `contracts/openapi-runtime.json` |
| `python scripts/check_document_links.py` | exit 0；27 份文档本地链接 0 断链 |
| `scripts/package-windows.ps1 -SkipTests -SkipInstaller -ReleaseDirectory artifacts\release-agent-chat` | exit 0；原 onedir 和 ZIP 原位覆盖；脚本内冻结诊断、worker 冒烟通过 |
| 本机旧会话数据库只读核对 | 96 条历史记录对应 48 个唯一当前路径；未修改用户数据库 |

## 产物与限制

- EXE：`artifacts/release-agent-chat/Guixu-0.1.0/Guixu.exe`，SHA-256 `FC07837087BC01E78D9479A105AE7A324967D7E941370F02C31BEA5421AAB6CB`。
- 便携 ZIP：`artifacts/release-agent-chat/Guixu-portable-x64-0.1.0.zip`，SHA-256 `F635A7DC15D59E2B028EE82D6F8E138191F1A57A07812E79CD6626309B90F6A7`。
- 未运行真实 DeepSeek 图片对话或在用户照片目录执行整理；没有用户图片内容出站。真实视觉回答质量及大于 500 文件的完整桌面耗时尚未验收。
- 501 文件实体集成测试尝试耗时过长，已停止该尝试并改用确定性的 501 项分页边界测试；不把该集成场景写为通过。
- 本次未生成安装器（显式 `-SkipInstaller`）。现有 pytest 的 Starlette/Pillow 提示与 Windows 临时 symlink 清理警告未阻断测试。
