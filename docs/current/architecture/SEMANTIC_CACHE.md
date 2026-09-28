# Semantic Cache / 文件内容分析缓存

版本：PHASE J，2026-09-21

## 1. 目标与边界

Guixu 的语义缓存复用已经完成的文件证据，降低重复解析、OCR、视觉描述和媒体转写的成本。它不是分类规则、向量数据库、RAG、长期记忆或后台索引器；分类决定仍由当前 AI Planner/Classifier 完成。

## 2. Stable File ID 与 fingerprint

`files.id` 是当前数据库跟踪的稳定引用；`content_fingerprint` 是文件内容 SHA-256。路径、文件名、mtime 只用于展示、校验或定位，不能作为缓存 identity。当前 stable ID 的兼容范围仍为单 Task；跨 Task canonical identity 留给后续阶段。

文件第一次解析时计算 SHA-256 并回写 `files.sha256`。同一文件移动或重命名，只要 fingerprint 不变，`file_evidence` 继续命中。

## 3. 缓存层

- L0：Agent/turn 的临时工作集合，仍由当前 Conversation 服务管理。
- L1：`ParserRunner` 的内容寻址 worker cache 与 `file_profiles` parser snapshot；解析完成后投影到 `file_evidence`。
- L2：`file_evidence` 中的 OCR、视觉描述、文档摘要、转写等高成本证据。
- L3：本阶段不实现分类 decision cache；taxonomy 或 requirements 改变时只重新分类，不重做仍有效的 evidence。

## 4. FileEvidence 表

`file_evidence` 是唯一统一的可复用证据 ledger。关键字段包括：`file_id`、`content_fingerprint`、`evidence_kind`、`evidence_schema_version`、`payload_json`、`normalized_content`、`state`、producer/model/prompt provenance、quality、created/last-used/invalidated 时间。`file_profiles.profile_json` 仍作为完整 parser 快照和旧数据兼容来源，不再成为新的独立 cache API。

## 5. Evidence kinds

`METADATA`、`TEXT_EXTRACT`、`OCR_TEXT`、`VISUAL_DESCRIPTION`、`DOCUMENT_SUMMARY`、`AUDIO_TRANSCRIPT`、`AUDIO_SUMMARY`、`VIDEO_FRAME_DESCRIPTION`、`VIDEO_TRANSCRIPT`、`VIDEO_SUMMARY`、`COMBINED_CONTENT_SUMMARY`、`USER_CONTEXT`。旧 profile kind（如 `extracted_text`、`ocr`、`transcript`）在写入 ledger 时做确定性映射。

## 6. Cache key 与 provenance

有效查找主键是：

```text
file_id + content_fingerprint + evidence_kind + evidence_schema_version
```

producer 不改变文件身份，但被记录用于审计：`producer_type`（LOCAL_PARSER/LOCAL_OCR/LOCAL_MEDIA/CLOUD_MODEL/LOCAL_MODEL/USER/LEGACY）、`producer_name`、`producer_version`、`model_profile_id`、`model_id`、`prompt_version`。缓存不保存 API key、Authorization header、签名 URL 或原始模型请求。

## 7. Validity 与失效

状态为 `VALID`、`STALE`、`INVALID`、`REFRESHING`、`ERROR`。fingerprint 改变时旧 fingerprint 的证据被标记 `INVALID / CONTENT_CHANGED`，历史 provenance 保留；解析器或 prompt 版本改变时，可以并存新行，旧行不会覆盖。失败结果不会写成 `VALID`。

## 8. Move、rename、content change

移动或重命名只更新 `files.current_path`/ConversationFile 投影，不改变 `file_id` 或 fingerprint，因此命中缓存。内容被替换时重新计算 fingerprint，旧证据失效，新的 parser/model 结果以新 fingerprint 写入；磁盘文件从不由 cache service 删除。

## 9. Evidence sufficiency 与 targeted refresh

Post-execution refinement 先使用当前 fingerprint 查询有效 evidence。候选集合中已有有效 evidence 的文件可复用；缺失或不可用文件才进入 ParsingService/模型刷新。当前 V1 的 sufficiency 仍是“存在非空语义 evidence”的保守策略，后续可以增加按任务要求的细粒度评估。

## 10. Force refresh

`POST /api/v1/tasks/{task_id}/reanalyze` 支持 `force_refresh=true`，仅将传入 file IDs 的当前证据标为 `STALE / FORCE_REFRESH`，随后按正常解析流程生成新记录；旧 provenance 不被覆盖。新建 `/api/v1/cache/status`、`/cleanup`、`/clear` 只管理本地 evidence rows。

## 11. 模态策略

文本、PDF、Office、OCR、metadata 和媒体解析通过 `ParsingService` 复用 parser snapshot 并同步 ledger。图片已有有效 `VISUAL_DESCRIPTION` 时，分类/规划以本地文本 evidence 继续工作，不因当前模型没有 vision 能力而强制上传原图；证据不足时才要求当前模型具备 vision。音频/视频子证据按 kind 独立保存，允许 transcript 成功而视觉摘要仍为 missing/error。

## 12. Provider、taxonomy 与 requirements

Evidence 默认跨 Provider 复用，DeepSeek 生成的有效视觉描述可供另一个 ModelProfile 的文本推理使用；只有用户明确 force refresh 才重新生成。taxonomy 或 confirmed requirements 改变会使分类 decision 自然重新计算，但不会使 fingerprint 未变的 Parser/OCR/Vision/ASR 证据失效。

## 13. Agent / affected scope / file reference 接入

所有 cache hit/miss 由后端 `EvidenceCacheService` 确认，Agent 不凭聊天记忆猜测。AffectedScope 先查询候选文件再 refresh 缺失项；File Reference 的显式 file IDs 只限定 refresh 范围，不会扩展到整个目录。Conversation scope 的授权边界仍由现有 resolver、ConversationFile 和任务 scope 校验负责。

## 14. 并发与统计

服务提供同一 `file_id + fingerprint + kind` 的进程内 single-flight lock，避免同一 worker 进程重复生成。可观察事件使用 `CACHE_HIT`、`CACHE_MISS`、`CACHE_REFRESH` 日志；`get_cache_status` 返回 cache_hit、cache_miss、cache_refresh、evidence_reused、vision/ocr/asr_calls_saved 计数与估算 payload 大小。

## 15. Privacy 与清理

payload 仅写入本地 SQLite；不会因为已有本地 evidence 就把原文件发送给新的云 Provider。`cleanup_invalid_cache` 只清理失效 payload、保留必要 provenance；`clear` 只删除 evidence rows，不删除源文件、Conversation、Plan、Execution、OperationJournal 或 Undo。

## 16. Migration 与 legacy evidence

schema v8 通过 Alembic `0008_semantic_cache` 创建 `file_evidence`，并在应用初始化时执行带 SQLite backup 的非破坏升级。已有 `file_profiles` 不会被删除或强制重新分析；解析/模型流第一次访问时将旧嵌入式 evidence 投影到 ledger，producer/version 不可知时使用现有 origin 或保守的 `LEGACY`/parser provenance。

## 17. Decision cache（deferred）

本阶段不缓存 `file + taxonomy + requirements -> category` 决策，避免 taxonomy signature、requirements canonicalization 和 classifier prompt 版本不完整时错误复用。未来实现必须把 fingerprint、evidence revision、taxonomy signature、requirements signature 和 classifier prompt version 作为严格 signature。

## 18. 测试与未来 Qwen

自动化覆盖 cache miss/hit、move/rename、content change、parser/prompt version、provider switch、force refresh、restart、clear、single-flight 和现有 AI-only 回归。真实 DeepSeek smoke 只有在用户已配置授权 key 时执行；Qwen 未来沿用相同 `file_evidence` provenance，不需要新 cache 数据库。
