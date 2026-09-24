from pathlib import Path
import json
import sqlite3

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from guixu.infrastructure.db.database import Database


def test_initial_schema_and_pragmas(project_root: Path, tmp_path: Path):
    database = Database(tmp_path / "db" / "test.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    with database.engine.connect() as connection:
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        assert {"tasks", "files", "plans", "operations", "privacy_consents"} <= tables
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 2
    database.close()


def test_alembic_initial_migration_creates_contract_schema(project_root: Path, tmp_path: Path):
    database_path = tmp_path / "migration.sqlite3"
    config = Config(str(project_root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"alembic_version", "tasks", "files", "operations", "conversations", "conversation_messages", "conversation_contexts"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0010"
        plan_columns = {row[1] for row in connection.execute("PRAGMA table_info(plans)")}
        assert {"plan_basis_revision", "approved_task_revision"} <= plan_columns
        version_columns = {row[1] for row in connection.execute("PRAGMA table_info(conversation_plan_versions)")}
        assert {"kept_file_count", "conflict_count", "created_by_message_id", "restored_from_version_id",
                "baseline_execution_round_id", "plan_kind"} <= version_columns
        file_columns = {row[1] for row in connection.execute("PRAGMA table_info(conversation_files)")}
        assert "current_category_id" in file_columns
        assert {"conversation_plan_approvals", "conversation_message_file_references"} <= tables
        task_columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        assert {"deleted_at", "deletion_source", "delete_reason", "conversation_id", "conversation_plan_version_id"} <= task_columns
    finally:
        connection.close()


def test_alembic_v4_to_v5_plan_versioning_upgrade_is_repeatable(project_root: Path, tmp_path: Path):
    database_path = tmp_path / "incremental.sqlite3"
    config = Config(str(project_root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "0004")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version FROM schema_metadata WHERE singleton=1").fetchone()[0] == 4
        # The base contract is intentionally forward-compatible, so v4 can
        # already contain nullable v5 columns; 0005 must still be idempotent.
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_plan_versions'").fetchone()
    finally:
        connection.close()
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0010"
        assert connection.execute("SELECT version FROM schema_metadata WHERE singleton=1").fetchone()[0] == 10
        columns = {row[1] for row in connection.execute("PRAGMA table_info(conversation_plan_versions)")}
        assert {"kept_file_count", "conflict_count", "created_by_message_id", "restored_from_version_id",
                "baseline_execution_round_id", "plan_kind"} <= columns
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_plan_approvals'").fetchone()
    finally:
        connection.close()
    command.upgrade(config, "head")


def test_v2_to_v7_migration_is_backed_up_and_repeatable(project_root: Path, tmp_path: Path):
    path = tmp_path / "data" / "legacy.sqlite3"
    database = Database(path, project_root / "contracts" / "database.sql")
    database.initialize()
    backups_before = len(list((path.parent / "backups").glob("legacy-schema-*.sqlite3")))
    with database.engine.begin() as connection:
        connection.exec_driver_sql("UPDATE schema_metadata SET version=2")
        definition = json.dumps({"template_id":"legacy.course","version":1,"name":"旧模板","nodes":[]}, ensure_ascii=False)
        connection.exec_driver_sql(
            "INSERT INTO template_versions(id,template_key,version,name,origin,definition_json,definition_hash,created_at) VALUES(?,?,?,?,?,?,?,datetime('now'))",
            ("legacy-template", "legacy.course", 1, "旧模板", "builtin", definition, "a" * 64),
        )
        connection.exec_driver_sql(
            """INSERT INTO tasks(id,name,status,phase,revision,settings_json,settings_hash,classification_request_json,
               template_snapshot_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))""",
            ("legacy-task", "旧任务", "DRAFT", "SETUP", 1, "{}", "b" * 64,
             json.dumps({"template_key":"legacy.course"}), "{}"),
        )
    database.close()

    upgraded = Database(path, project_root / "contracts" / "database.sql")
    upgraded.initialize()
    with upgraded.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version FROM schema_metadata WHERE singleton=1").scalar_one() == 10
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")}
        assert {"deleted_at", "deletion_source", "delete_reason", "conversation_id", "conversation_plan_version_id"} <= columns
        tables = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"conversations", "conversation_plan_versions", "conversation_plan_approvals", "conversation_execution_rounds", "conversation_message_file_references", "file_evidence"} <= tables
        snapshot = connection.exec_driver_sql(
            "SELECT template_snapshot_json FROM tasks WHERE id='legacy-task'"
        ).scalar_one()
        assert json.loads(snapshot)["name"] == "旧模板"
    backups = list((path.parent / "backups").glob("legacy-schema-*.sqlite3"))
    assert len(backups) == backups_before + 1 and all(item.stat().st_size > 0 for item in backups)
    upgraded.initialize()
    assert len(list((path.parent / "backups").glob("legacy-schema-*.sqlite3"))) == backups_before + 1
    upgraded.close()
