# PHASE E —— Conversation UI Skeleton / 前端重做

更新时间：2026-09-20

## 1. 交付范围

本阶段把桌面端主工作区切换为 Conversation Workspace 三栏骨架：左侧长期会话导航，中间消息与输入区，右侧文件工作区。实现严格停留在数据持久化和 UI 骨架边界，没有调用 LLM、没有生成假助手回复，也没有实现 Agent Orchestrator、Tool Calling、Incremental Replanning 或新的文件执行逻辑。

开始实现前的现状审计见 [conversation-ui-audit.md](conversation-ui-audit.md)。

## 2. 新增与修改

- `frontend/src/pages/ConversationWorkspacePage.vue`：新建会话空状态、真实会话加载、消息区、输入区和右侧工作区组合。
- `frontend/src/features/conversations/store.ts`：Pinia 会话状态，统一读取 Conversation、Message、Context、PlanVersion、ExecutionRound、ConversationFile。
- `frontend/src/features/conversations/components/ConversationSidebar.vue`：新建、搜索、切换、重命名、归档/删除入口和旧页面兼容导航。
- `ConversationHeader.vue`、`ChatComposer.vue`、`ConversationMessage.vue`、`WorkspaceStatusBar.vue`：标题、模型、消息和发送状态。
- `FileWorkspace.vue`：当前文件、整理预览、变更记录三个真实数据入口；没有方案/执行数据时显示明确空状态。
- `PlanPreviewCard.vue`、`ExecutionResultCard.vue`：只渲染已有 PlanVersion / ExecutionRound 数据，当前不主动生成数据。
- `frontend/src/services/api.ts`：补齐 Conversation 基础 CRUD、消息、上下文、文件、方案和执行轮次 API。
- `frontend/src/router.ts` / `frontend/src/App.vue`：根路径切换到工作区，保留旧 Task、History、Trash、Models、Settings 路由作为兼容入口；模板路由继续迁移，不恢复模板导航。
- `frontend/src/styles/theme.css`：追加 PHASE E 视觉层，使用冷白背景、石墨文字、钴蓝主色、细边框和 304/76px 可折叠侧栏；右侧文件区 392px，可收起；保留旧样式以支持旧页面。

## 3. 用户流程

1. `/` 读取会话列表；存在会话时打开最近会话，否则显示“选择一个文件夹”空状态。
2. 选择文件夹沿用 `chooseSource()` 安全授权流程，随后调用 `POST /api/v1/conversations` 创建会话。
3. 会话页读取真实消息、上下文、文件和未来可用的方案/执行轮次。
4. 输入消息只写入 `POST /api/v1/conversations/{id}/messages`，成功后显示“消息已保存。对话式 AI 整理能力将在下一阶段接入。”
5. 右侧文件可搜索、列表/网格切换、单选；当前选择作为引用入口预留在 Composer 中，未执行任何工具动作。
6. 预览和变更记录只展示已有数据；没有数据时使用明确的“还没有整理方案/执行记录”状态，不伪造卡片。

## 4. 保留与清理边界

- 主导航不再出现模板、规则或旧分类模式入口。
- Task、Planner、Classifier、Plan、Execution、History、Undo 等核心旧能力未删除。
- 旧任务页面与历史页面继续通过原路由可访问，避免前端重做破坏既有数据。
- 本阶段不实现 ChatGPT 风格假聊天、不连接 DeepSeek/Qwen、不触碰 FileOperationEngine。

## 5. 测试与验证

在 `frontend/` 执行：

| 命令 | 结果 |
|---|---|
| `npm.cmd run test -- --run` | 4 files / 24 tests passed |
| `npm.cmd run typecheck` | exit 0 |
| `npm.cmd run build` | exit 0，Vite 1727 modules transformed |

前端重做未修改后端实现；为确认 API 基线仍可用，额外运行 `backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_conversation_data_model.py -q`：2 passed，保留既有 Windows 临时 reparse 清理 warning。

新增 `frontend/tests/conversation-workspace.test.ts` 覆盖：

- 用户/系统消息角色渲染；
- Composer 调用真实消息 API，且不插入假助手消息；
- 文件区 tab 切换与文件选择；
- 根路径空状态和“下一阶段接入”提示。

通过本地 FastAPI + SQLite 临时数据验证：

- 真实 Conversation、Message、ConversationFile、ModelProfile 能在重载后恢复；
- 发送消息后列表和数据库均出现新 USER 消息；
- 右侧 4 个临时目录文件可显示，选择文件会同步到 Composer 引用状态；
- 右侧预览/变更记录在没有真实 PlanVersion/ExecutionRound 时保持空状态；
- 文件区收起后工作区扩展为单列，侧栏收起后从 304px 变为 76px。

## 6. 视觉验证

源视觉目标为用户提供的 `C:\Users\renxiaolin\Downloads\ChatGPT Image 2026年9月20日 16_51_58.png`。使用 Codex Desktop in-app browser（IAB）打开 `http://127.0.0.1:5173/conversations/7e9c13d6-807a-4c41-8df6-2c6a93916133`，在 1310×898 CSS viewport、device scale 1.5 下完成三栏、消息、真实文件列表、文件选择、tab、侧栏和右侧收起状态检查。窗口标题栏由 pywebview 外壳负责，浏览器内只比较应用内容区。

实现有意使用 lucide 文件类型图标而非虚构缩略图，因为当前临时数据没有受信任的图片缩略图服务；这与 Phase E “无缩略图时使用类型图标”边界一致。下一阶段接入真实预览能力时再替换资源。

详细 QA 记录见项目根目录 [`design-qa.md`](../../design-qa.md)。

## 7. 下一阶段切入点

Conversation UI 已经只依赖持久化 API。下一阶段可以在不改三栏布局的前提下，将 Composer 的保存成功点接入 Agent Orchestrator，并把 PlanPreviewCard、ExecutionResultCard 替换为真实的方案/执行事件渲染；本阶段没有预埋任何假回复或工具调用。
