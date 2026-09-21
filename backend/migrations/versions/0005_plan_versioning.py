"""Complete immutable Conversation plan versioning metadata and approvals."""

from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(conversation_plan_versions)")}
    additions = (
        ("kept_file_count", "INTEGER NOT NULL DEFAULT 0"),
        ("conflict_count", "INTEGER NOT NULL DEFAULT 0"),
        ("created_by_message_id", "TEXT"),
        ("restored_from_version_id", "TEXT"),
    )
    for column, declaration in additions:
        if column not in columns:
            connection.exec_driver_sql(f"ALTER TABLE conversation_plan_versions ADD COLUMN {column} {declaration}")
    connection.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS conversation_plan_approvals (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
            plan_version_id TEXT NOT NULL REFERENCES conversation_plan_versions(id) ON DELETE RESTRICT,
            plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
            plan_hash TEXT NOT NULL CHECK(length(plan_hash)=64),
            context_revision INTEGER NOT NULL CHECK(context_revision >= 1),
            status TEXT NOT NULL CHECK(status IN ('ACTIVE','STALE','REVOKED')),
            authorization_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(authorization_json)),
            approved_at TEXT NOT NULL,
            superseded_at TEXT,
            UNIQUE(plan_version_id)
        )
    """)
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_conversation_plan_approvals_conversation ON conversation_plan_approvals(conversation_id,status,approved_at DESC)")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=5,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v5 does not support destructive automatic downgrade")

