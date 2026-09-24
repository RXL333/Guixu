"""conversation undo facade

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(conversation_execution_rounds)")}
    for column, declaration in (
        ("round_kind", "TEXT NOT NULL DEFAULT 'FORWARD'"),
        ("target_execution_round_id", "TEXT"),
        ("undo_state", "TEXT NOT NULL DEFAULT 'NOT_UNDONE'"),
        ("reversible_file_count", "INTEGER NOT NULL DEFAULT 0"),
        ("undone_file_count", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in columns:
            connection.exec_driver_sql(f"ALTER TABLE conversation_execution_rounds ADD COLUMN {column} {declaration}")
    connection.exec_driver_sql("""
      CREATE TABLE IF NOT EXISTS conversation_undo_plans (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
        target_execution_round_id TEXT NOT NULL REFERENCES conversation_execution_rounds(id) ON DELETE RESTRICT,
        core_plan_id TEXT REFERENCES plans(id) ON DELETE RESTRICT,
        status TEXT NOT NULL CHECK(status IN ('WAITING_FOR_APPROVAL','APPROVED','EXECUTING','COMPLETED','PARTIALLY_COMPLETED','BLOCKED','STALE','CANCELLED','RECOVERY_REQUIRED')),
        basis_file_state_revision INTEGER NOT NULL CHECK(basis_file_state_revision >= 1),
        plan_hash TEXT NOT NULL CHECK(length(plan_hash)=64),
        requested_file_ids_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(requested_file_ids_json)),
        summary_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(summary_json)),
        approval_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(approval_json)),
        execution_round_id TEXT REFERENCES conversation_execution_rounds(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL, approved_at TEXT, completed_at TEXT, cancelled_at TEXT
      )
    """)
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_conversation_undo_plans_conversation ON conversation_undo_plans(conversation_id,created_at DESC)")
    connection.exec_driver_sql("""
      CREATE TABLE IF NOT EXISTS conversation_undo_plan_items (
        id TEXT PRIMARY KEY,
        undo_plan_id TEXT NOT NULL REFERENCES conversation_undo_plans(id) ON DELETE RESTRICT,
        file_id TEXT NOT NULL REFERENCES files(id) ON DELETE RESTRICT,
        original_operation_id TEXT NOT NULL REFERENCES operations(id) ON DELETE RESTRICT,
        undo_operation_id TEXT REFERENCES operations(id) ON DELETE RESTRICT,
        operation_kind TEXT NOT NULL CHECK(operation_kind IN ('MOVE','COPY')),
        ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
        current_source TEXT NOT NULL,
        restore_target TEXT NOT NULL,
        expected_fingerprint TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('READY','COMPLETED','ALREADY_REVERSED','BLOCKED_MISSING','BLOCKED_MODIFIED','BLOCKED_EXTERNAL_MOVE','BLOCKED_TARGET_CONFLICT','BLOCKED_DEPENDENCY','BLOCKED_SCOPE','FAILED')),
        block_reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(undo_plan_id,original_operation_id)
      )
    """)
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_conversation_undo_plan_items_plan ON conversation_undo_plan_items(undo_plan_id,ordinal)")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=10,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v10 does not support destructive automatic downgrade")
