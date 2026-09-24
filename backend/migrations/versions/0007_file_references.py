"""Persist immutable message-to-file reference snapshots."""

from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS conversation_message_file_references (
          message_id TEXT NOT NULL REFERENCES conversation_messages(id) ON DELETE RESTRICT,
          conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
          file_id TEXT NOT NULL REFERENCES files(id) ON DELETE RESTRICT,
          reference_source TEXT NOT NULL CHECK(reference_source IN (
            'UI_SELECTION','FOCUSED_FILE','RECENT_MESSAGE_REFERENCE','LATEST_PLAN_AFFECTED',
            'LATEST_EXECUTION_AFFECTED','ACTIVE_CATEGORY_ALL','EXPLICIT_FILENAME'
          )),
          reference_role TEXT NOT NULL DEFAULT 'SUBJECT' CHECK(reference_role IN ('SUBJECT','RESULT','CONTEXT')),
          path_snapshot TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY(message_id,file_id)
        )
    """)
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_message_file_references_message ON conversation_message_file_references(message_id,created_at)")
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_message_file_references_conversation_file ON conversation_message_file_references(conversation_id,file_id)")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=7,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v7 does not support destructive automatic downgrade")
