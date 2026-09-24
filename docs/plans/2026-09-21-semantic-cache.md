# Semantic Cache implementation plan

## Scope

Create one durable, local evidence cache above the existing `files` and `file_profiles` records. Reuse stable file IDs and SHA-256 content fingerprints; do not add a vector store, new classifier, or new provider integration.

## Decisions

- `files.id` remains the tracked identity and `sha256`/validated current file hash is the content key.
- A new `file_evidence` table is the canonical reusable evidence ledger. `file_profiles.profile_json` remains a parser snapshot and compatibility source, not a second lookup API.
- Evidence rows are append-oriented: a changed fingerprint invalidates old rows, while a new fingerprint creates new rows. Provenance is explicit and secrets never enter payloads.
- Existing `ParsingService` and `AIFileClassifier` are adapted through `EvidenceCacheService`; their public contracts remain compatible.
- Classification decisions remain uncached in this phase. Taxonomy/requirements changes therefore reuse evidence but rerun classification.
- Cache operations are local and scope checked by the caller; no disk deletion is performed by cache maintenance.

## Implementation order

1. Add the audit and schema/migration for `file_evidence` and cache metrics.
2. Implement `EvidenceCacheService` with lookup/store/invalidation/force-refresh/cleanup/statistics and a per-key single-flight lock.
3. Backfill parser snapshots into canonical evidence and reuse them in `ParsingService`.
4. Reuse cached visual descriptions in batch classification and store new model evidence with provenance.
5. Replace post-execution evidence heuristics with the service where the current fingerprint is available.
6. Add cache statistics/cleanup API endpoints and a small settings-facing response; do not add a cache manager page.
7. Add focused tests, migration checks, restart/move/change/concurrency coverage, and update documentation/status.

## Acceptance

- Move/rename with the same SHA-256 is a cache hit; content changes invalidate old rows.
- Parser/model/prompt/schema provenance is queryable; cache hit/miss/refresh events are observable.
- Force refresh creates a new row without deleting the prior provenance.
- Failed generation is retryable and never marked valid.
- Clearing cache affects only evidence rows, not files, conversations, plans, executions, journals, or undo data.
- Existing AI-only and conversation/file-reference flows retain their current contracts.
