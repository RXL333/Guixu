# AI-only 核心重构实施计划

## 目标与边界

将所有“属于什么类别/进入哪个文件夹/创建什么分类树”的判断收敛到 AI。保留扩展名/MIME/签名作为 Parser 路由，保留所有确定性文件安全、授权、计划、日志、撤销与隐私边界。旧表可以兼容读取，但不能参与新任务。

## 阶段与依赖

1. 审计：记录本地分类入口、AI 调用缺口与执行状态问题；建立真实基线。
2. 移除本地分类：删除运行时 RuleEngine、`universal.types` 和 plan compiler 模态 fallback；新任务无模型必须显式失败。
3. FileProfile：统一源路径/name/extension/MIME/modality、parser status/warnings、内容证据与受控 derivative 描述；分类不得从这些上下文字段直接推导。
4. 模型能力：让 profile capabilities 约束 text/vision/structured output；任务启动前按已扫描模态验证；接入任务 consent。
5. Taxonomy Planner：按 auto_plan/template/fixed_categories 三种入口产生或约束 taxonomy，做 schema、深度、同级、节点数、非法路径校验，并记录 planner 事件。
6. AI File Classifier：只接受 approved taxonomy，支持可配置 batch、重试/部分失败、证据引用、低置信度待确认与分类事件。
7. UI：重做新建任务三入口；模板详情/使用/复制；taxonomy 编辑、重生成与批准；AI 进度和 consent/capability 错误。
8. 状态机：明确 review → compile → approve → execute 的 identity、basis revision 和结构化错误；补充 source changed 与批准不 stale 回归。
9. AI-only 验收：全 JPG 多语义、同扩展名文档语义、template/fixed/no-model/capability、AI 事件、真实临时目录移动和 undo。
10. DeepSeek 真联调：仅在真实 Key、明确 consent 与支持能力存在时运行，否则 SKIPPED_EXTERNAL。
11. Qwen 真联调：仅在本地服务可用时运行，否则 SKIPPED_EXTERNAL。
12. 桌面闭环与打包：验证 pywebview/source package；核心闭环未通过前不发布 0.2.0。

## 影响模块

- 契约与迁移：`contracts/schemas`、OpenAPI snapshot、SQLite migrations、seed defaults/templates。
- 后端：task orchestration、profiles/parsers、models/privacy、taxonomy planner、classification、plan compiler/coordinator。
- 前端：新建任务、模板、分析/分类树/审阅/执行、模型与 API error 类型、导航。
- 测试：architecture/unit/integration/frontend/desktop；仅使用 `tmp_path`、项目 fixtures 或 `artifacts/test-workspaces`。

## 关键验收

- 新任务默认 auto_plan，模型缺失/失败不产生任何类型目录 fallback。
- 所有新分类记录 source=ai 或人工 review；category ID 必须属于 approved taxonomy。
- 同为 JPG 或同扩展名文档能依据 evidence 分到多个语义类别。
- 图片任务在 vision unsupported 时启动失败；支持时实际发送受控 derivative 并生成视觉 evidence。
- template 只提供 guidance/constraint；fixed tree 只限制候选类别。
- approve 不改变 plan identity/hash；真正源变化返回具体 code；临时目录移动与 undo 一致。
- 每阶段运行相关后端、前端与 typecheck，更新状态；最终运行全量、build、现有 lint/type check 和 desktop smoke。

## 风险控制

- 先让旧 fallback 失效并补失败测试，再接新 AI 能力，避免假 AI 成功。
- 数据库兼容字段不等于运行时兼容；旧规则与 universal template 数据只读保留。
- Fake adapter 仅证明架构和契约；真实 DeepSeek/Qwen/Windows 结果分别记录 PASSED/FAILED/SKIPPED。
