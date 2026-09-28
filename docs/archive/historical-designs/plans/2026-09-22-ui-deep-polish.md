# Phase M 实施与验收计划

目标：依照用户 Phase M 原文完成现有 Windows 工作区深度精修，不改变核心执行与授权流程。

1. 记录当前页面截图和审计；缺少状态通过隔离 fixture 补齐。
2. 冻结冷白/石墨/钴蓝方向；统一 tokens、字体、spacing、controls、menus、cards、dialogs。
3. 三栏 240 / flex / 380，聊天至少 520；窄屏右侧 overlay，独立滚动。
4. Sidebar、Header、Message、Composer、Reference、File list/grid；修复已有联动和键盘问题。
5. Plan/diff/history、execution/undo/recovery、History/Models/Settings/Trash。
6. 长文案、0/1/大量数据、5000 文件窗口化、500 消息分批显示、reduced motion。
7. 实际截图第一轮 → 审查 → 第二轮修正；保存用户规定的 24 状态及 1280/1366/1440 截图。
8. 前端行为测试、typecheck/build、后端完整回归、desktop build/smoke；实测 DPI，无法控制的原生环境明确记录。
9. UI_DESIGN_SYSTEM.md、ui-deep-polish.md、PROJECT_STATUS.md；逐项核对原始要求，未完成项不标通过。

依赖：使用现有 Vue/Pinia/API/Lucide；不增加字体、模型或新服务。各阶段既有未提交改动保留。浏览器 QA 使用内置浏览器，数据仅来自真实隔离状态或明确 dev fixture。
