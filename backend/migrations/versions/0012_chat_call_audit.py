"""Audit conversation discussion calls in `model_calls`.

Discussion runs before any Task exists, so chat rows keep `task_id` NULL and are
linked to the conversation instead. Per-Task budget accounting filters on `task_id`
and therefore stays unaffected.

Revision ID: 0012
Revises: 0011
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


NEW_TABLE = """CREATE TABLE model_calls_v12 (
 id TEXT PRIMARY KEY,
 task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
 conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
 provider_profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
 purpose TEXT NOT NULL CHECK(purpose IN ('probe','policy','caption','planning','classification','repair','chat')),
 model_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 response_status TEXT NOT NULL CHECK(response_status IN ('ok','error','cancelled')),
 input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
 output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
 estimated_cost_micros INTEGER CHECK(estimated_cost_micros IS NULL OR estimated_cost_micros >= 0),
 currency TEXT, latency_ms INTEGER NOT NULL CHECK(latency_ms >= 0),
 error_code TEXT, created_at TEXT NOT NULL
)"""

COLUMNS = ("id,task_id,provider_profile_id,purpose,model_id,request_hash,response_status,"
           "input_tokens,output_tokens,estimated_cost_micros,currency,latency_ms,error_code,created_at")


def _commit(driver) -> None:
    """Close the open transaction, if there is one.

    pysqlite raises `cannot commit - no transaction is active` on an unopened
    transaction, and unlike `rollback()` that is not a harmless no-op. Alembic
    does not guarantee a transaction is open at this point either: the statements
    above are PRAGMA and SELECT, which pysqlite's legacy autocommit mode does not
    wrap. Committing blindly therefore broke the upgrade for every legacy
    database, while a fresh install never reached the line because its schema
    already has the new shape.
    """
    if driver.in_transaction:
        driver.commit()


def upgrade() -> None:
    bind = op.get_bind()
    # 0001 executes contracts/database.sql, so a fresh database already has the new
    # shape and only legacy databases need the rebuild.
    columns = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(model_calls)")}
    definition = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='model_calls'"
    ).scalar()
    if "conversation_id" in columns and definition and "'chat'" in definition:
        # A fresh install already carries the new shape; only the version stamp is left.
        bind.exec_driver_sql("UPDATE schema_metadata SET version=12,updated_at=datetime('now') WHERE singleton=1")
        return

    # `classifications.model_call_id` references this table and SQLite cannot alter a
    # CHECK constraint in place. The rebuild therefore needs foreign keys disabled on
    # a committed connection; inside a transaction `PRAGMA foreign_keys` is a no-op and
    # DROP TABLE would fire ON DELETE SET NULL against the classification audit.
    driver = bind.connection.dbapi_connection
    _commit(driver)
    driver.execute("PRAGMA foreign_keys=OFF")
    try:
        driver.execute(NEW_TABLE)
        driver.execute(f"INSERT INTO model_calls_v12({COLUMNS}) SELECT {COLUMNS} FROM model_calls")
        driver.execute("DROP TABLE model_calls")
        driver.execute("ALTER TABLE model_calls_v12 RENAME TO model_calls")
        driver.execute("CREATE INDEX IF NOT EXISTS idx_model_calls_task_created ON model_calls(task_id,created_at)")
        driver.execute("CREATE INDEX IF NOT EXISTS idx_model_calls_conversation_created ON model_calls(conversation_id,created_at)")
        _commit(driver)
    except Exception:
        driver.rollback()
        raise
    finally:
        driver.execute("PRAGMA foreign_keys=ON")
        _commit(driver)
    if driver.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("DATABASE_MIGRATION_LEFT_FOREIGN_KEY_VIOLATION")
    bind.exec_driver_sql("UPDATE schema_metadata SET version=12,updated_at=datetime('now') WHERE singleton=1")


def downgrade() -> None:
    raise RuntimeError("Guixu v12 does not support destructive automatic downgrade")
