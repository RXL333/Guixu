from pathlib import Path
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
        assert {"alembic_version", "tasks", "files", "operations"} <= tables
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0001"
    finally:
        connection.close()
