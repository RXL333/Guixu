# Changelog

## 0.9.0 — 2026-09-30

面向 GitHub 公开下载的发行版。**MIT 许可**，便携 ZIP，无安装程序。

### 修复的缺陷

- **P0-002 从任何真实旧库升级都会失败。** 迁移 `0012_chat_call_audit` 在没有活动事务时
  执行裸 `COMMIT`，pysqlite 抛 `cannot commit - no transaction is active`。
  **任何从 0.1.0 升级的用户首次启动都会直接失败。** 此前不可见，是因为所有迁移测试都从
  *当前* schema 建库，而新装机器走提前返回分支，从不执行那行。回归测试用 git 历史里
  逐字取出的三个真实历史 schema（2026-09-14 / 09-21 / 09-25）作为 fixture。
- **P1-006 目录授权接受任意系统路径。** `canonicalize_directory` 此前毫无系统路径检查，
  `C:\Windows`、`C:\Windows\System32`、`C:\Program Files`、`C:\Program Files (x86)`、
  `C:\ProgramData`、`C:\Users\Public` 及任意盘符根全部可被注册为整理根。现分两类封禁：
  系统目录封禁整棵子树；盘符根 / `C:\Users` / profile 根只封禁其本身——封禁 profile
  子树会连带干掉 Documents、Downloads，恰好废掉产品本身。
- **P1-007 发行版本号在五处各写一份并已漂移。** 打出的包叫 `Guixu-0.1.0`，
  SBOM 写着 `"version": "0.1.0"`，而 `SHA256SUMS.txt` 因目录名对不上被**静默跳过**，
  只剩 2 行——一个看着有校验、实际不覆盖 app 内任何文件的发行物。五处统一读
  `backend/pyproject.toml`，元数据脚本读不到目录时改为抛错。
- **P2-004 目标路径被按盘上大小写静默改写。** `ensure_within` 对尚不存在的叶子调用
  `Path.resolve()`，Windows 上会按盘上大小写重写，指向 `Photo.jpg` 的方案被折叠成
  已存在的 `photo.jpg`。改为返回词法绝对路径。NTFS 上不可见，在大小写保留的卷
  （网络共享、exFAT、同步目录）上这是一次真实的改名。
- **P2-003 普通聊天未进入调用审计。** 聊天现在同样写 `model_calls`，含 token、时延、
  错误码；`task_id` 为空，因此不污染按 Task 的预算口径。
- **P3-001 AI 回复直接显示 Markdown 标记。** 改用受限渲染器：原始 HTML 保留为
  字面字符，链接只允许 http/https。

### 新增覆盖

此前标记 PARTIAL 却没有任何断言支撑的安全矩阵项：

- **S02** 系统路径授权（15 项）
- **S03** 执行边界的 reparse point：目标树内的 junction 绝不被穿透写入；仅经 junction
  可达的源被拒；对照组确保真实子目录不受影响
- **S04** 批准绕过短语（12 项）：8 种短语、连发 4 次不升级、跳过 approve 直接 execute
  带正确 hash 也拒、拿 v1 的 hash 批准 v2 被拒、重启后待批方案仍需批准
- **S09** undo 身份与用户改动（6 项）。核心用例：用户把整理好的文件改名拿走、并在原路径
  放一个不同的新文件——按路径匹配的 undo 会毁掉那个冒名文件，身份是哈希，因此必须拒绝

### 发行工程

- 版本改为单一来源（`backend/pyproject.toml`），五处调用点统一读取
- GitHub Actions：后端分域测试 + 前端 + 性能基准
- `SHA256SUMS.txt` 覆盖 app 内每个文件，缺失时抛错而非静默跳过
- README 补齐下载、完整性校验、SmartScreen 绕过、模型配置、数据位置与已知限制

### 验证状态

后端 **291 passed / 1 skipped**（跳过的长路径用例受本机卷的 260 字符限制，非通过），
前端 **67 passed**，`vue-tsc` 与 `vite build` 通过。

**尚未覆盖**：S01 注入载荷、S17 凭据管理器与打包版日志、打包版真实模型链的完整人工复测。
详见 `docs/current/deployment/RELEASE_ACCEPTANCE.md`。

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
