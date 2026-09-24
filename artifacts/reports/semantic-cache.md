# PHASE J Semantic Cache 阶段报告

日期：2026-09-21

## 最终架构

新增 `file_evidence` 作为本地 canonical evidence ledger；`file_profiles` 继续保存完整 parser snapshot 并在解析后投影到 ledger。`EvidenceCacheService` 统一负责 lookup、store、invalid/invalidation、force refresh、cleanup、clear、statistics 和进程内 single-flight。

最终 cache key 为 `file_id + content_fingerprint + evidence_kind + evidence_schema_version`。producer、model、prompt、parser version 都是 provenance，不把 provider 切换自动变成 cache miss。

## FileProfile / FileEvidence 变更

- parser 每次获得 SHA-256 后回写 `files.sha256`，并把 `FileProfile.evidence` 投影为 `METADATA/TEXT_EXTRACT/OCR_TEXT/...`。
- `append_model_evidence` 保留旧 profile snapshot，同时写入 `VISUAL_DESCRIPTION` 的 model/prompt provenance。
- AI Planner/Classifier 在有有效视觉证据时将它作为文本证据使用，避免无意义的 derivative/image upload；缺失时仍走既有 capability/privacy gate。
- Post-execution refinement 使用 unified cache 判断 REUSE/REFRESH_REQUIRED；不改 FileOperationEngine、PlanCompiler、OperationJournal 或 Undo。

## Invalidation / refresh

文件移动和重命名只改变路径，fingerprint 不变，缓存命中。内容改变会将旧 fingerprint 记录标为 `INVALID / CONTENT_CHANGED`，新结果追加到新 fingerprint。`force_refresh=true` 只作用于明确 file IDs，标为 `STALE / FORCE_REFRESH` 后重新生成；失败不写 VALID。

## Evidence kinds / provenance

支持 `METADATA`、`TEXT_EXTRACT`、`OCR_TEXT`、`VISUAL_DESCRIPTION`、`DOCUMENT_SUMMARY`、`AUDIO_TRANSCRIPT`、`AUDIO_SUMMARY`、`VIDEO_FRAME_DESCRIPTION`、`VIDEO_TRANSCRIPT`、`VIDEO_SUMMARY`、`COMBINED_CONTENT_SUMMARY`、`USER_CONTEXT`。每行记录 producer type/name/version、model profile/id、prompt version、schema version、quality、state 和失效原因。

## Decision cache 与大 payload

L3 classification decision cache deferred；taxonomy/requirements 变化只重跑分类。当前 payload 仍使用 SQLite JSON/text 字段，复用已有 profile artifact cache；没有新对象存储或向量数据库。后续若 transcript/视频 payload 过大，可在不改 key 的情况下把 payload 迁移到已有本地 artifact store。

## API / settings

新增 `GET /api/v1/cache/status`、`POST /api/v1/cache/cleanup`、`POST /api/v1/cache/clear`。现有 reanalyze API 增加 `force_refresh`。本阶段没有新增复杂 Cache Manager 页面；UI 可直接用 status/clear 接入设置页。

## Migration

`0008_semantic_cache`，应用 schema version 8。升级前沿用现有 SQLite backup；迁移只创建表和索引，不删除旧 profile、Task、Conversation、Plan、Execution、Journal 或 Undo。

## 测试结果

本阶段新增 `backend/tests/integration/test_semantic_cache.py`，覆盖：初次 miss/二次 hit、move/rename、内容变更失效、parser/model/prompt provenance、force refresh、失败可重试、重启、clear 保持真实文件不变、single-flight、500 文件只刷新缺失子集。已运行定向缓存/分类/规划测试：12 passed；后端全量回归：165 passed / 2 warnings。

数据库契约已同步 schema v8 / Alembic head 0008；前端 4 files / 31 tests、typecheck 和 production build 均通过；`git diff --check` 通过（仅有 CRLF 转换提示）。

## 真实 DeepSeek smoke

当前工作树没有在本报告中写入或暴露任何 API key、base64 或私人文件内容。若运行环境有用户明确授权的 DeepSeek 配置，可按项目既有真实模型 smoke 流程补充 `artifacts/reports/real-semantic-cache-smoke.md`；没有配置时保持外部阻塞，不伪造“vision calls saved”数字。

## 500 文件性能

服务按 file/fingerprint/kind 建立索引，并支持批量范围先筛选后分析；本阶段未把未运行的性能数字写成通过。下一步可使用授权临时目录和 500 个 FileProfile fixture 记录 lookup time、刷新数量、DB size。

## 当前限制与下一阶段

- stable file ID 仍是 Task 内范围，跨 Task canonical identity 未实现。
- sufficiency 是保守的非空语义 evidence 判断，尚未按每个用户要求做语义评估。
- single-flight 是单进程锁，多进程 worker 协调留待后续。
- L3 decision cache、vector search、watch folder、Qwen 正式接入和长期 memory 均 deferred。

下一阶段可以在现有 `EvidenceCacheService` 上接入更细的 evidence sufficiency 与可审计 decision signature，但不应复制另一套 File/Evidence 表。
