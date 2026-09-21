"""Separate task revision from immutable plan authorization facts."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(plans)")}
    if "plan_basis_revision" not in columns:
        connection.exec_driver_sql("ALTER TABLE plans ADD COLUMN plan_basis_revision INTEGER NOT NULL DEFAULT 1")
        connection.exec_driver_sql("UPDATE plans SET plan_basis_revision=(SELECT revision FROM tasks WHERE tasks.id=plans.task_id)")
    if "approved_task_revision" not in columns:
        connection.exec_driver_sql("ALTER TABLE plans ADD COLUMN approved_task_revision INTEGER")
        connection.exec_driver_sql("UPDATE plans SET approved_task_revision=(SELECT revision FROM tasks WHERE tasks.id=plans.task_id) WHERE status IN ('approved','executing','finished')")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=2,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v2 does not support destructive automatic downgrade")
