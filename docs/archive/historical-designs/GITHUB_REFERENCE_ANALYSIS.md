# Guixu Conversation Agent：GitHub 参考项目源码研究

日期：2026-09-19  
阶段：PHASE B — GitHub Reference Research  
边界：只做研究、比较、映射与设计建议；未复制第三方代码，未修改 Guixu 产品源码、数据库、前端或依赖。

## 1. 执行摘要

本次按固定 commit 对五个重点仓库进行了源码级检查，而非只读 README：

| 项目 | 检查 commit | 主要价值 | 最终判断 |
|---|---:|---|---|
| `joshuasoup/file-organizer`（Drift） | `e02830b1c980b0b650c0a3073cfd116274c57c68` | Chat loop、窄工具集、preview 卡片 | Agent 交互最接近；仅借鉴设计，安全能力弱于 Guixu |
| `Venere-Labs/ragfs` | `3aa3e44daadccab8add03676ec8e38f1d34476ac` | 结构化操作结果、trash/history/undo、semantic layer | 借鉴分层和结果契约；不采用 FUSE/runtime/删除实现 |
| `tursodatabase/agentfs` | `0a014ebd4918615baff589ed17486e557e7c6a23` | SQLite tool-call ledger、可恢复 Agent workspace | 借鉴审计 schema；Guixu 自有 SQLite 足够 |
| `BorisBesky/file-organizer-desktop` | `b53f83871ce7f85f2a4c3fe07291892ada2ce792` | Desktop provider/progress/review UX | 只借鉴桌面状态表达；不采用其路径执行与 localStorage 策略 |
| `run-llama/file-organizer` | `e360789a9dc5cb95298c978da188061839cf1571` | describe → categorize 分离、移动后缓存复用 | 借鉴缓存思想；inode-only 与 JSON 状态不可用 |

没有一个项目同时满足 Guixu 的 Windows 桌面、Python/FastAPI/Vue/pywebview、AI-only、按 scope 授权、版本化计划、no-clobber、持久 journal、恢复与 undo 边界。正确方向不是换栈或移植某个项目，而是在现有核心外增加薄的 `Conversation + AgentOrchestrator + Tool Registry`。

三个最重要结论：

1. 模型只应调用稳定 ID 驱动的业务工具；不能把路径、shell、Python 或原始 move/delete 暴露为工具。
2. 聊天历史不是当前状态。ConversationContext、PlanVersion、FileReference、ToolCall 和 ExecutionRound 必须结构化持久化。
3. 语义证据按内容指纹复用，计划与分类按 taxonomy/strategy 版本失效；文件移动不应触发昂贵的 OCR/Vision/LLM 重算。

## 2. Guixu 当前基线与不可退化边界

- AI-only 主链：Scanner → Parser / `FileProfile` / `Evidence` → `AITaxonomyPlanner` → taxonomy 审阅 → `AIFileClassifier` → 人工 review → `PlanCompiler` → approval → `FileOperationEngine` → journal/history/undo。
- 主要定位：`backend/src/guixu/application/ai_taxonomy_planner.py`、`ai_file_classifier.py`、`model_gateway.py`、`plan_compiler.py`、`operations.py`、`undo.py`。
- 数据与安全定位：`backend/src/guixu/infrastructure/db/database.py`、`repository.py`、`operation_journal.py`。
- 当前桌面流程定位：`frontend/src/pages/NewTaskPage.vue`、`TaskScanPage.vue`、`TaskTaxonomyPage.vue`、`TaskReviewPage.vue`、`TaskRunPage.vue`、`HistoryPage.vue`、`ModelsPage.vue`。
- DeepSeek / Qwen 继续通过统一 ModelAdapter 与 capability gate 接入；不得为 Agent 再建一套 provider 调用。
- 现有 plan hash/revision、source fingerprint、授权记录、no-clobber、operation events、恢复和 undo 都要复用。
- 运行时没有 RuleEngine 语义 fallback；新 Agent 也不得用扩展名 bucket、规则或假成功绕过 AI。

## 3. 项目对比矩阵

| 维度 | Drift | RAGFS | AgentFS | Boris Desktop | run-llama | Guixu 结论 |
|---|---|---|---|---|---|---|
| Agent loop | OpenAI tool loop，内存消息 | 无聊天 loop，文件式 op API | SDK 记录 tool call | 固定桌面 workflow | 无 loop | 新增轻量 orchestrator，不上大型框架 |
| Tool 输入 | 多处接受原始 path | JSON op 接受 path，绝对路径可直通 | parameters JSON | Tauri command 接受路径 | CLI path + JSON | 只接受稳定 ID、scope ID、plan ID/hash |
| Preview/approval | TUI preview 后确认 | dry-run；非强人工批准 | 不负责批准 | 表格勾选后应用 | 无 | 复用 versioned plan approval |
| 文件执行 | rename/unlink/rmtree | Rust fs；delete 可硬删 fallback | 虚拟 DB FS | `fs::rename` | `os.rename` | 只允许现有 FileOperationEngine |
| Undo | 单个 last_action | history ID + trash/逆操作 | tool history 非真实磁盘 undo | 无可靠持久 undo | 无 | 复用 journal + UndoCompiler |
| 状态 | 会话不持久；SQLite/Chroma 索引 | JSONL + LanceDB | 单 SQLite KV/files/tool calls | localStorage | JSON | 新增显式 Conversation schema |
| Semantic cache | path-keyed metadata/vector | chunk/vector + watcher | 非重点 | 弱持久 | inode description | fingerprint + parser/model/prompt version |
| 桌面 UX | CLI/TUI | FUSE/CLI | CLI/SDK | 桌面表格 | CLI | 三栏 Chat-first + 业务卡片 |
| 相对安全成熟度 | 较弱 | 概念可取，执行边界弱 | 审计好，真实磁盘不适用 | 明显较弱 | 明显较弱 | 保留现有核心，不重写 |

## 4. 重点项目源码研究

### 4.1 Drift：`joshuasoup/file-organizer`

仓库：https://github.com/joshuasoup/file-organizer

源码定位：Agent loop 在 `drift/chat/loop.py`；registry 在 `drift/chat/tools/__init__.py`；搜索/结构/预览/移动/删除/撤销分别在 `search.py`、`structure.py`、`previews.py`、`moves.py`、`delete.py`、`undo.py`；计划应用在 `plan_ops.py`；索引在 `drift/indexer/pipeline.py`、`scan.py`；元数据/向量在 `drift/store/meta.py`、`chroma.py`；undo 存储在 `drift/undo.py`。固定 commit 的 46 个文件中未发现测试。

每轮由内存 `messages` 驱动：加入 user message，调用 OpenAI completion；若有 tool calls，则落 assistant tool-call message、逐个本地执行、追加 tool result，再调用一次模型生成自然语言。上下文只保留 system 与约 18 条/12k 字符尾部消息，并避免拆散 assistant/tool 对；没有持久 ConversationContext。

实际 tools：`search_files`、`find_duplicates`、`suggest_structure`、`preview_moves`、`move_files`、`delete_items`、`undo_last_action`。搜索通过 Chroma 返回路径；AI 以路径而非稳定 ID 引用文件。Structure 用 HDBSCAN + GPT-4o 命名目录，对未 embedding 文件还有扩展名 bucket fallback，违反 Guixu AI-only。

Preview 与 move 分开，TUI 会询问确认；但模型仍提供原始 src/dst。`plan_ops.py` 只验证解析后路径仍在 scan root 且 destination 不存在，然后 `rename`，没有 plan revision/hash、持久授权、source fingerprint 或 journal。Delete 可在确认后 `unlink`/`rmtree`，不可迁移。

Undo 只保存最新 move 到 `last_action.json` 并反向 rename；无多轮依赖、外部修改或冲突处理。SQLite metadata 保存 path/type/size/mtime/content_hash/embedding_model/indexed_at，主要用 size+mtime+model 判定新鲜；移动后全量重索引，未做稳定 identity 重绑定。

可迁移：tool loop 节奏、窄工具集、结果回灌、preview card。不可迁移：内存会话、路径引用、模型给目标路径、delete、单层 undo、扩展名 fallback、重模型/全盘索引、CLI 专用交互。Semantic Search 可作为以后只读发现能力，但第一版应先用已有 Evidence 的结构化查询，不能把 Chroma/CLIP/SentenceTransformer 带入执行链。

License：固定 commit tree 无 LICENSE/COPYING，GitHub 无明确许可证。商业使用、修改和分发授权不明确；**禁止复制代码，只参考思想。**

### 4.2 RAGFS：`Venere-Labs/ragfs`

仓库：https://github.com/Venere-Labs/ragfs

源码定位：`crates/ragfs-fuse/src/ops.rs`（协议/执行）、`safety.rs`（trash/history/undo）、`semantic.rs`、`filesystem.rs`、`inode.rs`；`crates/ragfs-index/src/indexer.rs`、`watcher.rs`；`crates/ragfs-store/src/schema.rs`、`lancedb.rs`；Python binding `crates/ragfs-python/src/ops.rs`。测试主要是操作、安全和 pipeline 的 Rust inline unit/integration tests。

`.ops` 接受 JSON。Operation 支持 create/delete/move/copy/write/mkdir/symlink；结果有 id、success、op、path、error、timestamp、indexed、undo_id。Batch 支持 dry-run/atomic/rollback 状态。结构化成功/失败值得借鉴。

但 `resolve_path` 对绝对路径直接返回，只有相对路径才拼 source root，所以并未证明绝对路径受 scope 限制。删除先 soft delete，失败会退化成硬删除，不可接受。Trash 保存到 `data_dir/trash/<index_hash>/<uuid>/content`，metadata 有 original/trash path、deleted/expires time、BLAKE3、size；History JSONL 有 UUID、operation、timestamp、success、reversible、undo_data、error。

Undo 按 operation ID：create/copy 反向删除，move 把 dst rename 回 src，delete 从 trash 恢复；未覆盖 source fingerprint、后续计划依赖、目标冲突审批。Guixu 当前 journal/undo 更完整。

可迁移：OperationResult、undo handle、operation/safety/semantic 分层、batch rollback 表达。不可迁移：FUSE、Rust/LanceDB/Candle、自动下载约 500MB 模型、watch、任意绝对路径、agentic delete、hard-delete fallback。不要重写 Guixu 执行器。

License：实际存在 `LICENSE-MIT` 和 `LICENSE-APACHE`，MIT OR Apache-2.0；允许商业使用、不要求衍生作品开源，但须保留许可/版权声明，Apache 另有 NOTICE/专利条款。法律上可局部复用；本阶段仅参考设计。

### 4.3 AgentFS：`tursodatabase/agentfs`

仓库：https://github.com/tursodatabase/agentfs

源码定位：`SPEC.md`；`sdk/python/agentfs_sdk/toolcalls.py`、`kvstore.py`、`filesystem.py`、`agentfs.py`；测试 `sdk/python/tests/test_toolcalls.py`、`test_kvstore.py`、`test_filesystem.py`；框架示例在 `examples/openai-agents/` 等。

SQLite `tool_calls` 保存 id/name/parameters/result/error/status（pending/success/error）/started/completed/duration，并按 name/time 索引。SDK 支持 start/success/error/record/get/recent/stats；测试覆盖跨实例持久化。可借鉴“执行前先落 pending，完成后推进状态；启动后 reconcile 未完成项”。

KV 是 namespaced JSON，只适合辅助状态，不能作为 current plan 等关键状态的唯一真相。“Snapshot”主要是复制 SQLite DB 后重开，不是完整 Conversation snapshot API，更不能恢复真实用户磁盘；SPEC 仍把 session/conversation grouping 列为未来方向。

Guixu 不需要 AgentFS runtime、虚拟 FS、FUSE/NFS 或通用 KV；现有 SQLite 足够。借鉴 tool-call ledger、timeline、checkpoint；真实文件恢复仍交给 OperationJournal。

License：固定 commit 根 tree 没有 README 所链接的 `LICENSE.md`，仅见第三方 `licenses/`；README/manifest 声称 MIT。MIT 通常允许商业使用且无 copyleft，但实际文件缺失，**澄清前不复制代码，只参考 schema 思想。**

### 4.4 BorisBesky Desktop

仓库：https://github.com/BorisBesky/file-organizer-desktop

源码定位：`src/App.tsx`（主 UI/state）、`src/api.ts`（provider）、`src/components/LLMConfigPanel.tsx`、`ManagedLLMDialog.tsx`、`src/types/index.ts`、`src-tauri/src/main.rs`（磁盘命令），测试在 `tests/`。

主页面是左栏 provider/目录选择 + 主区 proposal table；有 idle/scanning/stopped/completed/organizing、进度条、事件、stop/resume/new scan、partial review。Provider 覆盖 managed-local、LM Studio、Ollama、OpenAI、Anthropic、Groq、Gemini、custom；值得借鉴连接/进度/错误可见，而非 provider 数量。

不安全点：配置、API key、processed state 写 localStorage；managed model 自动下载/启动；Tauri move 接受任意字符串路径并直接创建父目录、`fs::rename`；无 plan/journal/fingerprint；还有 extension-based category fallback。

可借鉴：阶段状态、partial review、可编辑 proposal、provider availability。不可迁移：左栏长期塞设置、中心大表格、localStorage secret、自动模型下载、直接 path move。Guixu 应把 proposal/progress 变成聊天业务卡片，细节放右侧 Workspace。

License：根目录 `LICENSE` 为 MIT；允许商业使用、不要求衍生开源，需保留 notice。因 React/Tauri 与安全模型不匹配，**只参考 UX。**

### 4.5 run-llama/file-organizer

仓库：https://github.com/run-llama/file-organizer

源码核心只有 `organize.py`，另有 `pyproject.toml`、lock 与 LICENSE，无测试。四阶段为 `--describe`、`--categorize`、`--recategorize`、`--move`。Describe 用 GPT-4o/多模态 GPT-4o；categorize 只读 description；recategorize 对少于 3 个文件的类趋向合并、超过总量 20% 的类趋向拆分，最多 5 轮；move 直接创建 `<category> (Auto)` 后 `os.rename`。

Description 以 `os.stat(...).st_ino` 为 key 存 `db/<inode>.json`。同卷 rename 通常不改 inode，所以移动后命中；但没有 size/mtime/hash/parser/model/prompt version，原地修改后会错误复用，跨卷/复制/inode 重用/Windows 差异也会破坏假设。`categorized_paths.json` 仍保存脆弱路径，代码注明只假定一个 folder。

Describe/categorize 分开可让昂贵内容理解跨 taxonomy 复用，值得迁移。不可迁移：inode-only、单 description blob、全局 JSON、类别名即目录、直接 rename/清空目录、无审批/journal/undo。

License：根目录 `LICENSE` 为 MIT；允许商业使用、不要求衍生开源，须保留 notice。代码安全/状态模型过弱，**只参考设计。**

## 5. License 与复用决策

| 项目 | 实际 LICENSE 文件 | 声明 | 商业使用 | 衍生开源 | 建议 |
|---|---|---|---|---|---|
| Drift | 无 | 不明确 | 未获明确授权 | 不适用 | 禁止复制；仅思想 |
| RAGFS | `LICENSE-MIT`、`LICENSE-APACHE` | MIT OR Apache-2.0 | 允许 | 不要求，需 notices | 可局部复用但本阶段仅思想 |
| AgentFS | 根目录缺失，README/manifest 称 MIT | 证据不完整 | MIT 声明下通常允许 | 通常不要求 | 澄清前不复制 |
| Boris Desktop | `LICENSE` | MIT | 允许 | 不要求，保留 notice | 仅 UX |
| run-llama | `LICENSE` | MIT | 允许 | 不要求，保留 notice | 仅思想 |

本阶段没有复制任何源码。许可证结论用于工程筛选，不替代法律审查。

## 6. Guixu 能力映射：避免重复建设

`ADD` 新增；`REUSE` 原样复用；`PARTIAL` 在既有能力上扩展；`RETIRE` 从新主流程退出但暂不物理删除。

| 能力 | 参考 | 当前情况 | 决策 | 落点 |
|---|---|---|---|---|
| Chat Agent loop | Drift | 缺失 | ADD | 薄 `AgentOrchestrator` |
| Conversation/Message | AgentFS 思想 | 缺失 | ADD | SQLite 类型化 schema |
| Tool-call ledger | AgentFS | events/model calls 部分已有 | PARTIAL | ToolCall/ToolResult 关联消息/轮次 |
| Scanner | 综合 | 已有且受 scope 控制 | REUSE | 不另建 scanner |
| Parser/FileProfile/Evidence | run-llama/RAGFS | 已有 | PARTIAL | 扩展 cache/provenance |
| Taxonomy planner | Drift/run-llama | 已有 | REUSE | facade 调现有 Planner |
| AI classifier | run-llama | 已有 | REUSE | 禁止规则 fallback |
| Preview/Plan | Drift | PlanCompiler/revision/hash 已有 | REUSE | 新 UI 卡片，核心不改 |
| FileOperationEngine | RAGFS | Guixu 更完整 | REUSE | Agent 仅请求执行批准 plan |
| Undo | RAGFS/Drift | journal + UndoCompiler 已有 | REUSE | 新对话入口，不另造逆操作 |
| Semantic evidence cache | run-llama/RAGFS | 部分已有 | PARTIAL | 多维 cache key |
| Semantic search | Drift/RAGFS | 缺失 | LATER | 先结构化查询，向量后置 |
| Stable file reference | 外部普遍不足 | 部分已有 | PARTIAL | FileReference/selection context |
| Plan versions | 外部不足 | revision 部分已有 | PARTIAL | immutable parent chain |
| Provider UI | Boris | ModelsPage/probe 已有 | PARTIAL | 与 Chat 状态联动 |
| 三栏 Chat UI | 综合 | 缺失 | ADD | Conversation/Chat/File Workspace |
| 模板驱动新流程 | 无 | 新方向不需 | RETIRE | 先切断引用再另阶段删除 |
| RuleEngine fallback | 外部有反例 | 运行时已删除 | RETIRE/禁止 | 不以 tool 形式复活 |

## 7. Guixu Agent Loop 草案

```text
User Message
  ↓ persist Message(user)
Load typed ConversationContext + active PlanVersion + selection/reference context
  ↓
AgentOrchestrator
  ├─ resolve intent and references (never trust model paths)
  ├─ decide answer-only or allowed ToolCall
  └─ persist ToolCall(pending) before execution
        ↓
Tool Registry / application facade
  ├─ validate conversation revision, scope, authorization, stable IDs
  ├─ invoke current Guixu core
  └─ persist ToolResult(success/error) + domain events
        ↓
Update typed context and/or create immutable PlanVersion
  ↓
Model produces user-facing response from bounded state + tool result
  ↓ persist Message(assistant)
Wait for next message OR show plan approval card
  ↓ explicit user confirmation only
Execution Request Tool → revalidate plan/hash/fingerprints → current executor
```

每轮只允许有界次数 tool calls；任何 write intent 到 plan preview 即停止自动循环。`request_plan_execution` 不能由模型文本自行授权。模型输出中的路径只作为非权威文本，解析成 FileReference 后才能进入工具。

| 用户消息 | 工具/状态变化 | 重分析范围 | 最终确认 |
|---|---|---|---|
| “帮我整理这些照片。” | resolve selection → inspect/analyze missing evidence → propose | 仅所选照片，补缺失 evidence | 分析不需；执行需要 |
| “人物照片单独放。” | `revise_proposal` 新增/调整人物类 | 当前 scope 人像候选；缺证据才 Vision | 执行需要 |
| “建筑里面的夜景放到风景。” | 建筑类子集 → 调整 mapping/structure | Category Change，仅相关文件 | 执行需要 |
| “这些都属于毕业旅行。” | selection 绑定 category intent | Local Change；通常不重做理解 | 执行需要 |
| “刚才那个方案还是好一点。” | 消歧最近 PlanVersion，旧版设候选 | 不重做内容；按当前磁盘重 preview | 激活不需；执行需要 |
| “撤销刚才的整理。” | 最近可撤销 ExecutionRound → undo preview | 不跑 AI；检查后续变化/冲突 | 需要 |

## 8. 第一版 Tool Registry

统一失败结构：`{ok:false, code, message, retryable, details, stale_revision?, ambiguous_refs?}`；输出不得泄露 API key、未授权全文或不必要绝对路径给云模型。

| Tool | Purpose | Input（ID only） | Output | R/W | 授权 | 改磁盘 | 最终确认 | 失败 |
|---|---|---|---|---|---|---|---|---|
| `scan_scope` | 扫描/刷新授权目录 | conversation_id, scope_id, expected_revision | scan_id, counts, file_ids, warnings | W DB/R disk | scope 授权 | 否 | 否 | SCOPE_UNAUTHORIZED / SCAN_FAILED |
| `inspect_files` | 读取 profile/evidence 摘要 | file_ids, fields | refs, profile/evidence availability | R | scope 内 | 否 | 否 | FILE_NOT_FOUND / REF_STALE |
| `analyze_files` | 补 parser/Vision/OCR evidence | file_ids, evidence types, model_profile_id, privacy_grant_id | evidence_ids, cache hits, blocked/errors | W DB/R disk/可能云 | 内容出站授权 | 否 | 否 | CAPABILITY_UNAVAILABLE / PRIVACY_BLOCKED |
| `find_files` | 结构化/语义证据查找 | scope/category/selection refs, query, limit | ranked FileReferences + reason | R | scope 内 | 否 | 否 | QUERY_UNSUPPORTED / AMBIGUOUS |
| `get_workspace_state` | 当前结构/selection/plan/execution | conversation_id, include | typed snapshot + revision | R | 否 | 否 | 否 | STATE_NOT_FOUND |
| `propose_structure` | 首次 taxonomy proposal | scope_id, file_ids, constraints, model_profile_id | taxonomy version, evidence gaps | W DB | 模型/隐私规则 | 否 | 否 | INSUFFICIENT_EVIDENCE / MODEL_UNAVAILABLE |
| `revise_proposal` | 多轮修改结构/映射 | active_version_id, resolved change set, expected_revision | child PlanVersion, impact | W DB | 新分析时授权 | 否 | 否 | STALE_VERSION / AMBIGUOUS_REFERENCE |
| `preview_plan` | 确定性变更预览 | plan_version_id, expected_revision | plan_id/hash, moves/conflicts/warnings | W DB/R disk | scope 内 | 否 | 否 | SOURCE_CHANGED / CONFLICT |
| `request_plan_execution` | 提交 UI 已确认计划 | plan_id, plan_hash, approval_id | execution_round_id/status | W DB+disk | **approval** | 是 | **是** | APPROVAL_REQUIRED / STALE_PLAN |
| `get_execution_status` | 执行/恢复/错误 | execution_round_id | status, counts, events, recovery | R | 否 | 否 | 否 | EXECUTION_NOT_FOUND |
| `prepare_undo` | 生成 undo preview | execution_round_id | undo plan/conflicts/dependencies | W DB/R disk | 否 | 否 | 否 | NOT_REVERSIBLE / SUBSEQUENT_CHANGE |
| `request_undo_execution` | 执行已确认 undo | undo_plan_id/hash, approval_id | new ExecutionRound/status | W DB+disk | **approval** | 是 | **是** | APPROVAL_REQUIRED / UNDO_CONFLICT |

合并/延后：`search_files` 与 `get_selected_files` 合为 `find_files` + context；`get_current_structure` 纳入 `get_workspace_state`；`update_structure` 改为产生新版本的 `revise_proposal`；`apply_plan` 改为 request，要求独立 approval record。暂不提供通用 vector search、delete、copy、rename、mkdir、shell、PowerShell、Python、任意 path move；目录创建只能来自编译后的 plan operation。

## 9. Conversation State 草案

| 实体 | 内容 | 持久化 | 真相/可变性 |
|---|---|---|---|
| `Conversation` | title/status/timestamps/active context revision | 是 | 元数据可改，不承载磁盘真相 |
| `Message` | role/content/reply/display payload | 是 | 历史不可改，可另加 tombstone |
| `ConversationContext` | scopes、selection、active taxonomy/plan/execution/model/privacy、constraints、revision | 是 | 版本化可覆盖；当前意图投影 |
| `PlanVersion` | proposal/taxonomy/mappings、parent、trigger message、impact、hash/status | 是 | 不可变；新要求建 child |
| `ExecutionRound` | forward/undo、plan、approval、start/end/status | 是 | 历史；状态机推进 |
| `FileReference` | message/context 到 file_id 集、类型、selection snapshot、resolution | 是 | 冻结引用，失效另记 |
| `FileEvidence` | fingerprint/type/payload/provenance/cache dimensions | 是 | 追加/失效，不覆盖伪装新鲜 |
| `ToolCall` | message/round/tool/input hash/status/timing | 是 | pending → result/error；审计 |
| `ToolResult` | typed result/domain refs/error/visibility | 是 | 不可变 |
| Runtime turn | token budget/stream/candidates | 否或短 checkpoint | 可丢，不是业务真相 |

聊天历史只用于语言上下文和审计。每轮模型 context 由数据库投影生成：scope/selection、active plan、必要消息摘要、已解析 FileReference、权限和 capabilities。启动恢复读结构化状态，不把完整聊天重新发给模型猜状态。

Conversation 删除与文件删除完全分域：删除/最近删除 Conversation 只处理应用数据，不生成 FileOperation；第一版工具没有文件删除。

## 10. 稳定 File Identity 与指代解析

推荐三层身份：

1. `file_id`：数据库 UUID，所有业务关联的唯一稳定主键。
2. `content_fingerprint`：size + strong/qualified hash，记录算法/采样版本；决定内容一致与 evidence cache。
3. `filesystem_identity`：Windows volume serial + file ID（可获得时）和 observed metadata；用于同卷 rename 重绑定，不能独立作为永恒身份。

路径是属性，不是 identity。维护 `current_path` 与 append-only path observations；扫描按 filesystem identity → fingerprint → 受控启发式重绑定，多候选一律返回歧义。

`FileReference` 保存 conversation/message、ref token、resolved file_ids、来源（selection/category/result/execution）、selection revision、resolved_at、confidence/ambiguity：

- “这个文件”→ 当前 UI focused file，必须匹配 focus revision。
- “这些照片”→ 冻结当前显式 selection，不随 UI 后续选择漂移。
- “刚才那些”→ 最近相关 FileReference/ToolResult 的冻结 file_id 集。
- “建筑里的这几个”→ category version 与 selection 的交集；空或多义就询问。
- “上一次移动的文件”→ 最近完成 ExecutionRound 的 operation file_ids。

模型声称未知 file_id 时返回 `FILE_NOT_FOUND`；模型返回路径时只能作查询提示，不能进入执行参数。

## 11. Semantic Evidence Cache

```text
File(file_id, current_path, filesystem identity)
  ↓ content_fingerprint
FileProfile(parser outputs, metadata)
  ↓
FileEvidence(OCR / text summary / visual description / transcript / video evidence)
  ↓ taxonomy_version + classifier model/prompt
ClassificationEvidence / mapping
```

| 产物 | Cache key 最小维度 | 移动 | 内容修改 | 切模型 | Taxonomy 改变 |
|---|---|---|---|---|---|
| profile/metadata | fingerprint + parser/version + options | 复用，更新 path | 失效 | 无关 | 复用 |
| OCR/text extraction | fingerprint + parser/version + language/options | 复用 | 失效 | 通常复用 | 复用 |
| text summary | fingerprint + source evidence hash + model + prompt version | 复用 | 失效 | 旧版可保留，新配置新版本 | 复用 |
| visual description | fingerprint + derivative hash + model + prompt + safety policy | 复用 | 失效 | 保留 provenance，不冒充新结果 | 复用 |
| audio transcript | fingerprint + decoder/ASR/version/language | 复用 | 失效 | 同配置复用，否则新版本 | 复用 |
| video evidence | fingerprint + sampling policy + model/prompt | 复用 | 失效 | 新配置新版本 | 复用 |
| classification | evidence-set hash + taxonomy version + model/prompt + constraints | 复用 | 失效 | 默认重分类或保留待确认 | **局部失效** |
| compiled plan | plan version + paths/fingerprints + compiler version | **重编译/复核** | 失效 | 无关 | 失效 |

缓存命中也记录 provenance，不能只有可覆盖 blob。移动只改变 location projection；内容变更让派生 evidence stale。模型切换不删除旧 evidence，但新结果必须有新 provenance。Taxonomy 变化只重跑分类/plan，不重跑新鲜的 OCR/Vision。第一版先做精确 key + SQLite，不上向量数据库/watcher。

## 12. Incremental Replanning

四级影响模型合理，但必须由确定性 impact analyzer 根据 resolved refs 与变更类型判定，不能让模型单独声明范围。

| 等级 | 例子 | 受影响集合 | AI 重算 | 不重算 |
|---|---|---|---|---|
| Local Change | “这 5 个都属于毕业旅行” | 明确 file_ids | mapping/classification validation | OCR/Vision/其他文件 |
| Category Change | “建筑里的夜景放到风景” | 指定 category version 的成员/目标类 | 相关集合重分类和冲突检查 | 无关类别理解 |
| Structure Change | “人物单独一类，合并截图和素材” | 被拆/并节点成员 | taxonomy 局部更新 + 相关分类/plan | 未涉及分支 evidence |
| Global Strategy Change | “以后全部按活动分类” | 整个授权 scope | taxonomy + 全 scope 分类 + plan | 新鲜内容 evidence |

流程：解析引用 → 计算 affected file_ids/category nodes → 检查 evidence gaps → 只补缺失分析 → 创建 child PlanVersion → 增量分类 → 全局确定性约束检查 → preview。即使局部变化，PlanCompiler 仍对最终完整 plan 做冲突、路径和质量校验。

恢复旧方案不是直接执行旧 path operations：把旧 PlanVersion 设为候选，基于当前 file identity/path/fingerprint 重新编译；文件已变则必须处理冲突。

## 13. Agent 安全边界

| 风险 | 边界/缓解 |
|---|---|
| 文件内 Prompt Injection | 文件内容标记 untrusted evidence；不从内容生成权限/tool/system instruction；输入分隔且最小化 |
| Tool abuse / excessive agency | allowlist、每轮预算、写意图止于 preview、独立 UI approval、无通用代码执行 |
| Path traversal | tool 禁止路径；本地 ID 解析后 canonicalize + enforce scope/root |
| 指代歧义 | FileReference 冻结 revision；多义返回 structured ambiguity 并询问 |
| Stale plan | revision/hash/context revision/source fingerprint/approval binding；执行前重验 |
| 外部文件修改 | 执行前 stat/fingerprint；变化即 SOURCE_CHANGED |
| 意外批量移动 | 数量/比例/跨目录风险阈值、摘要+展开、mass-move 强提醒、禁止默认批准 |
| Agent 幻觉文件 | file_id FK + scope membership；未知 ID 拒绝；path 文本不落执行器 |
| Wrong file_id | UI 同步缩略图/路径/证据；reference provenance；低置信度消歧 |
| 后续变化后的 Undo | 从 ExecutionRound/journal 生成新 undo plan；检查后续操作、占用和 fingerprint |
| Conversation 删除 vs 文件删除 | API/权限/UI/表完全分离；删会话永不触发磁盘 tool |
| 云端隐私 | 复用 privacy grant/capability gate/derivative；ToolResult 按字段脱敏 |
| Tool/result 重放 | idempotency key、expected revision、pending reconcile、approval 绑定 |
| 假成功 | unavailable/blocked/error 写入 ToolResult；Mock 仅测试/显式演示 |

## 14. Conversation Agent 桌面 UI 建议

### 左：Conversation Sidebar

- 分组：进行中、待确认、已完成、最近删除；展示标题、scope 摘要、最后状态/时间。
- 新建 Conversation 不等于立即扫描；恢复时定位 active PlanVersion/ExecutionRound。
- 模型设置不常驻，只显示 provider availability 小状态，点击进入 ModelsPage。

### 中：Chat Workspace

普通消息只承载用户意图、AI 解释、消歧问题。以下应做业务卡片：scope 授权、扫描/分析进度、evidence gap、taxonomy proposal、影响范围、plan preview、approval、execution/error、undo preview。

Tool Call 默认展示人类摘要（如“分析 12 张照片，9 个缓存命中”），诊断展开区才显示 tool name、耗时、error code、trace ID；不展示思维链或敏感参数。进度区分 queued/scanning/parsing/cache-hit/model-analyzing/blocked/completed；partial result 不伪装成完整计划。

计划确认最自然的位置是 Chat 中的 sticky approval card，右侧同步完整变更；确认按钮绑定 plan hash/revision，不能用一条自然语言“好的”自动替代授权。

### 右：File Workspace

Tabs：`当前文件` / `整理预览` / `变更记录`。

- 点击 Chat 的文件 chip/card，用稳定 file_id 定位预览、current path 与 evidence provenance。
- 点击 category/plan card，切到整理预览，筛选 affected scope、冲突、未分析项。
- 点击 execution/undo card，切到变更记录，展示 operation events 与恢复状态。

避免手机式聊天：桌面需要并排比较、多选、键盘操作、可见层级与 sticky preview，不应把每个文件做成气泡或把确认藏在滚动历史。避免管理后台：减少常驻统计/大表单，围绕当前意图呈现一张主卡，详情按需在右侧展开。

## 15. Target Architecture（文字图）

```text
[ADD] Conversation UI
  ├─ Left: Conversation Sidebar
  ├─ Center: Chat Workspace + business cards
  └─ Right: File Workspace / Plan Preview / Change History
        ↓
[ADD] AgentOrchestrator
        ↓
[ADD] Typed ConversationContext + Reference Resolver + Impact Analyzer
        ↓
[ADD] Tool Registry (application facades only)
  ├─ File Query Tools
  ├─ Analysis Tools
  ├─ Planning / Revision Tools
  ├─ Preview Tools
  └─ Execution Request / Undo Request Tools
        ↓
[REUSE/PARTIAL] Current Guixu Core
  ├─ Scanner                           [REUSE]
  ├─ Parser                            [REUSE]
  ├─ FileProfile / Evidence Cache      [PARTIAL]
  ├─ AITaxonomyPlanner                 [REUSE]
  ├─ AIFileClassifier                  [REUSE]
  ├─ ModelAdapter / capability gate    [REUSE]
  ├─ PlanCompiler                      [REUSE]
  ├─ FileOperationEngine               [REUSE]
  └─ OperationJournal / History / Undo [REUSE]

[RETIRE FROM NEW FLOW]
  ├─ template-dependent task creation
  └─ legacy one-shot wizard as primary navigation

[FORBIDDEN]
  ├─ RuleEngine semantic fallback
  ├─ arbitrary path/shell/code/delete tools
  └─ model-direct disk operations
```

## 16. 建议的后续阶段顺序

对初步顺序作小幅调整：稳定 reference 基础提前到 orchestrator 之前，semantic cache contract 提前到首次真实 Agent 分析之前；否则早期 schema/tool payload 会依赖路径并返工。

1. **Task/Conversation 删除语义治理**：应用数据删除、最近删除与磁盘删除完全分离。
2. **切断新流程 Templates 依赖**：退出新主流程，保留兼容读取/迁移路径。
3. **Conversation schema + ToolCall ledger**：Conversation、Message、Context revision、PlanVersion、ExecutionRound。
4. **Stable FileReference foundation**：file_id、path observations、selection snapshot、execution references。
5. **Conversation UI skeleton**：三栏、路由、空状态、恢复入口；不接执行。
6. **AgentOrchestrator + read-only tools**：bounded loop、typed result、context projection、错误状态。
7. **Semantic Evidence Cache contract**：fingerprint/parser/model/prompt provenance；不上向量库。
8. **First-turn organization**：scope → scan → analyze gaps → proposal，复用当前 Planner/Classifier。
9. **PlanVersion + preview/approval bridge**：不可变版本、parent、hash 与现有 PlanCompiler/approval 对接。
10. **Execution + post-execution conversation**：ExecutionRound、进度卡、失败/恢复，不改 engine。
11. **Incremental Replanning**：四级影响、局部重分类、旧方案重新编译。
12. **Conversational Undo**：prepare → preview → explicit approval → 新 ExecutionRound。
13. **Session Recovery**：pending tool reconciliation、断点恢复、stale context。
14. **Semantic Search（可选门）**：先评估 SQLite FTS/现有 evidence，确有需求再引 embeddings。
15. **UI polish/accessibility/performance**。
16. **Qwen Integration completion**：继续统一 ModelAdapter，可与 polish 部分并行。

理由：schema 先于 UI/loop，identity 先于 tool contract，cache 先于昂贵分析，preview/approval 先于执行，增量计划先于对话式 undo，所有写能力都建立在已验证只读 loop 之后。

## 17. 明确不采用

- 不引入 LangChain 等大型 Agent framework。
- 不引入 FUSE、AgentFS runtime、Chroma/LanceDB 作为第一版依赖。
- 不自动下载 embedding/vision/local LLM 大模型。
- 不开放 delete、shell、PowerShell、Python、任意 path move/copy/rename。
- 不把聊天记录当状态数据库，不把模型“确认”当授权记录。
- 不用外部项目的简单 rename/undo 替换 Guixu 安全执行链。
- 不因 MIT/Apache 就直接复制；未来取用仍需来源、版本、notice 与安全评审。

## 18. 完成核对

- [x] 研究完 5 个重点项目
- [x] 不只阅读 README
- [x] 找到关键源码实现位置
- [x] 核对每个项目实际 License 文件状态
- [x] 明确代码复用与仅设计参考边界
- [x] 完成项目对比矩阵
- [x] 完成 Guixu 能力映射表
- [x] 完成 Agent Loop 草案
- [x] 完成 Tool Registry 草案
- [x] 完成 Conversation State 草案
- [x] 完成稳定 File Identity 建议
- [x] 完成 Semantic Cache 建议
- [x] 完成 Incremental Replanning 建议
- [x] 完成 Agent 安全边界
- [x] 完成 Conversation UI 建议
- [x] 完成 Guixu Target Architecture
- [x] 给出后续开发顺序
- [x] `docs/GITHUB_REFERENCE_ANALYSIS.md` 已生成

## 19. 最终建议

Conversation Agent 应是 Guixu 核心之上的“受限编排与状态层”，不是新的文件操作系统。Drift 提供交互节奏，AgentFS 提供审计思路，RAGFS 提供结构化结果和 safety 分层，Boris Desktop 提供桌面进度/review 表达，run-llama 证明内容理解与分类应分层缓存；负责安全执行、隐私、模型能力和 undo 的仍是 Guixu 当前核心。
