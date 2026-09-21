"""Add the PHASE D Conversation state layer without touching core history."""

from alembic import op

from guixu.infrastructure.db.database import Database


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the runtime and Alembic paths structurally identical. The helper only
    # creates new tables/nullable mappings and never rewrites existing core rows.
    connection = op.get_bind()
    Database._ensure_conversation_schema(connection)
    connection.exec_driver_sql("UPDATE schema_metadata SET version=4,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v4 does not support destructive automatic downgrade")
