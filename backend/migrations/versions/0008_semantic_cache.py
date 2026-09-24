"""Add the provenance-aware semantic evidence ledger."""

from alembic import op


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS file_evidence (
          id TEXT PRIMARY KEY,
          file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          content_fingerprint TEXT NOT NULL CHECK(length(content_fingerprint)=64),
          evidence_kind TEXT NOT NULL CHECK(evidence_kind IN (
            'METADATA','TEXT_EXTRACT','OCR_TEXT','VISUAL_DESCRIPTION','DOCUMENT_SUMMARY',
            'AUDIO_TRANSCRIPT','AUDIO_SUMMARY','VIDEO_FRAME_DESCRIPTION','VIDEO_TRANSCRIPT',
            'VIDEO_SUMMARY','COMBINED_CONTENT_SUMMARY','USER_CONTEXT'
          )),
          evidence_schema_version INTEGER NOT NULL DEFAULT 1 CHECK(evidence_schema_version >= 1),
          payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
          normalized_content TEXT,
          state TEXT NOT NULL DEFAULT 'VALID' CHECK(state IN ('VALID','STALE','INVALID','REFRESHING','ERROR')),
          producer_type TEXT NOT NULL CHECK(producer_type IN ('LOCAL_PARSER','LOCAL_OCR','LOCAL_MEDIA','CLOUD_MODEL','LOCAL_MODEL','USER','LEGACY')),
          producer_name TEXT NOT NULL,
          producer_version TEXT NOT NULL DEFAULT 'unknown',
          model_profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
          model_id TEXT,
          prompt_version TEXT,
          quality TEXT CHECK(quality IS NULL OR quality IN ('high','medium','low')),
          completeness_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(completeness_json)),
          created_at TEXT NOT NULL,
          last_used_at TEXT,
          invalidated_at TEXT,
          invalidation_reason TEXT,
          error_code TEXT
        )
    """)
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_file_evidence_lookup ON file_evidence(file_id,content_fingerprint,evidence_kind,evidence_schema_version,state)")
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_file_evidence_fingerprint ON file_evidence(content_fingerprint,evidence_kind,state)")
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_file_evidence_cleanup ON file_evidence(state,invalidated_at)")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=8,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v8 does not support destructive automatic downgrade")
