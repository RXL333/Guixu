# Semantic Cache Audit

日期：2026-09-21

## 现状

- `files` 已保存 task 内稳定 `id`、当前路径、size/mtime，并在执行/工作区同步时使用 `sha256`；路径不是执行安全身份，但扫描初始阶段不会预先计算 hash。
- `file_profiles` 已持久化 `ParseOutcome.profile_json`，其 `cache_key` 由内容 SHA-256、`PARSER_VERSION` 和解析选项组成。`ParserRunner` 另有内容寻址的本地 JSON worker cache。此前这两层没有统一命中/失效/统计接口。
- `FileProfile.evidence` 是嵌入式 evidence 列表，支持 `metadata`、`extracted_text`、`ocr`、`visual_description`、`transcript` 等 kind；没有独立的 evidence provenance 表，模型 evidence 只在 `origin=AI:<profile>` 与 profile cache key 中间接记录。
- `TaskRepository.append_model_evidence()` 会生成新的 profile snapshot，但不按 fingerprint、schema、prompt 或 producer 查询，也没有明确 invalidation 状态。
- `PostExecutionConversationService` 的 `EvidenceReuseService` 只检查 profile JSON 中是否存在非空语义 kind；它能阻止明显缺失，但无法区分 fingerprint、parser/prompt version、provider 或失败状态。
- 当前没有 OCR/ASR/视频专用数据库缓存，也没有第二个向量/RAG 缓存。ParserRunner 的文件缓存和 file_profiles 将被适配为统一服务的 deterministic evidence 来源，而不是继续添加一套独立查找逻辑。

## Phase J 采取的最小调整

新增 `file_evidence` 作为 canonical evidence ledger，保留 `file_profiles` 作为可恢复的完整 parser snapshot。新服务按 `file_id + content_fingerprint + evidence_kind + schema_version` 查找，producer/model/prompt 作为 provenance；失效记录保留元数据，payload 可手动清理。

图片视觉证据写入同一 ledger；文本/PDF/Office/OCR/媒体 metadata 由 parser snapshot 同步写入。分类 decision cache 暂不实现，因此 taxonomy 或 requirements 变化只重新分类，不重新解析或重新 Vision。

## 已知基线限制

- 当前 `files.id` 的稳定范围仍是单 Task；跨 Task canonical identity 留待后续阶段。
- 初始 scan 不计算 SHA-256，第一次 parse 会计算并建立 fingerprint；这避免扫描阶段增加额外 I/O。
- 没有可用的真实 DeepSeek 凭据时不伪造 smoke 结果；真实调用仅在用户已配置且授权的环境中运行。
