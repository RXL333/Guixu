# 命名指令与分类语言修复

日期：2026-09-26

## 问题与修改

- 旧前端以过窄的正则识别命名命令，“帮我把所有文件文件进行命名”未匹配；若用户随后点击整理按钮，就生成分类方案。现明确的命名请求在发送和整理按钮上均进入命名预览；普通提问仍交给 AI 聊天。
- 设置增加中文 / English 分类语言；SQLite `default_settings` 保存选择与 revision，首次分析和已有会话重规划读取该设置。模型规划提示明确语言要求，并校验类别名称；不合格输出走受限修复，仍不合格则阻止方案。
- 前端不再把 HTTP 500 的纯文本响应当 JSON 解析；显示可读状态错误。截图中的 500 根因尚无可用服务端堆栈证据，不能声称后端错误已完全解决。
- 命名方案按钮显示“确认并开始命名”，准备方案时旧方案执行按钮禁用。

## 验证

- `npm run build`：exit 0。
- `npm run test:run`：exit 0，49 passed。
- `uv run pytest -q --disable-warnings`：exit 0，220 passed，2 warnings（测试依赖弃用告警）；测试收尾另有 pytest 临时目录清理告警，不影响断言。
- `uv run pytest tests/models/test_models.py::test_taxonomy_category_language_is_enforced tests/integration/test_api.py::test_category_language_setting_persists_and_checks_revision -q --disable-warnings`：exit 0，2 passed。
- `uv run pytest tests/classification/test_ai_planner.py::test_conversation_replan_uses_current_category_language -q --disable-warnings`：exit 0，1 passed。
- 当前尚未对用户照片目录执行改名或分类；真实模型命名质量仍需用户审核预览。

## 包与阻塞

原位覆盖 `artifacts/release-agent-chat/Guixu-0.1.0` 时，运行中的 `Guixu.exe` 占用 `_internal/charset_normalizer/cd.cp312-win_amd64.pyd`，PyInstaller exit 1。暂存包构建后需退出旧应用再原位覆盖并验证冻结入口。
