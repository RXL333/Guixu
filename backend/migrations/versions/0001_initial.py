"""Create the v1 contract schema."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = Path(__file__).resolve().parents[3] / "contracts" / "database.sql"
    connection = op.get_bind().connection
    connection.executescript(schema.read_text("utf-8"))


def downgrade() -> None:
    raise RuntimeError("Guixu v1 does not support destructive automatic downgrade")

