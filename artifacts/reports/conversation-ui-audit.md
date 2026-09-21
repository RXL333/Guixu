# PHASE E — Conversation UI Audit

日期：2026-09-20  
范围：前端信息架构、可复用组件、API 与窗口约束；先于 UI 重做编写。

## 1. 当前前端状态

- `App.vue` 仍是固定左侧导航 + 单内容列，视觉系统使用暖纸白、深松绿和后台式页面标题。
- 首页仍以一次性 Task 创建和历史 Task 列表为主入口。
- `HistoryPage.vue` 已承载任务删除、最近删除和批量操作，旧 Task 页面必须继续保留以支持历史兼容。
- `/templates` 已重定向到 `/`，规则页面和模板页面不再存在。
- `ModelsPage.vue`、`SettingsPage.vue`、任务扫描/分类/审阅/执行页属于旧流程兼容页面，不在本阶段删除。
- 当前依赖已有 `lucide-vue-next`、Pinia 和 Vue Router；没有独立 Conversation store 或三栏 Layout。
- 全局设计 token 集中在 `frontend/src/styles/theme.css`，但仍包含旧绿色品牌和大卡片样式，需要改为冷白/石墨/钴蓝 token。

## 2. 可复用能力

| 能力 | 当前实现 | PHASE E 决策 |
|---|---|---|
| API client | `src/services/api.ts` | 增加 Conversation CRUD、Message、Context、Files、Plans、Executions 方法，继续复用会话 token 与 envelope |
| 状态管理 | Pinia 已安装，当前页面多用本地 ref | 新增轻量 `conversationStore`，只管理会话工作区状态 |
| 图标 | `lucide-vue-next` | 统一复用现有图标库，不混入 Emoji 或第二套图标 |
| 旧 Task 工作流 | 多个 `/tasks/*` 页面 | 保留兼容路由，主入口切换到 Conversation Workspace |
| 最近删除/历史 | `HistoryPage.vue` | 保留 `/history`、`/trash`，从新版侧栏进入 |
| 模型连接/设置 | `ModelsPage.vue`、`SettingsPage.vue` | 保留二级入口，使用新版壳层 |

## 3. Conversation API 可用性

PHASE D 已提供持久化 facade：创建/列表/读取/改名/删除/恢复会话，消息追加与读取，Context CAS 更新，文件引用与验证，PlanVersion/ExecutionRound 读取。创建会话要求已登记的 source grant，因此“选择文件夹”必须先走 `chooseSource`，不能把任意路径直接写入 API。

本阶段只连接这些持久化 API，不调用 LLM、Planner、Classifier 或执行器。用户消息可以保存；助手区域显示明确的“下一阶段接入”状态，禁止 fake AI 回复。

## 4. 视觉与窗口基线

- 目标图是 Windows 桌面 1536×1024 视觉，三栏比例约为 304 / 780 / 452 px。
- 后端 pywebview 默认窗口为 1280×820；前端安全可用最小尺寸调整为 1024×680，并在 1280/1366/1440 宽度下分别收窄侧栏或抽屉化文件区。
- 新 token 采用 `#F6F7F9` app background、`#FFFFFF` surface、`#20242C` primary text、`#68717E` secondary text、`#356AE6` primary accent、`#E4E7EC` border。
- 三个滚动域彼此独立：Conversation Sidebar、Chat Message Area、File Workspace；composer 固定在中栏底部。

## 5. 淘汰/保留边界

本阶段淘汰旧主壳层、首页 Task 入口、暖色管理后台视觉和旧导航层级；不删除 Task、Planner、Classifier、历史详情、模型连接或设置页面。新 UI 只建立未来 Agent 居住的骨架，不实现 Agent Orchestrator、Tool Calling、自动回复、分类推理或 Conversational Undo。

