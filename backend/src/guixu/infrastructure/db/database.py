from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection


CURRENT_SCHEMA_VERSION = 6


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
        if version is not None and int(version) < CURRENT_SCHEMA_VERSION:
            self._migrate(int(version))

    def _migrate(self, version: int) -> None:
        if version not in {1, 2, 3, 4, 5}:
            raise RuntimeError("DATABASE_MIGRATION_REQUIRED")
        self.backup_for_migration()
        with self.engine.begin() as connection:
            if version <= 2:
                columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(plans)")}
                if "plan_basis_revision" not in columns:
                    connection.exec_driver_sql("ALTER TABLE plans ADD COLUMN plan_basis_revision INTEGER NOT NULL DEFAULT 1")
                    connection.exec_driver_sql("UPDATE plans SET plan_basis_revision=(SELECT revision FROM tasks WHERE tasks.id=plans.task_id)")
                if "approved_task_revision" not in columns:
                    connection.exec_driver_sql("ALTER TABLE plans ADD COLUMN approved_task_revision INTEGER")
                    connection.exec_driver_sql("UPDATE plans SET approved_task_revision=(SELECT revision FROM tasks WHERE tasks.id=plans.task_id) WHERE status IN ('approved','executing','finished')")
            if version <= 3:
                task_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")}
                for column, declaration in (
                    ("deleted_at", "TEXT"),
                    ("deletion_source", "TEXT"),
                    ("delete_reason", "TEXT"),
                ):
                    if column not in task_columns:
                        connection.exec_driver_sql(f"ALTER TABLE tasks ADD COLUMN {column} {declaration}")
                # Freeze legacy template definitions while the compatibility table still exists.
                # New tasks never read or write template_versions.
                legacy_rows = connection.exec_driver_sql(
                    "SELECT id,classification_request_json,template_snapshot_json FROM tasks"
                ).fetchall()
                for task_id, request_json, snapshot_json in legacy_rows:
                    request = json.loads(request_json or "{}")
                    snapshot = json.loads(snapshot_json or "{}")
                    template_key = request.get("template_key")
                    if not template_key or snapshot:
                        continue
                    template_version = request.get("template_version")
                    if template_version is None:
                        row = connection.exec_driver_sql(
                            "SELECT definition_json FROM template_versions WHERE template_key=? ORDER BY version DESC LIMIT 1",
                            (template_key,),
                        ).first()
                    else:
                        row = connection.exec_driver_sql(
                            "SELECT definition_json FROM template_versions WHERE template_key=? AND version=? LIMIT 1",
                            (template_key, template_version),
                        ).first()
                    if row:
                        connection.exec_driver_sql(
                            "UPDATE tasks SET template_snapshot_json=? WHERE id=?", (row[0], task_id)
                        )
                connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tasks_deleted_updated ON tasks(deleted_at,updated_at DESC)")
                connection.exec_driver_sql("UPDATE schema_metadata SET version=3,updated_at=? WHERE singleton=1", (utc_now(),))
            if version <= 3:
                self._ensure_conversation_schema(connection)
                connection.exec_driver_sql("UPDATE schema_metadata SET version=4,updated_at=? WHERE singleton=1", (utc_now(),))
            if version <= 4:
                self._ensure_plan_versioning_schema(connection)
                connection.exec_driver_sql("UPDATE schema_metadata SET version=5,updated_at=? WHERE singleton=1", (utc_now(),))
            if version <= 5:
                self._ensure_post_execution_schema(connection)
                connection.exec_driver_sql("UPDATE schema_metadata SET version=6,updated_at=? WHERE singleton=1", (utc_now(),))

    @staticmethod
    def _ensure_conversation_schema(connection: Connection) -> None:
        """Create the PHASE D state layer without rewriting existing core tables."""
        statements = (
            """CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL CHECK(length(title)>0 AND length(title)<=160),
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','ARCHIVED','DELETED','ERROR')),
                revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
                model_profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json)),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                deleted_at TEXT, last_message_at TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversations_status_updated ON conversations(status,updated_at DESC)",
            """CREATE TABLE IF NOT EXISTS conversation_scopes (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
                scope_kind TEXT NOT NULL CHECK(scope_kind IN ('folder','task_scope','selection')),
                source_root TEXT NOT NULL,
                display_name TEXT NOT NULL,
                authorization_ref TEXT,
                authorization_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(authorization_json)),
                scope_hash TEXT NOT NULL CHECK(length(scope_hash)=64),
                created_at TEXT NOT NULL, revoked_at TEXT,
                UNIQUE(conversation_id,source_root)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversation_scopes_conversation ON conversation_scopes(conversation_id,created_at)",
            """CREATE TABLE IF NOT EXISTS conversation_plan_versions (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
                version_number INTEGER NOT NULL CHECK(version_number >= 1),
                parent_plan_version_id TEXT REFERENCES conversation_plan_versions(id) ON DELETE RESTRICT,
                baseline_execution_round_id TEXT REFERENCES conversation_execution_rounds(id) ON DELETE RESTRICT,
                basis_context_revision INTEGER NOT NULL CHECK(basis_context_revision >= 1),
                source TEXT NOT NULL CHECK(source IN ('USER_REQUEST','SYSTEM','LEGACY')),
                plan_kind TEXT NOT NULL DEFAULT 'FULL' CHECK(plan_kind IN ('FULL','DELTA')),
                status TEXT NOT NULL CHECK(status IN ('DRAFT','PROPOSED','APPROVED','EXECUTED','SUPERSEDED','CANCELLED')),
                taxonomy_id TEXT REFERENCES taxonomies(id) ON DELETE RESTRICT,
                taxonomy_snapshot_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(taxonomy_snapshot_json)),
                plan_id TEXT REFERENCES plans(id) ON DELETE RESTRICT,
                plan_hash TEXT CHECK(plan_hash IS NULL OR length(plan_hash)=64),
                summary TEXT NOT NULL DEFAULT '',
                change_summary_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(change_summary_json)),
                affected_file_count INTEGER NOT NULL DEFAULT 0 CHECK(affected_file_count >= 0),
                kept_file_count INTEGER NOT NULL DEFAULT 0 CHECK(kept_file_count >= 0),
                conflict_count INTEGER NOT NULL DEFAULT 0 CHECK(conflict_count >= 0),
                created_by_message_id TEXT REFERENCES conversation_messages(id) ON DELETE SET NULL,
                restored_from_version_id TEXT REFERENCES conversation_plan_versions(id) ON DELETE RESTRICT,
                created_at TEXT NOT NULL, approved_at TEXT, executed_at TEXT, superseded_at TEXT,
                UNIQUE(conversation_id,version_number)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversation_plan_versions_conversation ON conversation_plan_versions(conversation_id,version_number)",
            """CREATE TABLE IF NOT EXISTS conversation_plan_approvals (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
                plan_version_id TEXT NOT NULL REFERENCES conversation_plan_versions(id) ON DELETE RESTRICT,
                plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
                plan_hash TEXT NOT NULL CHECK(length(plan_hash)=64),
                context_revision INTEGER NOT NULL CHECK(context_revision >= 1),
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','STALE','REVOKED')),
                authorization_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(authorization_json)),
                approved_at TEXT NOT NULL,
                superseded_at TEXT,
                UNIQUE(plan_version_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversation_plan_approvals_conversation ON conversation_plan_approvals(conversation_id,status,approved_at DESC)",
            """CREATE TABLE IF NOT EXISTS conversation_execution_rounds (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
                round_number INTEGER NOT NULL CHECK(round_number >= 1),
                plan_version_id TEXT NOT NULL REFERENCES conversation_plan_versions(id) ON DELETE RESTRICT,
                execution_plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
                undo_plan_id TEXT REFERENCES plans(id) ON DELETE RESTRICT,
                status TEXT NOT NULL CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED','RECOVERY_REQUIRED')),
                undo_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED' CHECK(undo_status IN ('NOT_REQUESTED','AVAILABLE','PREPARED','EXECUTED','BLOCKED')),
                started_at TEXT, completed_at TEXT,
                summary_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(summary_json)),
                affected_file_count INTEGER NOT NULL DEFAULT 0 CHECK(affected_file_count >= 0),
                created_at TEXT NOT NULL,
                UNIQUE(conversation_id,round_number)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversation_execution_rounds_conversation ON conversation_execution_rounds(conversation_id,round_number)",
            """CREATE TABLE IF NOT EXISTS conversation_contexts (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id) ON DELETE RESTRICT,
                context_revision INTEGER NOT NULL DEFAULT 1 CHECK(context_revision >= 1),
                current_taxonomy_id TEXT REFERENCES taxonomies(id) ON DELETE SET NULL,
                current_plan_version_id TEXT REFERENCES conversation_plan_versions(id) ON DELETE SET NULL,
                current_execution_round_id TEXT REFERENCES conversation_execution_rounds(id) ON DELETE SET NULL,
                model_profile_id TEXT REFERENCES model_profiles(id) ON DELETE SET NULL,
                max_directory_depth INTEGER NOT NULL DEFAULT 2 CHECK(max_directory_depth BETWEEN 1 AND 3),
                organization_intent_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(organization_intent_json)),
                confirmed_requirements_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(confirmed_requirements_json)),
                privacy_scope_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(privacy_scope_json)),
                selection_state_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(selection_state_json)),
                file_state_revision INTEGER NOT NULL DEFAULT 1 CHECK(file_state_revision >= 1),
                strategy_state_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(strategy_state_json)),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS conversation_files (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
                file_id TEXT NOT NULL REFERENCES files(id) ON DELETE RESTRICT,
                first_seen_path TEXT NOT NULL,
                current_known_path TEXT NOT NULL,
                first_seen_fingerprint TEXT, current_fingerprint TEXT,
                first_seen_size_bytes INTEGER CHECK(first_seen_size_bytes IS NULL OR first_seen_size_bytes >= 0),
                current_size_bytes INTEGER CHECK(current_size_bytes IS NULL OR current_size_bytes >= 0),
                first_seen_mtime_ns INTEGER, current_mtime_ns INTEGER,
                current_category_id TEXT,
                added_at TEXT NOT NULL, removed_from_scope_at TEXT, last_verified_at TEXT,
                state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(state IN ('ACTIVE','FILE_CHANGED','MISSING','REMOVED')),
                UNIQUE(conversation_id,file_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversation_files_conversation_state ON conversation_files(conversation_id,state)",
            """CREATE TABLE IF NOT EXISTS conversation_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
                role TEXT NOT NULL CHECK(role IN ('USER','ASSISTANT','SYSTEM_EVENT')),
                content TEXT NOT NULL CHECK(length(content)>0),
                sequence_number INTEGER NOT NULL CHECK(sequence_number >= 1),
                message_type TEXT NOT NULL CHECK(message_type IN ('TEXT','STATUS','PLAN_PROPOSAL','EXECUTION_RESULT','ERROR','SYSTEM_EVENT')),
                status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','REDACTED')),
                referenced_plan_version_id TEXT REFERENCES conversation_plan_versions(id) ON DELETE SET NULL,
                referenced_execution_round_id TEXT REFERENCES conversation_execution_rounds(id) ON DELETE SET NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json)),
                created_at TEXT NOT NULL,
                UNIQUE(conversation_id,sequence_number)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_conversation_messages_order ON conversation_messages(conversation_id,sequence_number)",
        )
        for statement in statements:
            connection.exec_driver_sql(statement)
        task_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(tasks)")}
        if "conversation_id" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL")
        if "conversation_plan_version_id" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN conversation_plan_version_id TEXT REFERENCES conversation_plan_versions(id) ON DELETE SET NULL")
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_tasks_conversation ON tasks(conversation_id,updated_at DESC)")

    @staticmethod
    def _ensure_plan_versioning_schema(connection: Connection) -> None:
        """Extend the PHASE D version rows without rewriting historical plans."""
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(conversation_plan_versions)")}
        additions = (
            ("kept_file_count", "INTEGER NOT NULL DEFAULT 0"),
            ("conflict_count", "INTEGER NOT NULL DEFAULT 0"),
            ("created_by_message_id", "TEXT"),
            ("restored_from_version_id", "TEXT"),
        )
        for column, declaration in additions:
            if column not in columns:
                connection.exec_driver_sql(f"ALTER TABLE conversation_plan_versions ADD COLUMN {column} {declaration}")
        connection.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS conversation_plan_approvals (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE RESTRICT,
                plan_version_id TEXT NOT NULL REFERENCES conversation_plan_versions(id) ON DELETE RESTRICT,
                plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
                plan_hash TEXT NOT NULL CHECK(length(plan_hash)=64),
                context_revision INTEGER NOT NULL CHECK(context_revision >= 1),
                status TEXT NOT NULL CHECK(status IN ('ACTIVE','STALE','REVOKED')),
                authorization_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(authorization_json)),
                approved_at TEXT NOT NULL,
                superseded_at TEXT,
                UNIQUE(plan_version_id)
            )
        """)
        connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_conversation_plan_approvals_conversation ON conversation_plan_approvals(conversation_id,status,approved_at DESC)")

    @staticmethod
    def _ensure_post_execution_schema(connection: Connection) -> None:
        """Add immutable execution baselines and current workspace projections."""
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

    def close(self) -> None:
        self.engine.dispose()
