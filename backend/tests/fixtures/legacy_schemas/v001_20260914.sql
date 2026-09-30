-- Guixu v1 reference schema, intended for an empty SQLite database.
-- Runtime owns Alembic migrations, WAL, synchronous=FULL, and busy_timeout.
-- No raw API keys or original binary media belong in this database.
PRAGMA foreign_keys = ON;
BEGIN;
CREATE TABLE schema_metadata (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 version INTEGER NOT NULL CHECK(version>=1),
 updated_at TEXT NOT NULL
);
INSERT INTO schema_metadata(singleton,version,updated_at) VALUES(1,1,datetime('now'));
CREATE TABLE settings (
 key TEXT PRIMARY KEY,
 value_json TEXT NOT NULL CHECK(json_valid(value_json)),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
 updated_at TEXT NOT NULL
);
CREATE TABLE model_profiles (
 id TEXT PRIMARY KEY, name TEXT NOT NULL,
 provider TEXT NOT NULL CHECK(provider IN ('deepseek','qwen_local')),
 runtime TEXT NOT NULL CHECK(runtime IN ('deepseek','openai_compatible','ollama','lmstudio','vllm','llamacpp')),
 base_url TEXT NOT NULL, model_id TEXT NOT NULL, secret_ref TEXT,
 capabilities_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(capabilities_json)),
 options_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(options_json)),
 trust_scope TEXT NOT NULL CHECK(trust_scope IN ('cloud','loopback','trusted_lan')),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE template_versions (
 id TEXT PRIMARY KEY, template_key TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version >= 1), name TEXT NOT NULL,
 origin TEXT NOT NULL CHECK(origin IN ('builtin','user')),
 definition_json TEXT NOT NULL CHECK(json_valid(definition_json)),
 definition_hash TEXT NOT NULL CHECK(length(definition_hash)=64),
 created_at TEXT NOT NULL,
 UNIQUE(template_key,version)
);
CREATE TABLE rules (
 id TEXT PRIMARY KEY, name TEXT NOT NULL,
 priority INTEGER NOT NULL DEFAULT 100 CHECK(priority >= 0),
 enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
 scope_json TEXT NOT NULL CHECK(json_valid(scope_json)),
 condition_json TEXT NOT NULL CHECK(json_valid(condition_json)),
 action_json TEXT NOT NULL CHECK(json_valid(action_json)),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE tasks (
 id TEXT PRIMARY KEY, name TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('DRAFT','RUNNING','PAUSE_REQUESTED','PAUSED','AWAITING_TAXONOMY_APPROVAL','AWAITING_EXECUTION_APPROVAL','RECOVERY_REQUIRED','COMPLETED','COMPLETED_WITH_ISSUES','CANCELLED','FAILED')),
 phase TEXT NOT NULL CHECK(phase IN ('SETUP','SCAN','EXTRACT','PLAN','CLASSIFY','PREVIEW','EXECUTE','REPORT','UNDO')),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
 settings_json TEXT NOT NULL CHECK(json_valid(settings_json)),
 settings_hash TEXT NOT NULL CHECK(length(settings_hash)=64),
 model_profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
 model_snapshot_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(model_snapshot_json)),
 rules_snapshot_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(rules_snapshot_json)),
 classification_request_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(classification_request_json)),
 template_snapshot_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(template_snapshot_json)),
 counters_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(counters_json)),
 checkpoint_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(checkpoint_json)),
 last_error_code TEXT,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE task_scopes (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('whole_tree','protected_child','root_loose','current_only')),
 source_root TEXT NOT NULL, destination_root TEXT NOT NULL,
 display_name TEXT NOT NULL, source_volume_id TEXT,
 settings_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(settings_json)),
 UNIQUE(task_id,id)
);
CREATE TABLE files (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
 scope_id TEXT NOT NULL,
 original_path TEXT NOT NULL, current_path TEXT NOT NULL,
 path_key TEXT NOT NULL, relative_path TEXT NOT NULL,
 basename TEXT NOT NULL, extension TEXT NOT NULL,
 modality TEXT NOT NULL CHECK(modality IN ('image','text','document','audio','video','other')),
 mime TEXT, size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
 mtime_ns INTEGER NOT NULL, volume_id TEXT, filesystem_file_id TEXT,
 sha256 TEXT CHECK(sha256 IS NULL OR length(sha256)=64),
 scan_status TEXT NOT NULL CHECK(scan_status IN ('discovered','eligible','excluded','missing','error')),
 exclusion_code TEXT, companion_group_id TEXT,
 metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(task_id,id), UNIQUE(task_id,path_key),
 FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
 FOREIGN KEY(task_id,scope_id) REFERENCES task_scopes(task_id,id) ON DELETE CASCADE
);
CREATE TABLE file_profiles (
 id TEXT PRIMARY KEY,
 file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 cache_key TEXT NOT NULL, parser_version TEXT NOT NULL, options_hash TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('ready','partial','failed','unsupported')),
 profile_json TEXT NOT NULL CHECK(json_valid(profile_json)),
 payload_cache_path TEXT, payload_hash TEXT CHECK(payload_hash IS NULL OR length(payload_hash)=64),
 created_at TEXT NOT NULL, expires_at TEXT,
 UNIQUE(file_id,cache_key)
);
CREATE TABLE taxonomies (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL, scope_id TEXT NOT NULL,
 version INTEGER NOT NULL CHECK(version >= 1),
 source TEXT NOT NULL CHECK(source IN ('template','fixed','auto')),
 status TEXT NOT NULL CHECK(status IN ('draft','approved','superseded')),
 policy_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(policy_json)),
 tree_hash TEXT NOT NULL CHECK(length(tree_hash)=64),
 created_at TEXT NOT NULL, approved_at TEXT,
 UNIQUE(scope_id,version), UNIQUE(task_id,id),
 FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
 FOREIGN KEY(task_id,scope_id) REFERENCES task_scopes(task_id,id) ON DELETE CASCADE
);
CREATE TABLE categories (
 taxonomy_id TEXT NOT NULL REFERENCES taxonomies(id) ON DELETE CASCADE,
 category_id TEXT NOT NULL, parent_id TEXT, name TEXT NOT NULL CHECK(length(name)>0 AND length(name)<=60),
 path_segments_json TEXT NOT NULL CHECK(json_valid(path_segments_json)),
 depth INTEGER NOT NULL CHECK(depth BETWEEN 1 AND 3),
 ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
 selectable INTEGER NOT NULL DEFAULT 1 CHECK(selectable IN (0,1)),
 definition_json TEXT NOT NULL CHECK(json_valid(definition_json)),
 is_fallback INTEGER NOT NULL DEFAULT 0 CHECK(is_fallback IN (0,1)),
 PRIMARY KEY(taxonomy_id,category_id),
 FOREIGN KEY(taxonomy_id,parent_id) REFERENCES categories(taxonomy_id,category_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE model_calls (
 id TEXT PRIMARY KEY,
 task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
 provider_profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
 purpose TEXT NOT NULL CHECK(purpose IN ('probe','policy','caption','planning','classification','repair')),
 model_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 response_status TEXT NOT NULL CHECK(response_status IN ('ok','error','cancelled')),
 input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
 output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
 estimated_cost_micros INTEGER CHECK(estimated_cost_micros IS NULL OR estimated_cost_micros >= 0),
 currency TEXT, latency_ms INTEGER NOT NULL CHECK(latency_ms >= 0),
 error_code TEXT, created_at TEXT NOT NULL
);
CREATE TABLE classifications (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL, file_id TEXT NOT NULL,
 taxonomy_id TEXT NOT NULL, category_id TEXT,
 attempt INTEGER NOT NULL CHECK(attempt >= 1),
 source TEXT NOT NULL CHECK(source IN ('rule','ai','cache')),
 model_score REAL CHECK(model_score IS NULL OR (model_score>=0 AND model_score<=1)),
 review_band TEXT NOT NULL CHECK(review_band IN ('high','medium','low')),
 abstain INTEGER NOT NULL CHECK(abstain IN (0,1)),
 reason TEXT NOT NULL, evidence_refs_json TEXT NOT NULL CHECK(json_valid(evidence_refs_json)),
 warnings_json TEXT NOT NULL CHECK(json_valid(warnings_json)),
 model_call_id TEXT REFERENCES model_calls(id) ON DELETE SET NULL,
 input_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 CHECK((abstain=1 AND category_id IS NULL) OR (abstain=0 AND category_id IS NOT NULL)),
 UNIQUE(file_id,taxonomy_id,attempt),
 FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
 FOREIGN KEY(task_id,file_id) REFERENCES files(task_id,id) ON DELETE CASCADE,
 FOREIGN KEY(task_id,taxonomy_id) REFERENCES taxonomies(task_id,id) ON DELETE CASCADE,
 FOREIGN KEY(taxonomy_id,category_id) REFERENCES categories(taxonomy_id,category_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE reviews (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL, file_id TEXT NOT NULL,
 taxonomy_id TEXT NOT NULL, category_id TEXT,
 decision TEXT NOT NULL CHECK(decision IN ('accept','change','skip','quarantine')),
 revision INTEGER NOT NULL CHECK(revision >= 1),
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
 CHECK((decision IN ('accept','change','quarantine') AND category_id IS NOT NULL) OR decision='skip'),
 UNIQUE(file_id,revision),
 FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
 FOREIGN KEY(task_id,file_id) REFERENCES files(task_id,id) ON DELETE CASCADE,
 FOREIGN KEY(task_id,taxonomy_id) REFERENCES taxonomies(task_id,id) ON DELETE CASCADE,
 FOREIGN KEY(taxonomy_id,category_id) REFERENCES categories(taxonomy_id,category_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE plans (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 version INTEGER NOT NULL CHECK(version >= 1),
 plan_hash TEXT NOT NULL UNIQUE CHECK(length(plan_hash)=64),
 plan_kind TEXT NOT NULL DEFAULT 'forward' CHECK(plan_kind IN ('forward','undo')),
 parent_plan_id TEXT REFERENCES plans(id) ON DELETE RESTRICT,
 status TEXT NOT NULL CHECK(status IN ('draft','validated','approved','superseded','executing','finished')),
 operation_mode TEXT NOT NULL CHECK(operation_mode IN ('preview_move','direct_move','copy','report_only')),
 settings_hash TEXT NOT NULL CHECK(length(settings_hash)=64),
 taxonomy_hashes_json TEXT NOT NULL CHECK(json_valid(taxonomy_hashes_json)),
 source_snapshot_hash TEXT NOT NULL CHECK(length(source_snapshot_hash)=64),
 summary_json TEXT NOT NULL CHECK(json_valid(summary_json)),
 authorization_kind TEXT CHECK(authorization_kind IS NULL OR authorization_kind IN ('interactive','preauthorized')),
 authorization_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(authorization_json)),
 created_at TEXT NOT NULL, approved_at TEXT,
 CHECK((plan_kind='forward' AND parent_plan_id IS NULL) OR (plan_kind='undo' AND parent_plan_id IS NOT NULL)),
 UNIQUE(task_id,version)
);
CREATE TABLE operations (
 id TEXT PRIMARY KEY,
 plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
 file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
 action TEXT NOT NULL CHECK(action IN ('move','copy','skip','noop','recycle_copy')),
 source_path TEXT NOT NULL, target_path TEXT, target_key TEXT,
 source_snapshot_json TEXT NOT NULL CHECK(json_valid(source_snapshot_json)),
 expected_sha256 TEXT CHECK(expected_sha256 IS NULL OR length(expected_sha256)=64),
 temp_path TEXT,
 state TEXT NOT NULL CHECK(state IN ('PLANNED','PREPARED','COPYING','TEMP_WRITTEN','VERIFIED','PUBLISHED','SOURCE_REMOVED','COMMITTED','SKIPPED','FAILED','CONFLICT','UNDO_PREPARED','UNDONE','UNDO_CONFLICT')),
 reverses_operation_id TEXT REFERENCES operations(id) ON DELETE RESTRICT,
 actual_target_path TEXT, result_sha256 TEXT CHECK(result_sha256 IS NULL OR length(result_sha256)=64),
 error_code TEXT, companion_group_id TEXT, updated_at TEXT NOT NULL,
 CHECK(action <> 'recycle_copy' OR (reverses_operation_id IS NOT NULL AND expected_sha256 IS NOT NULL)),
 CHECK(action NOT IN ('move','copy') OR (target_path IS NOT NULL AND target_key IS NOT NULL AND expected_sha256 IS NOT NULL)),
 UNIQUE(plan_id,file_id), UNIQUE(plan_id,target_key), UNIQUE(plan_id,ordinal)
);
CREATE TABLE operation_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 operation_id TEXT NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
 seq INTEGER NOT NULL CHECK(seq >= 1), event_type TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 created_at TEXT NOT NULL, UNIQUE(operation_id,seq)
);
CREATE TABLE created_directories (
 id TEXT PRIMARY KEY,
 plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
 path TEXT NOT NULL, path_key TEXT NOT NULL,
 created_by_task INTEGER NOT NULL CHECK(created_by_task IN (0,1)),
 removed INTEGER NOT NULL DEFAULT 0 CHECK(removed IN (0,1)),
 created_at TEXT NOT NULL, UNIQUE(plan_id,path_key)
);
CREATE TABLE task_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 seq INTEGER NOT NULL CHECK(seq >= 1), event_type TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 created_at TEXT NOT NULL, UNIQUE(task_id,seq)
);
CREATE TABLE privacy_consents (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
 provider_profile_id TEXT NOT NULL REFERENCES model_profiles(id) ON DELETE RESTRICT,
 scope_hash TEXT NOT NULL CHECK(length(scope_hash)=64),
 grant_json TEXT NOT NULL CHECK(json_valid(grant_json)),
 granted_at TEXT NOT NULL, revoked_at TEXT
);
CREATE TABLE components (
 id TEXT PRIMARY KEY, component_type TEXT NOT NULL, version TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('missing','ready','invalid','disabled')),
 install_path TEXT, manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
 manifest_sha256 TEXT CHECK(manifest_sha256 IS NULL OR length(manifest_sha256)=64),
 last_verified_at TEXT
);
CREATE TABLE idempotency_keys (
 key TEXT NOT NULL, endpoint TEXT NOT NULL,
 request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
 response_json TEXT NOT NULL CHECK(json_valid(response_json)),
 status_code INTEGER NOT NULL CHECK(status_code BETWEEN 100 AND 599),
 created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
 PRIMARY KEY(endpoint,key)
);
CREATE INDEX idx_tasks_status_updated ON tasks(status,updated_at);
CREATE INDEX idx_files_task_modality ON files(task_id,modality);
CREATE INDEX idx_files_task_status ON files(task_id,scan_status);
CREATE INDEX idx_files_sha256 ON files(sha256);
CREATE INDEX idx_classifications_review ON classifications(task_id,review_band);
CREATE INDEX idx_operations_state ON operations(plan_id,state,ordinal);
CREATE INDEX idx_model_calls_task_created ON model_calls(task_id,created_at);
COMMIT;
