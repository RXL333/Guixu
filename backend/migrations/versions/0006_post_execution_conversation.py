"""Add post-execution plan baselines and current category projection."""

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    plan_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(conversation_plan_versions)")}
    for column, declaration in (
        ("baseline_execution_round_id", "TEXT"),
        ("plan_kind", "TEXT NOT NULL DEFAULT 'FULL'"),
    ):
        if column not in plan_columns:
            connection.exec_driver_sql(f"ALTER TABLE conversation_plan_versions ADD COLUMN {column} {declaration}")
    file_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(conversation_files)")}
    if "current_category_id" not in file_columns:
        connection.exec_driver_sql("ALTER TABLE conversation_files ADD COLUMN current_category_id TEXT")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=6,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v6 does not support destructive automatic downgrade")
