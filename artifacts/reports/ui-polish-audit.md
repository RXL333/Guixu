# Phase M UI 审计（进行中）

日期：2026-09-22。基线为当前工作树；使用隔离的 `runtime-undo-ui/data` 数据库，未修改个人目录。

## 已观察的页面

| 页面 | 当前问题与层级/交互问题 | 保留 | 修改 |
|---|---|---|---|
| Main Workspace | 左栏 304px，标题区 91px；同一会话同时出现在今天/昨天；业务卡连续堆叠 | 三栏、真实消息与 API | 左栏 240px、标题 64px、按自然日分组、统一消息间距 |
| Empty Conversation | grid 拉伸导致巨大按钮/留白；过期“下一阶段接入”说明 | 目录授权、示例填充 | 紧凑空态、真实能力说明 |
| File Workspace | 文件图标按 nth-child 随机变色；每行重复路径和目录；窄屏遮住聊天 | 搜索、列表/网格、稳定文件引用 | 56px 行、统一图标、窗口化大列表、overlay |
| Plan Preview | 卡片高亮外圈明显；统计层级弱 | 既有批准与版本关系 | inline stats、轻边界 |
| Plan History | 点击聊天中版本历史未切换右侧 tab；版本横向平铺 | 历史只读/恢复为新版本 | 面板联动、折叠历史 |
| Execution | COMPLETED 技术状态直接显示；“查看执行记录”无动作 | 实际执行结果/撤销 | 本地化、接入历史面板 |
| Undo | 源码中渐变、16px 圆角与厚阴影违背规范；待补本轮 preview/conflict 截图 | 确认/冲突阻止/API | 同 Plan 的克制卡片 |
| Recovery | 源码含偏技术的中断说明；待补本轮恢复截图 | 真实中断、目录核对 | 轻量横幅、短文案 |
| History | 旧绿金色；暴露原始 ISO 时间、phase、operation_checkpoint；路径挤压 | 删除边界、任务入口 | 紧凑行、本地化、截断 |
| Model Settings | 绿金色大卡；“离线规则仍可正常使用”错误；大量能力/debug 网格 | 连接/探测/删除/隐私说明 | 统一行和表单、诊断折叠 |
| General Settings | 巨大卡片网格；原始枚举；空资源卡 | 实际默认值、缓存清理 | 分区导航、设置行、友好标签 |
| Recently Deleted | 技术文案；空列表仍占大卡；当前仅显示任务不显示会话 | 恢复、永久删除保护 | 轻空态、记录类型清楚、会话恢复衔接待审 |

## 证据

本轮已查看截图：`artifacts/ui/final-polish/before/01-empty.png` 至 `06-workspace.png`。方案预览已实际打开检查，后续保存补齐。初次 1440 viewport 截图出现黑边，已通过浏览器后台捕获恢复；黑边图未作为验收证据。

## 必须继续验证

Undo/Recovery/运行中 fixture、长文本、5000 files、500 messages、键盘菜单、Dialog focus、五个窗口尺寸、DPI、desktop smoke 均未验收。截图不能证明无障碍或性能通过。
