# AI-only 核心重构审计

日期：2026-09-15  
阶段：AI-only PHASE 1（审计现有代码与测试）  
结论：当前 0.1.0 的安全执行器可用，但语义分类主流程不是 AI-only；`auto_plan`、视觉理解与 AI 分类树规划尚未实现。

## 审计范围与基线

- 阅读：本轮完整目标、`docs/00_BLUEPRINT.md`、`PROJECT_STATUS.md`。
- 搜索范围：`backend/src`、`backend/tests`、`frontend/src`、`frontend/tests`、`contracts`、`seed`。
- 后端基线：`backend/.venv/Scripts/python.exe -m pytest -q`，退出 0，121 passed，2 warnings。
- 前端基线：`npm run test:run -- --reporter=dot`，退出 0，12 passed。
- 类型基线：`npm run typecheck`，退出 0。
- 计划闭环复核：`backend/.venv/Scripts/python.exe -m pytest -q tests/integration/test_safe_operations_api.py -vv`，退出 0，2 passed。

现有绿色测试将规则引擎、`universal.types` 和按模态生成目录视为预期行为，因此不能作为 AI-only 验收证据。

## 1. 当前所有本地分类决策入口

1. `backend/src/guixu/domain/classification.py`
   - `RuleEngine` 可按扩展名、相对路径、文件名、模态、大小、MIME、文本关键词、图片尺寸和时长命中规则。
   - `force_category` 与 `suggest_category` 可直接影响最终 category ID。
   - `classify_universal_types` 将 `modality` / `document_kind` 直接映射到 `universal.types.*`。
2. `backend/src/guixu/application/classification.py`
   - 先执行 `RuleEngine`；`exclude` 与 `force_category` 可绕过模型。
   - `template_key == universal.types` 时直接执行本地模态分类。
   - 只有其余模板且存在 callback 时才调用模型。
3. `backend/src/guixu/application/operations.py`
   - 当 plan input 没有 taxonomy 时，`TYPE_CATEGORIES` 把模态直接映射为“图片/文本/文档/音频/视频”目录。这是第二条本地语义 fallback。
4. `frontend/src/pages/TaskScanPage.vue`
   - 可从人工选择生成“同扩展名强制类别”规则，继续固化扩展名到最终类别的映射。
5. `frontend/src/pages/RulesPage.vue` 与 `/api/v1/rules*`
   - 向用户暴露规则中心及规则创建/测试能力。

扫描器和 Parser 中的扩展名/MIME/签名识别用于选择解析器，属于必须保留的解析路由，不属于上述待删除语义分类。

## 2. `universal.types` 调用路径

- `seed/templates.json` 内置定义并创建 image/text/pdf/word/slides/sheet/audio/video 分类节点。
- `frontend/src/pages/NewTaskPage.vue` 默认 `templateKey = universal.types`，挂载时又强制 `classification_source = template`。
- 新建任务提交始终携带该 `template_key`。
- `start_task` 在未给模板 key 时再次 fallback 到 `universal.types`，直接复制模板节点成为 draft taxonomy。
- `approve_taxonomy` 从 policy 读取模板 key，缺省再次 fallback 到 `universal.types`。
- `ClassificationService` 命中该 key 后调用 `classify_universal_types`，不调用 AI。
- `OperationService.compile` 对没有 taxonomy 的输入再次按 `TYPE_CATEGORIES` fallback。
- 后端 integration/classification/reliability 测试把这条路径当作正常行为。

## 3. AI 当前实际参与的步骤

- 模型页面可创建、探测和停用 DeepSeek/Qwen profile。
- `ModelGateway.classify` 能在已有 approved taxonomy、已有 FileProfile、已有隐私授权和预算时构造受限分类请求。
- 传输层会调用 DeepSeek 或 Qwen 的 OpenAI-compatible chat 接口。
- 返回 JSON 后由 classification schema、允许类别集合与 evidence ID 集合校验。

AI 目前只参与“非 universal 模板 + 已选模型 + 已有 consent”的逐文件分类；不参与目录扫描、解析、安全路径计算和文件操作，这是正确边界。

## 4. 当前根本没有调用 AI 的步骤

- `auto_plan` 没有 Taxonomy Planner 实现，启动任务不会创建 taxonomy。
- `fixed_categories` 没有从 fixed tree 创建受限 taxonomy 的实现。
- 模板 taxonomy 直接复制 seed nodes，不是 AI 在 guidance 下规划。
- `universal.types` 完全走本地模态映射。
- 图片 Parser 只生成元数据/OCR 等本地证据；没有将受控图片 derivative 发送给 vision 模型生成视觉描述的主链路。
- AI 调用没有 planner/classifier 分阶段事件，也没有 batch 分类和部分失败恢复。

## 5. 模板为什么不能真正使用

- 最新源码已给卡片增加点击/键盘跳转，修复了“卡片完全点不了”的表层问题。
- 仍缺模板详情、guidance/capability/examples 展示和“复制并自定义”。
- 新建任务页无论入口为何都会强制 `classification_source = template`，默认又是 `universal.types`。
- 模板 definition 主要保存固定 nodes；没有 planner guidance/classifier guidance 契约。
- 点击模板只能选择一个预制 taxonomy；不能证明 AI Planner 或视觉理解实际运行。

## 6. DeepSeek / Qwen 是否真正进入分类链路

- 对非 `universal.types` 模板：在 taxonomy 批准后，后端为每个文件调用选中的 profile，能进入对应 adapter。
- 对当前默认任务：不会，因为默认 `universal.types` 在 `ClassificationService` 内先被本地分支截获。
- 对 `auto_plan`：不会，因为没有 planner。
- 对图片：即使进入 classifier，也没有明确的 vision derivative 输入与 capability gate，不能证明基于图像实际内容分类。
- 前端没有任务级隐私 consent 操作，云模型通常会在 `PRIVACY_CONSENT_REQUIRED` 停止；后端虽有 consent API，UI 未接入。

## 7. approve → execute 失效分析

- 当前源码中批准计划不增加 task revision，批准只把同一 immutable `plan_id + plan_hash` 从 validated 改为 approved。
- `SqliteOperationJournal.approve` 已支持同 ID/同 hash 的幂等重试；当前安全 API 回归的 approve → execute → undo 通过，故截图中的旧错误在当前源码无法复现。
- 仍存在的缺陷：执行 API 把 `TASK_BUSY`、`REVISION_CONFLICT`、`PLAN_NOT_APPROVED`、`PLAN_HASH_MISMATCH`、scope 问题等合并为同一句文案；前端 `request()` 丢弃结构化错误 code；批准后没有重新读取并核对 plan 状态；磁盘级冲突只写 operation state，用户无法从执行入口得到明确说明。
- 后续必须补充专门的 plan identity/status 契约、结构化错误显示及 source-changed regression，不能仅依赖刷新 revision。

## 8. 分类结果为什么主要停留在模态级别

唯一默认入口被前端强制成 `template + universal.types`，该模板及 `classify_universal_types` 的设计目标就是把文件映射到类型目录；如果没有 taxonomy，计划编译器又使用 `TYPE_CATEGORIES` 做同样 fallback。内容 Parser 虽能提取文本/OCR，默认分支不会把这些内容交给 AI 做语义判断。

## 9. 本次删除 / 重构范围

- 删除 `RuleEngine`、规则匹配 AST、规则应用服务与主流程规则快照依赖；兼容旧数据库表时仅保留不可执行的 legacy 数据。
- 删除 `classify_universal_types`、`TYPE_CATEGORIES` 和所有按模态生成最终目录的 fallback。
- 从默认设置、契约和 UI 删除 `classification_mode` 及 rules_first/ai_first/rules_only。
- 隐藏/删除主导航规则中心、反馈转规则 UI 和新任务的纯规则表达。
- 将 `universal.types` 从新任务和模板列表移除；如为旧库保留 seed，只标记 legacy，不参与新任务。
- 新增统一 AI Planner、AI-only Classifier、capability gate、视觉 derivative、任务 consent UI、AI 事件与 batch 状态。
- 将模板改成 prompt/guidance/constraint，而非可执行规则。

## 10. 必须保留的安全逻辑

- 目录 grant、规范路径校验、scope 隔离和目录穿越防护。
- plan_id、plan_hash、settings/taxonomy/source snapshot 哈希与明确批准。
- 不覆盖、collision policy、目标出现检查、source fingerprint、磁盘空间和文件锁处理。
- 操作 journal、原子检查点、恢复、历史、undo 与 undo conflict。
- 隐私 consent、最小出站数据、预算、Key 凭据存储和日志脱敏。
- AI 只能返回 taxonomy/category ID、理由和 evidence refs；AI 不得返回或执行路径/命令。

## 阶段结论

PHASE 1 审计完成。已确认核心偏差是两套本地 fallback 与缺失 Planner/视觉链路，不是单一 UI Bug。下一阶段先停用本地分类路径和默认 `universal.types`，以失败显式化取代静默类型分类；随后再统一 FileProfile 和接入 AI Planner/Classifier。
