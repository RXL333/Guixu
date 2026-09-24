"""Add restart-safe AgentTurn and workspace reconciliation records."""

from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(conversation_plan_versions)")}
    if "basis_file_state_revision" not in columns:
        connection.exec_driver_sql(
            "ALTER TABLE conversation_plan_versions ADD COLUMN basis_file_state_revision INTEGER NOT NULL DEFAULT 1"
        )
    connection.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS conversation_agent_turns (
          id TEXT PRIMARY KEY,
          conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
          task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
          plan_version_id TEXT REFERENCES conversation_plan_versions(id) ON DELETE SET NULL,
          execution_round_id TEXT REFERENCES conversation_execution_rounds(id) ON DELETE SET NULL,
          retry_of_turn_id TEXT REFERENCES conversation_agent_turns(id) ON DELETE SET NULL,
          turn_kind TEXT NOT NULL CHECK(turn_kind IN ('ANALYSIS','REPLANNING','EXECUTION','OTHER')),
          status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','WAITING_FOR_USER','WAITING_FOR_APPROVAL','COMPLETED','FAILED','CANCELLED','INTERRUPTED')),
          request_hash TEXT,
          checkpoint_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(checkpoint_json)),
          result_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result_json)),
          interruption_code TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          completed_at TEXT,
          last_heartbeat_at TEXT
        )
    """)
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_conversation_agent_turns_conversation ON conversation_agent_turns(conversation_id,created_at DESC)")
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_conversation_agent_turns_recovery ON conversation_agent_turns(status,created_at)")
    connection.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS conversation_reconciliations (
          id TEXT PRIMARY KEY,
          conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
          trigger TEXT NOT NULL CHECK(trigger IN ('STARTUP','OPEN','BEFORE_OPERATION','MANUAL')),
          scope_status TEXT NOT NULL CHECK(scope_status IN ('AVAILABLE','SCOPE_UNAVAILABLE','SCOPE_RELINK_REQUIRED')),
          file_state_revision INTEGER NOT NULL CHECK(file_state_revision >= 1),
          summary_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(summary_json)),
          requires_user_action INTEGER NOT NULL DEFAULT 0 CHECK(requires_user_action IN (0,1)),
          created_at TEXT NOT NULL
        )
    """)
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_conversation_reconciliations_conversation ON conversation_reconciliations(conversation_id,created_at DESC)")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=9,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v9 does not support destructive automatic downgrade")
