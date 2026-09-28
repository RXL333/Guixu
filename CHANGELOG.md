# Changelog

## 0.1.0-dev 会话审计修复 — 2026-09-26

- 当前文件和后续方案按唯一路径计数，保留旧任务的审计历史；首次分析分批关联全部扫描文件。
- 新会话可选择最多 3 张图片，在明确确认后与视觉模型讨论；预览支持 Escape，桌面版可打开当前目录。
- 原便携包位置已覆盖更新；完整验证见 `artifacts/reports/phase-n-conversation-audit-fixes.md`。

## 0.1.0-dev 窗口与会话优化 — 2026-09-25

- 已保存会话先呈现内容，目录清点和恢复核对异步完成；避免已有文件记录重复进行目录清点。
- 每条对话新增复制文本按钮，模型连接操作换为统一风格图标按钮；普通窗口保持完整左侧导航，修复品牌图标加载。

## 1.0.0 candidate — 未发布（2026-09-24）

- PHASE N 开始 Feature Freeze 与真实模型/文件系统/Windows 发布矩阵验收。
- 修复执行前方案调整入口和 Windows 打包失败传播；真实 DeepSeek 完整组合链及失败重规划原子性仍是发布阻断，**未形成 RC 或 stable release**。
- 正式判定见 `docs/current/deployment/RELEASE_ACCEPTANCE.md`；本节不是发布记录。

## 0.1.0-dev — 2026-09-14

- 实现 pywebview + FastAPI + Vue 3 单入口与随机本地会话。
- 实现只读扫描、解析、24 个模板、规则/AI 分类、安全计划、批准、复制/移动、日志、恢复和冲突安全撤销。
- 实现 DeepSeek 与 OpenAI-compatible Qwen 适配、Windows 凭据存储、最小上传、隐私同意和硬预算。
- 实现完整任务 UI、证据审阅、分页/搜索/批量修正、历史恢复与授权报告导出。
- 增加 120 项许可样本、10,000 文件基准、安全预览 ticket、116+ 自动化测试与浏览器 E2E。
- 增加 Windows x64 PyInstaller onedir、同 EXE worker、Inno Setup 脚本、SBOM 与校验值流程。
- 修复同一冻结计划重复批准时误报 `PLAN_STALE`，并在执行前刷新 task revision、阻止重复点击。
- 模型连接页增加带 revision 校验和二次确认的删除入口；删除采用审计安全的停用语义，不物理破坏历史引用。

此版本仍为 dev；真实模型、媒体增强、干净机安装与原生兼容证据见 `docs/product/limitations.md`。
