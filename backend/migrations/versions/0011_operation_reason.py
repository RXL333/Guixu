"""Persist the reason that is part of each approved operation hash.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(operations)")}
    if "reason" not in columns:
        connection.exec_driver_sql("ALTER TABLE operations ADD COLUMN reason TEXT")
        connection.exec_driver_sql("UPDATE operations SET reason='UNSUPPORTED_OR_UNDECIDED' WHERE action='skip' AND target_path IS NULL")
        connection.exec_driver_sql("UPDATE operations SET reason='REPORT_ONLY' WHERE action='noop' AND plan_id IN (SELECT id FROM plans WHERE operation_mode='report_only')")
        connection.exec_driver_sql("UPDATE operations SET reason='SOURCE_EQUALS_TARGET' WHERE action='noop' AND reason IS NULL")
    connection.exec_driver_sql("UPDATE schema_metadata SET version=11,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v11 does not support destructive automatic downgrade")
