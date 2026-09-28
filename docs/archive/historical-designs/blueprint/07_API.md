# API、桌面桥与错误契约

> **兼容性提示：** 模板 API 和旧分类模式已于 2026-09-20 从运行时契约移除；机器可读现状以 `contracts/openapi-runtime.json` 为准。

## 1. 协议

REST根路径 `/api/v1`，JSON UTF-8。contracts/openapi.json 是机器可读的初始契约。生产运行时由FastAPI类型生成OpenAPI，CI比较关键字段与本契约，避免前端和后端各自发明字段。

除`/health`的最少健康信息和带独立签名的media ticket之外，API要求 `X-Guixu-Session`。POST／PATCH／PUT／DELETE命令使用 `Idempotency-Key`；任务更改还传 `expected_revision`。Key只是请求去重，不是用户身份认证。

成功为 `{data:...,meta:{request_id,...}}`；失败为 `{error:{code,message,details,retryable},request_id}`。执行长任务返回202和task_id／状态，不能在HTTP连接里同步跑完整目录分析。

分页默认100最大500，返回items、total、next_cursor。cursor为后端生成不透明值；排序有稳定ID作为二级键。事件轮询以after_seq递增，默认最多200；重连可以续读。

## 2. 桌面桥

`select_directory(purpose)` 打开原生选择器，purpose只允许source/output/export/component_import；返回grant_id、display_path、exists、writable与风险提示。选择取消返回cancelled，不算异常。

`register_typed_directory(path,purpose)` 用于用户直接输入路径，后台与原生选择相同校验；授权只发生在用户主动提交路径后。`reveal_registered_file(file_id)` 只允许已登记任务文件；不能接任意shell字符串。

临时grant保存在主进程授权注册表。POST /tasks只接grant_id，不能通过JSON请求传任意C盘路径获得访问权限。重启后的任务使用已保存并被重新核验的授权范围，不能静默扩大。

## 3. 接口清单

| 分组 | 方法与路由 | 关键输入／行为 |
|---|---|---|
| 系统 | GET /health | 仅版本和ready，不暴露路径／任务 |
| 系统 | GET /capabilities | 组件、运行环境与功能开关 |
| 设置 | GET /settings；PATCH /settings | revision + 白名单changes |
| 组件 | GET /components；POST /components/import | 授权资源包grant，验证manifest和hash，不执行安装脚本 |
| 模型 | GET/POST /models | 新建不自动调用用户文件 |
| 模型 | PATCH/DELETE /models/{model_id} | 版本检查；删除连接不删历史快照 |
| 密钥 | POST /models/{model_id}/secret | 只写不读明文，日志过滤body |
| 探测 | POST /models/{model_id}/probe | 内置非隐私样本，返回各能力结果 |
| 模板 | GET/POST /templates；GET /templates/{template_id} | POST仅用户模板 |
| 模板 | POST /templates/import；POST /templates/{template_id}/duplicate | schema校验、创建版本，不覆盖内置 |
| 模板 | DELETE /templates/{template_id} | 仅用户模板，历史快照不受影响 |
| 规则 | GET/POST /rules；PATCH/DELETE /rules/{rule_id} | AST与目标ID校验 |
| 规则 | POST /rules/test | task_id、file_ids、draft_rule，只返回命中预览 |
| 任务 | GET/POST /tasks | source_grant、output_grant、settings、name |
| 任务 | GET/PATCH/DELETE /tasks/{task_id} | 配置修改只限DRAFT；历史删除需要确认丢失撤销记录 |
| 启动 | POST /tasks/{task_id}/start | expected_revision；direct_move附受限preauthorization |
| 控制 | POST /tasks/{task_id}/pause、resume、cancel | 不把cancel解释为rollback |
| 事件 | GET /tasks/{task_id}/events | after_seq、limit |
| 文件 | GET /tasks/{task_id}/files | category／modality／status／query过滤 |
| 详情 | GET /tasks/{task_id}/files/{file_id} | Profile、建议、最新review、完整本地路径 |
| 重析 | POST /tasks/{task_id}/reanalyze | 明确file_ids／失败筛选，失效旧计划 |
| 预览 | POST /tasks/{task_id}/files/{file_id}/preview-ticket | 返回短期只读资源票据 |
| 媒体 | GET /media/{ticket} | 单文件有限权限，支持Range，禁止任意路径 |
| 规则理解 | POST /tasks/{task_id}/policy/compile | 用户文字+当前限制，需模型预算但不必发文件 |
| 分类树 | GET /tasks/{task_id}/taxonomies | 各区域的当前树与版本 |
| 分类树 | POST /tasks/{task_id}/taxonomies/replan | scope_ids、新策略，进入新草稿 |
| 修改树 | PUT /tasks/{task_id}/taxonomies/{taxonomy_id} | expected_revision + 受限新树，返回新taxonomy_id |
| 批准树 | POST /tasks/{task_id}/taxonomies/{taxonomy_id}/approve | tree_hash匹配后继续分类 |
| 审阅 | POST /tasks/{task_id}/reviews/bulk | file_id、taxonomy_id、category_id、decision；最多500项 |
| 执行计划 | GET /tasks/{task_id}/plan；POST /tasks/{task_id}/plan/compile | 只返回／生成当前不可变计划 |
| 批准计划 | POST /tasks/{task_id}/plan/approve | plan_id、plan_hash、用户确认 |
| 执行 | POST /tasks/{task_id}/execute | 已批准plan_id/hash + expected_revision |
| 恢复 | POST /tasks/{task_id}/recover | inspect或resume；先核验磁盘 |
| 撤销 | POST /tasks/{task_id}/undo/plan；POST /tasks/{task_id}/undo/execute | 撤销也是独立计划，执行前要匹配hash |
| 报告 | GET /tasks/{task_id}/report；POST /tasks/{task_id}/export | csv/json、export grant，不直接操作源文件 |
| 授权 | POST /tasks/{task_id}/consents；DELETE /tasks/{task_id}/consents/{consent_id} | 数据类型／服务／预算；撤销后停止新请求 |
| 清理 | POST /cache/clear | 缓存类型与范围，不清operation journal |
| 诊断 | GET /diagnostics | 脱敏环境报告，不含Key／全文 |

所有task_id、file_id、scope_id、taxonomy_id需要验证属于同一任务，不能只验证UUID格式。分类category存在也必须属于该文件scope当前批准的树。

## 4. 核心请求示例

新建：

```json
{"name":"资料整理","source_grant":"grant-source-example","output_grant":null,"settings":{"scan_mode":"preserve_top_level","operation_mode":"preview_move","organization_strategy":"hybrid","classification_source":"auto_plan","classification_mode":"rules_first","max_depth":2}}
```

settings允许省略未改字段，由后端统一使用seed默认值，持久化时保存完整结果。若rules_only配auto_plan，返回INVALID_CONFIGURATION，不默默改成调用AI。

批准执行计划：

```json
{"expected_revision":14,"plan_id":"plan-example","plan_hash":"完整SHA256","acknowledge_source_changes":true}
```

请求示例中的example ID和“完整SHA256”是阅读占位说明，不是合法真实ID；实际Schema与运行时使用UUID和64位十六进制hash。

## 5. 错误码与用户处理

| HTTP | code | 行为 |
|---|---|---|
| 400 | INVALID_CONFIGURATION / INVALID_TEMPLATE | 就地指出字段与冲突 |
| 401 | SESSION_INVALID / MODEL_AUTH_FAILED | 前者重新打开安全会话；后者重新配置Key |
| 403 | PATH_OUTSIDE_GRANT / PRIVACY_CONSENT_REQUIRED | 不执行／不上传，提示授权范围 |
| 404 | TASK_NOT_FOUND / FILE_NOT_FOUND / MODEL_NOT_FOUND | 保留用户上下文，不伪造空成功 |
| 409 | REVISION_CONFLICT / PLAN_STALE / TARGET_APPEARED | 刷新并重新生成／批准，不自动覆盖 |
| 409 | RULE_CONFLICT / SCOPE_CONFLICT / IDEMPOTENCY_CONFLICT | 精确显示冲突项 |
| 422 | SCHEMA_INVALID / CATEGORY_NOT_ALLOWED / PATH_INVALID | 拒绝模型或用户非法输入 |
| 423 | FILE_LOCKED / TASK_BUSY | 可重试或跳过，不能强行解锁 |
| 429 | PROVIDER_RATE_LIMIT / BUDGET_EXCEEDED | 退避或安全暂停 |
| 503 | COMPONENT_MISSING / MODEL_UNAVAILABLE / DB_UNAVAILABLE | 相关能力不可用，其他独立功能仍可用 |
| 507 | DISK_FULL | 保留源、停在安全检查点 |
| 500 | OPERATION_FAILED / RECOVERY_CONFLICT | 记录request_id，详情脱敏，不露原始Key |

SOURCE_CHANGED、UNSUPPORTED_FORMAT、LOW_EVIDENCE、UNDO_CONFLICT一般作为逐文件业务结果返回，不必让整份任务HTTP500。

## 6. 幂等与并发

幂等键保存请求摘要和首次响应，密钥接口不保存明文body。重复execute必须返回同一执行状态，而不是再次移动。即使幂等记录过期，operations中唯一(plan_id,file_id)仍防止重复指令。

两个页面同时修改任务，第二个以旧revision提交时409。批准与开始执行需要CAS事务，在同一任务锁下检查源快照和状态；不能先释放锁再允许改类后执行旧路径。

## 7. 列表与计数口径

discovered=扫描实际发现；eligible=未排除且允许整理；profile_ready与profile_partial分开；suggested_high、needs_review、excluded、conflict互斥计数通过后端聚合。计数可能随人工review变化；UI不用本地数组长度推断全任务数量。

report包含scan_summary、classification_summary、execution_summary、undo_summary以及warnings、artifacts。report_only的executed_count必须是0，不把“分类成功数”冒充“已移动数”。

## 8. 操作项与反向计划补充

GET /tasks/{task_id}/operations按plan_id分页返回执行或撤销逐项预览，支持state过滤；与GET /plan的汇总分开，避免大计划一次传几万行。Plan有plan_kind和parent_plan_id；Operation有reverses_operation_id。撤销copy的专用recycle_copy动作只由后端反向计划编译器生成，前端和AI不可任意调用。模型DELETE为停用并保留历史引用，不删除已存在consent依赖。policy/compile输出必须遵循contracts/schemas/policy-result.schema.json。

## 9. 草稿分类输入补充

POST /tasks与草稿PATCH可接template_key、template_version、fixed_tree、user_instructions、rule_ids。固定类别模式的fixed_tree遵循TaxonomyDraft；后端按scope实例化，而不是要求用户先知道taxonomy_id。任务GET以classification_request结构返回这些输入。后端持久化输入与模板版本快照，不能只留在Pinia。默认值合并后再次验证完整TaskSettings，包括task_budget（不是budget）；consents请求中的budget字段表示该次出站授权预算，两者校验取更严格者。
