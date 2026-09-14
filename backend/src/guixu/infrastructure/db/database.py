from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection


CURRENT_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path, schema_path: Path) -> None:
        self.path = path
        self.schema_path = schema_path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(f"sqlite:///{path.as_posix()}", future=True)

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection: sqlite3.Connection, _: object) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.close()

    def initialize(self) -> None:
        with self.engine.connect() as connection:
            present = connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).scalar()
        if not present:
            script = self.schema_path.read_text("utf-8")
            raw = self.engine.raw_connection()
            try:
                raw.executescript(script)
                raw.commit()
            finally:
                raw.close()
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS schema_metadata (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL CHECK(version>=1), updated_at TEXT NOT NULL)"
            )
            version = connection.exec_driver_sql("SELECT version FROM schema_metadata WHERE singleton=1").scalar()
            if version is None:
                connection.exec_driver_sql(
                    "INSERT INTO schema_metadata(singleton,version,updated_at) VALUES(1,?,?)",
                    (CURRENT_SCHEMA_VERSION, utc_now()),
                )
            elif int(version) > CURRENT_SCHEMA_VERSION:
                raise RuntimeError("DATABASE_VERSION_NEWER_THAN_APPLICATION")
            elif int(version) < CURRENT_SCHEMA_VERSION:
                raise RuntimeError("DATABASE_MIGRATION_REQUIRED")

    def backup_for_migration(self) -> Path:
        """Create an SQLite-consistent, non-overwriting backup before a future migration."""
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        destination = backup_dir / f"{self.path.stem}-schema-{stamp}.sqlite3"
        source = sqlite3.connect(self.path)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()
        return destination

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def seed_json(self, key: str, value: object) -> None:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self.begin() as connection:
            connection.exec_driver_sql(
                "INSERT OR IGNORE INTO settings(key,value_json,revision,updated_at) VALUES(?,?,1,?)",
                (key, encoded, utc_now()),
            )

    def seed_builtin_template(self, template: dict[str, object]) -> None:
        encoded = json.dumps(template, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT OR IGNORE INTO template_versions(
                  id,template_key,version,name,origin,definition_json,definition_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    f"builtin:{template['template_id']}:v{template['version']}",
                    template["template_id"], template["version"], template["name"], "builtin",
                    encoded, digest, utc_now(),
                ),
            )

    def close(self) -> None:
        self.engine.dispose()
