# Guixu 核心 AI-only 重构报告

日期：2026-09-19  
版本：0.1.0 dev

## 结论

用户报告的三个核心问题已在源码层完成修复：

1. 分类模板现在可以点击、键盘打开、查看详情、使用、复制并编辑；使用后会准确传递 `template_key`。
2. 整理主链路不再用本地规则、扩展名或“图片/文档/音频”模态目录假装 AI 分类。auto/template/fixed 全部进入内容解析、AI 分类树规划与 AI 文件分类。
3. `compile → approve → execute` 将 task revision、plan basis revision、批准 revision、plan ID 与 plan hash 分离并复核；批准本身不会让 plan stale，错误 code 会具体显示。

## 现在的真实流程

只读扫描 → 按模态选择解析器 → FileProfile/evidence → AI Planner → 用户编辑/批准 taxonomy → 批量 AI 内容分类 → 人工审阅 → 确定性 plan → plan 批准与复核 → no-clobber 执行 → 日志/撤销。

AI 仍只能输出允许的 category ID、证据引用、原因与置信度；磁盘路径完全由已批准 taxonomy 和确定性执行器生成。

## 关键实现

- 删除运行时 RuleEngine、规则 API/UI、`classification_mode` 和 `TYPE_CATEGORIES` fallback。
- 新增统一 FileProfile 文件上下文、parser 状态/警告与安全 derivative。
- 新增模型 capability gate、隐私 scope hash 授权、预算和受控视觉输入。
- 新增 `AITaxonomyPlanner` 与 `AIFileClassifier`，批量事件及 visual caption 持久证据。
- 新任务默认 AI 自动规划；模板仅作 guidance；固定类别仍由 AI 判断文件归属。
- taxonomy 批准前可重命名、增删、改父级；分析页显示 AI 事件进度。
- 数据库 schema v2 与 Alembic 0002，v1 升级前自动 SQLite backup。
- 执行响应包含逐操作 state/error code；源文件外部变化返回 `SOURCE_CHANGED` 且不移动。

## 验证总览

- 后端全量：133 passed，2 warnings。
- 前端：14 passed；typecheck 退出 0；production build 退出 0。
- 10 个同扩展名文本文件完整 AI-only 临时目录闭环：通过，分别进入两个内容语义目录。
- 全 JPG 视觉描述证据分类：通过测试 fake vision 合约；不代表真实模型质量。
- plan 批准回归、真实源文件变化、执行、日志与撤销：通过。
- Windows onedir/portable、冻结诊断与 worker：通过并已重建。

## 仍需外部补证

- DeepSeek：无真实 Key，未调用，未产生费用。
- 本地 Qwen：常见服务端口未监听，未运行真实模型。
- 可见 pywebview 全流程：本轮隐藏 smoke 无主窗口句柄，未宣称通过。
- Inno Setup 安装器、Authenticode 签名、干净 Windows 与多系统/高 DPI 矩阵：未完成。

上述阻塞不影响源码、测试、数据库迁移、onedir 与 portable 的交付，但在完成前版本保持 dev。
