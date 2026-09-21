"""Add non-destructive task record soft deletion."""

import json

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")}
    for column in ("deleted_at", "deletion_source", "delete_reason"):
        if column not in columns:
            connection.exec_driver_sql(f"ALTER TABLE tasks ADD COLUMN {column} TEXT")
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_tasks_deleted_updated ON tasks(deleted_at,updated_at DESC)"
    )
    for task_id, request_json, snapshot_json in connection.exec_driver_sql(
        "SELECT id,classification_request_json,template_snapshot_json FROM tasks"
    ).fetchall():
        request = json.loads(request_json or "{}")
        if not request.get("template_key") or json.loads(snapshot_json or "{}"):
            continue
        version = request.get("template_version")
        if version is None:
            row = connection.exec_driver_sql(
                "SELECT definition_json FROM template_versions WHERE template_key=? ORDER BY version DESC LIMIT 1",
                (request["template_key"],),
            ).first()
        else:
            row = connection.exec_driver_sql(
                "SELECT definition_json FROM template_versions WHERE template_key=? AND version=? LIMIT 1",
                (request["template_key"], version),
            ).first()
        if row:
            connection.exec_driver_sql("UPDATE tasks SET template_snapshot_json=? WHERE id=?", (row[0], task_id))
    connection.exec_driver_sql(
        "UPDATE schema_metadata SET version=3,updated_at=datetime('now') WHERE singleton=1"
    )


def downgrade() -> None:
    raise RuntimeError("Guixu v3 does not support destructive automatic downgrade")
