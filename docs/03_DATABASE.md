# 领域模型与 SQLite 数据设计

## 1. 公共约定

参考建表文件为 contracts/database.sql。SQLite数据库使用本机UTF-8文本，ID为UUID字符串，时间为UTC ISO-8601字符串，文件大小为64位整数，文件系统mtime_ns使用整数，金额估算使用整数微单位与currency，避免浮点累计误差。JSON列以TEXT保存并加 json_valid校验；Pydantic负责结构层校验。

每次连接开启 foreign_keys。运行时采用Alembic迁移，不在业务启动中散落 CREATE TABLE。首次导入24个模板与默认设置必须幂等，版本更新不覆盖用户自定义数据。

本设计不把原始大文件、图片、音频、视频存到SQLite；只存元信息、摘要、缓存相对路径与校验值。正文缓存本身受隐私策略保护。

## 2. 实体关系

```text
model_profiles ─┐
template_versions ─┼─> tasks ─> task_scopes ─> files ─> file_profiles
rules (snapshot) ──┘        │             │       └─> classifications
                           │             └─> taxonomies ─> categories
                           ├─> reviews ────────────────────┘
                           ├─> plans ─> operations ─> operation_events
                           │          └─> created_directories
                           ├─> task_events
                           ├─> model_calls
                           └─> privacy_consents
```

模板类别ID可跨版本语义稳定，但实例化的分类树有独立 taxonomy_id。categories主键为(taxonomy_id, category_id)，杜绝分类结果误指向其他任务的同名类别。

## 3. 表级定义

### 3.1 settings

`key`主键；`value_json`；`revision`；`updated_at`。保存全局偏好，不保存Key或未加密凭据。任务启动复制所需设置，后续修改全局设置不影响既有任务。

### 3.2 model_profiles

`id`、`name`、`provider`(deepseek/qwen_local)、`runtime`(deepseek/openai_compatible/ollama/lmstudio/vllm/llamacpp)、`base_url`、`model_id`、`secret_ref`、`capabilities_json`、`options_json`、`trust_scope`(cloud/loopback/trusted_lan)、`enabled`、`revision`、时间。

secret_ref只引用Windows凭据条目，GET接口只返回has_secret。capabilities_json包含状态unknown/supported/unsupported、实测时间、证据和限制；model_id变更使能力探测失效。options不允许写任意额外HTTP目的地或工具。

### 3.3 template_versions

`id`、`template_key`、`version`、`name`、`origin`(builtin/user)、`definition_json`、`definition_hash`、`created_at`；唯一(template_key,version)。内置版本不可编辑；复制产生user版本，历史任务引用原快照。

### 3.4 rules

`id`、`name`、`priority`、`enabled`、`scope_json`、`condition_json`、`action_json`、`revision`、时间。condition必须是allowlist AST，禁止eval和脚本。强制类别引用模板语义ID或任务树映射，目标不存在时必须报RULE_TARGET_MISSING，不可创建自由路径。

### 3.5 tasks

`id`、`name`、`status`、`phase`、`revision`、`settings_json`、`settings_hash`、`model_profile_id`可空、`model_snapshot_json`、`rules_snapshot_json`、`counters_json`、`checkpoint_json`、`last_error_code`、`created_at`、`updated_at`、`finished_at`。

checkpoint记录已完成批次ID、扫描游标与待核验操作，不以一个百分比替代真实进度。model_snapshot不含Key。删除model_profile不应破坏历史：FK置空，snapshot继续保留。

### 3.6 task_scopes

`id`、`task_id`、`kind`(whole_tree/protected_child/root_loose/current_only)、`source_root`、`destination_root`、`display_name`、`source_volume_id`、`settings_json`。唯一(task_id,id)，并保证同任务区域的文件集合不重叠；root_loose只能纳入源根直接文件。

### 3.7 files

`id`、`task_id`、`scope_id`、`original_path`、`current_path`、`path_key`、`relative_path`、`basename`、`extension`、`modality`、`mime`、`size_bytes`、`mtime_ns`、`volume_id`、`filesystem_file_id`可空、`sha256`可空、`scan_status`、`exclusion_code`、`companion_group_id`可空、`metadata_json`、时间。

唯一(task_id,path_key)。相同哈希不是同一个file_id。扫描仅保存stat快照；完整sha256延迟到需要内容缓存或执行前计算，避免扫描几十GB目录就全盘读取。执行时必须得到并核对完整哈希。

### 3.8 file_profiles

`id`、`file_id`、`cache_key`、`parser_version`、`options_hash`、`status`(ready/partial/failed/unsupported)、`profile_json`、`payload_cache_path`可空、`payload_hash`可空、`created_at`、`expires_at`可空。唯一(file_id,cache_key)。Profile包含证据项、抽样区间、覆盖度、警告，不仅是一个AI摘要。

### 3.9 taxonomies

`id`、`task_id`、`scope_id`、`version`、`source`(template/fixed/auto)、`status`(draft/approved/superseded)、`policy_json`、`tree_hash`、`created_at`、`approved_at`。唯一(scope_id,version)。修改树新建version，不原地篡改已批准树。

### 3.10 categories

`taxonomy_id`、`category_id`、`parent_id`可空、`name`、`path_segments_json`、`depth`、`ordinal`、`selectable`、`definition_json`、`is_fallback`。复合主键(taxonomy_id,category_id)，父节点引用同taxonomy；应用校验无环、连续depth、名字合法和同级数量。实体待确认目录可存在但默认不创建。

### 3.11 classifications

`id`、`task_id`、`file_id`、`taxonomy_id`、`category_id`可空、`attempt`、`source`(rule/ai/cache)、`model_score`可空、`review_band`、`abstain`、`reason`、`evidence_refs_json`、`warnings_json`、`model_call_id`可空、`input_hash`、`created_at`。唯一(file_id,taxonomy_id,attempt)。abstain=true必须category_id=null；文件内容里的命令永远不能改变这个契约。

### 3.12 reviews

`id`、`task_id`、`file_id`、`taxonomy_id`、`category_id`可空、`decision`(accept/change/skip/quarantine)、`revision`、`note`、`created_at`。唯一(file_id,revision)。存历史决策，不覆盖模型原始建议；最新有效review决定执行候选。人工操作失效于被替换的树时必须重新映射并显示。

### 3.13 plans

`id`、`task_id`、`version`、`plan_hash`、`plan_kind`、`parent_plan_id`、`status`(draft/validated/approved/superseded/executing/finished)、`operation_mode`、`settings_hash`、`taxonomy_hashes_json`、`source_snapshot_hash`、`summary_json`、`authorization_kind`可空(interactive/preauthorized)、`authorization_json`、`created_at`、`approved_at`。唯一(task_id,version)，plan_hash唯一。批准时CAS检查版本与hash，再记录授权；执行请求必须携带plan_id与plan_hash。

### 3.14 operations

`id`、`plan_id`、`file_id`、`ordinal`、`action`(move/copy/skip/noop/recycle_copy)、`source_path`、`target_path`可空、`target_key`可空、`source_snapshot_json`、`expected_sha256`可空、`temp_path`可空、`state`、`reverses_operation_id`、`actual_target_path`可空、`result_sha256`可空、`error_code`、`companion_group_id`、`updated_at`。

唯一(plan_id,file_id)和(plan_id,target_key)。state见08的固定操作状态机。批量目标名在plan编译时确定；执行时发现新冲突，不临时改个名字绕过用户批准。

### 3.15 operation_events

`id`整数自增、`operation_id`、`seq`、`event_type`、`payload_json`、`created_at`；唯一(operation_id,seq)。只追加，记录意图、临时写入、哈希校验、目标发布、源删除、提交、撤销等。state与event同事务更新；数据库事务不能与磁盘rename原子提交，所以必须有重启核验。

### 3.16 created_directories

`id`、`plan_id`、`path`、`path_key`、`created_by_task`、`removed`、`created_at`；唯一(plan_id,path_key)。仅本任务确实创建且当前仍为空的目录可以在撤销后删除；既有目录永远不删。

### 3.17 task_events

`id`整数自增、`task_id`、`seq`、`event_type`、`payload_json`、`created_at`；唯一(task_id,seq)。用于增量轮询、恢复后UI重建和审计；payload只放摘要和计数。

### 3.18 model_calls

`id`、`task_id`、`provider_profile_id`可空、`purpose`(probe/policy/caption/planning/classification/repair)、`model_id`、`request_hash`、`response_status`、`input_tokens`可空、`output_tokens`可空、`estimated_cost_micros`可空、`currency`可空、`latency_ms`、`error_code`可空、`created_at`。

不保存Key、base64、完整请求正文或思维链。调试留存仅可显式开启，脱敏、限制体积并显示保留期限。未知token／价格为null，不记作零。

### 3.19 privacy_consents

`id`、`task_id`、`provider_profile_id`、`scope_hash`、`grant_json`、`granted_at`、`revoked_at`。grant列明是否允许文字片段、去EXIF缩略图、视频帧、ASR文本、文件名、原图及调用／费用预算。新增数据种类、服务端地址或扩大范围必须新授权。

### 3.20 components

`id`、`component_type`、`version`、`status`(missing/ready/invalid/disabled)、`install_path`、`manifest_json`、`manifest_sha256`、`last_verified_at`。资源包必须有校验值、许可来源和本地路径。应用不把用户权重路径转为云URL。

### 3.21 idempotency_keys

`key`、`endpoint`、`request_hash`、`response_json`、`status_code`、`created_at`、`expires_at`。相同key+相同请求返回原结果，相同key不同body返回409。清理幂等记录不影响operations的长期唯一约束。

## 4. 事务策略与关键索引

需要索引：(tasks.status,updated_at)、(files.task_id,modality)、(files.task_id,scan_status)、(files.sha256)、(classifications.task_id,review_band)、(operations.plan_id,state,ordinal)、(task_events.task_id,seq)、(model_calls.task_id,created_at)。首版不要给整个正文建FTS索引。

安全日志使用SQLite短事务并设置FULL同步；程序不能承诺磁盘损坏或文件系统不遵守持久性语义时仍绝对不丢数据。备份使用SQLite backup API或正确关闭后的数据库快照，不在WAL写入期间直接只复制.db文件。

启动迁移前备份；迁移失败留在只读诊断页面，不使用半迁移库继续执行。历史删除与缓存删除分开；仍有撤销记录的任务删除前需提示不可逆地丢失撤销能力，但不得跟着删除用户文件。

## 5. 执行计划hash的组成

使用规范化JSON和SHA-256：任务ID、settings_hash、每区域taxonomy_hash、排好序的操作(action/file_id/source identity/source_sha256/target_path)、冲突处理政策、人工审阅revision、隐私政策revision。哈希中不含Key和临时UI状态。

源文件变化、用户改变类别、树重命名、目的根目录改变都会使旧批准失效。实际执行前的源文件核验不通过，标记SOURCE_CHANGED并跳过／暂停，不用旧分类结果处理新内容。

## 6. 反向计划与外键补充

plans增加plan_kind(forward/undo)、parent_plan_id；forward的parent为空，undo必须引用原计划且同任务。operations增加reverses_operation_id，逐项引用被撤销操作；undo移动使用move反向路径，undo复制使用专用recycle_copy动作。recycle_copy只允许来源于本任务已提交copy、目标身份与hash未变，调用系统回收站；普通分类引擎不能产生此动作。数据库保存这些链接，领域层再验证同任务和动作对应；不能只在内存记撤销关系。执行成功后原操作标UNDONE，反向操作标COMMITTED，并分别写事件。

categories显式selectable布尔列，非可选结构节点不得成为classification或review目标。模型连接的DELETE语义是停用；被consent引用时保留行与凭据引用审计，凭据本体可独立删除。没有历史引用的实体才允许物理删除。用户确认清理整个任务时先按依赖顺序删反向计划/反向操作，再删正向历史，避免自引用RESTRICT意外失败；运行中和恢复中的任务禁止清历史。

## 7. 任务的分类输入快照

tasks.classification_request_json保存template_key、template_version、user_instructions、fixed_tree、rule_ids；tasks.template_snapshot_json保存最终选定模板版本的完整定义。它们不是临时前端状态，退出后仍需恢复。settings_json仅保存TaskSettings，不向严格schema偷偷追加这些业务输入。启动前将用户规则解析为rules_snapshot_json；模板库或规则库后续修改不会改变既有任务。

classification_source=template要求有效template_key，省略version时在草稿保存时解析当时最新版并固定；fixed_categories要求fixed_tree，按各scope实例化并验证；auto_plan允许没有template和fixed_tree，user_instructions可以为空。两种显式分类来源也可带自然语言偏好，但不能推翻固定类别和任务限制。scopes在授权范围校验及扫描时建立；树批准前不开始真实文件操作。
