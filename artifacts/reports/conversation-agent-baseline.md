# Conversation Agent 稳定基线

日期：2026-09-19  
状态：PASSED（源码与自动化基线稳定；外部环境项继续单列）  
范围：PHASE A，只读审计、测试与恢复点记录；未进行 Conversation Agent 或 UI 大改。

## 1. 基线结论

当前工作树已经形成可继续演进的 AI-only 安全闭环：

`Scanner → Parser/FileProfile/Evidence → AITaxonomyPlanner → taxonomy 审批 → AIFileClassifier → 人工审阅 → PlanCompiler → plan 审批 → FileOperationEngine → journal/history/undo`

DeepSeek Vision 修复已经有同日真实 `deepseek-flash` 证据，当前自动化回归也保持通过。Conversation Agent 应作为这条链路之上的状态编排层接入，不应让模型接触任意路径或磁盘 API，也不应重写已验证的执行器、撤销、授权和解析模块。

Git 现场不是干净提交：当前分支为 `main`，HEAD 为 `01dc2f7b7179a5de189abc64c1794cf5126b7517`（`Enable template selection and AI classification entry`），现场有 52 个修改、3 个删除、22 个未跟踪项。AI-only 与 Vision 收口主要存在于这批未提交改动中，因此这个 HEAD 不能单独代表当前稳定基线；进入下一实际开发阶段前应先由用户决定是否形成独立基线提交。本轮未提交、未重置、未覆盖这些既有改动。

## 2. 当前真正完成的功能

- Windows 桌面壳、FastAPI 本地服务、Vue 3 工作台、SQLite 迁移和本地会话鉴权已存在。
- 目录授权、三种扫描方式、稳定 `file_id`、本地多模态解析、FileProfile/evidence、受控图片 derivative 和解析缓存已存在。
- DeepSeek/Qwen OpenAI-compatible 模型配置、能力探测、隐私授权、预算、调用审计和错误映射已存在；本地 Qwen 的真实运行仍缺外部服务。
- `auto_plan`、`template`、`fixed_categories` 都进入 AI taxonomy/file classification 主链；模板在当前实现中是 planner guidance，不是本地语义分类器。
- taxonomy 编辑/批准、批量 AI 分类、人工审阅、确定性计划编译、plan revision/hash/approval、no-clobber 执行、操作日志、恢复和 undo 已存在。
- Windows onedir/portable 已构建；安装器、签名、干净机矩阵仍未完成。

## 3. DeepSeek Vision 状态

结论：修复已完成，可作为 Conversation Agent 前的视觉基线。

- 真实模型 ID 为 `deepseek-flash`。
- vision probe 已由损坏的硬编码 1×1 PNG 改为 Pillow 动态生成、回读校验的 64×64 RGB PNG。
- 真实 text/json/vision probe 均为 supported，能力在重建数据库服务对象后仍保持 `vision_verified=true`。
- 项目合成 JPG 已通过 Base64 data URL 的 `image_url` multimodal block 得到非空 `visual_description`，并写入 FileProfile evidence；图片 + JSON mode 也有成功证据。
- 当前轮没有可再次使用的用户 Key，因此没有重复产生真实 API 费用；本轮重新运行的模型与分类自动化测试全部通过。语义质量金标准、完整可见桌面链路和本地 Qwen 仍是独立补证项。

详细证据见 `artifacts/reports/deepseek-vision-probe-fix.md`。

## 4. AI-only 审计

结论：运行时 AI-only 仍成立，但数据库/种子/旧静态契约保留兼容残留，后续迁移时必须显式处理。

已确认：

- `RuleEngine`、规则 API/UI、`classify_universal_types`、plan compiler 的 `TYPE_CATEGORIES` fallback 和 `classification_mode` 运行时入口已删除。
- Planner 只接受模型返回的受限 category ID/name/parent/criteria，并拒绝路径样式类别名；Classifier 校验精确 file ID、批准 taxonomy 的 category ID 和图片视觉描述。
- PlanCompiler 根据批准 taxonomy 确定性生成目标路径；AI 不能提供任意目标路径，也不能直接调用文件系统执行。
- 模型失败会进入失败事件，不会回退到扩展名、文件名、路径关键词或模态分类。

兼容残留：

- `seed/templates.json` 和数据库模板快照仍包含历史 `universal.types`，服务层会过滤并拒绝新任务使用。
- `contracts/openapi.json` 仍含旧 `classification_mode`，而当前运行时快照为 `contracts/openapi-runtime.json`；这是静态契约漂移，后续契约清理时应修正。
- `rules` 表、`rules_snapshot_json` 以及 classifications 的 `source='rule'` 仍在数据库契约中作为历史兼容字段，但没有当前运行时语义规则入口。

## 5. 当前模板系统位置

模板仍是完整产品入口，而非仅有历史数据：

- 数据：`seed/templates.json`、`template_versions`、`tasks.template_snapshot_json`、classification request 的 `template_key/template_version`。
- 后端：`TemplateService`，模板列表/详情/导入/复制 API，任务创建与 `AITaxonomyPlanner._template_guidance`。
- 前端：`/templates`、`TemplatesPage.vue`、`TemplatePicker.vue`、AppShell 导航，以及 `NewTaskPage.vue` 的模板分类来源/选择器。
- 测试：模板详情、使用、复制以及路由传递 `template_key` 的现有覆盖。

PHASE D 不能只删页面。应先禁止新会话写入模板依赖，再移除 runtime branching/API/UI，最后保留旧任务的不可变模板快照供历史查看。

## 6. 当前任务数据模型

当前核心聚合是一次性 `Task`：

- `tasks` 保存状态、阶段、revision、settings/model/rules/classification/template 快照、计数和 checkpoint。
- `task_scopes` 保存授权扫描/输出范围。
- `files` 使用稳定 ID，并同时保留 original/current path、文件系统身份、sha256 和扫描状态。
- `file_profiles` 按 cache key/parser/options 保存语义证据。
- `taxonomies/categories` 已有按 scope 的版本、状态和 tree hash，可作为未来 PlanVersion 的重要输入，但目前不等于会话计划版本。
- `classifications/reviews` 保存 AI 结果、证据引用与人工决策。
- `plans/operations/operation_events/created_directories` 保存版本化、哈希化、可审计的磁盘计划与执行状态。
- `task_events/model_calls/privacy_consents` 保存流程、模型与授权审计。

当前没有 `Conversation`、`Message`、`ConversationContext`、`ExecutionRound`、`FileReference` 或 `deleted_at`；任务 API 也没有单删/批量删/最近删除/恢复入口。数据库级联删除会破坏 journal/undo 元数据，所以 PHASE C 必须采用软删除/可恢复视图，不应直接删除 task 行。

## 7. 当前 UI 架构

当前 Vue Router 仍围绕一次性任务向导：

- `/` 首页
- `/tasks/new` 大表单
- `/tasks/:id/analyze|taxonomy|review|run|report` 分阶段页面
- `/templates`、`/history`、`/models`、`/settings` 独立管理页

它能够完成现有安全闭环，但信息架构是“新建任务 → 分步执行”，不是目标三栏对话工作台。可复用的是 API service、文件映射/证据/分类树/执行条/undo preview 等业务组件；路由壳、模板页和复杂新任务表单准备逐步退出主流程。

## 8. 执行、恢复与 undo 状态

- Plan 带 `plan_id`、版本、`plan_hash`、settings/taxonomy/source snapshot hash、basis revision 和 approved revision。
- 执行前复核授权范围、plan 状态/hash/revision 和源文件身份；外部修改返回 `SOURCE_CHANGED`。
- 执行器支持 move/copy/skip/noop，采用 no-clobber/keep-both，先写 journal，再按状态机执行。
- undo 由已完成 forward plan 编译为独立 undo plan，并继续走检查、批准、journal 和执行状态；不是模型直接反向移动。
- crash recovery、冲突状态、创建目录记录和操作事件已有测试覆盖。

这些模块应保持为 Conversation Agent tool 的唯一副作用出口。

## 9. Conversation Agent 最小切入点

建议最小切口是新增一个无磁盘权限的 `ConversationCoordinator`，而不是改写底层服务：

1. Conversation/Message/Context 只保存用户意图、引用对象和已确认事实。
2. 每次需要实际分析时，由 coordinator 创建或关联一个受限 Task/ExecutionRound，调用现有 scan/parse/planner/classifier 服务。
3. 方案变更生成新的显式 PlanVersion/taxonomy version；消息只引用版本 ID，不把聊天文本当计划事实源。
4. Agent tools 只映射到现有 application service；`apply_plan` 和 `undo` 必须返回待确认计划，并由既有 approval + FileOperationEngine 执行。
5. FileReference 绑定稳定 `file_id`；文件移动后更新 current path，不以聊天中的路径文本解析“这些文件”。

开始该切口前，应按既定路线先完成 PHASE C 任务软删除/恢复，再完成 PHASE D 新流程去模板依赖，避免新会话模型反向依赖即将淘汰的 Task UI 与 template branching。

## 10. 复用与淘汰清单

继续复用：

- Scanner、PathPolicy、Grant/PrivacyGate
- ParserRegistry、ParsingService、FileProfile/evidence/cache
- ModelGateway、DeepSeek/Qwen adapters、capability probe、model call audit
- AITaxonomyPlanner、AIFileClassifier、TaxonomyService、ClassificationService
- PlanCompiler、OperationService、FileOperationEngine、OperationJournal、Recovery、UndoCompiler
- 稳定 file identity、source fingerprint、plan hash/revision、task/model/privacy events
- 前端 EvidenceDrawer、TaxonomyTree、FileMappingTable、ExecutionBar、UndoPreview 的业务能力

准备淘汰或降为历史兼容：

- 模板导航、页面、选择/创建/复制、模板作为新入口、template runtime branching
- 复杂 `/tasks/new` 表单和一次性任务向导作为产品主入口
- 旧静态 OpenAPI 中的 `classification_mode`、历史 rules/universal.types 契约残留
- 以 Task 记录本身充当用户对话与计划版本的做法

## 11. 当前测试结果

命令：

```powershell
.\backend\.venv\Scripts\python.exe scripts\verify.py all
```

退出码：`0`。

分组结果：

- unit + contract：6 passed
- safety + integration：85 passed
- parsers + API：16 passed
- classification + API：19 passed
- models + API：15 passed
- reliability + safe operations API：10 passed
- security + contract + desktop security：9 passed
- frontend Vitest：16 passed
- frontend typecheck：exit 0
- frontend production build：exit 0，1712 modules transformed

警告/非阻塞问题：Starlette TestClient 弃用提示、Pillow decompression-bomb 边界测试预期警告，以及 pytest 清理 Windows reparse-point 临时目录时的既有 WinError 145 警告。没有测试失败，也没有操作用户个人目录。

## 12. 下一步建议与恢复点

PHASE A 已完成，PHASE B 研究见 `docs/GITHUB_REFERENCE_ANALYSIS.md`。按用户要求，本轮在研究完成后停止，不进入实际功能开发。

下一实际阶段建议：

1. 先形成/确认当前 AI-only + Vision 基线提交，避免在 77 项脏工作树上叠加结构迁移。
2. 进入 PHASE C：设计软删除状态、禁止删除的运行状态、批量删除/恢复 API 与 UI，并保证 journal/undo 元数据保留。
3. 再进入 PHASE D：先切断新流程模板依赖，后移除模板 API/UI/runtime branching，旧任务只读保留 snapshot。
4. 之后再落 Conversation 数据模型与第一版 coordinator/tool boundary。

外部补证继续保留：本地 Qwen、可见 pywebview 完整人工验收、Inno 安装器、签名、干净机/多系统/高 DPI、真实语义质量评测与缺失 ffmpeg/ASR 环境。
