"""S16 - upgrade from a database that a real earlier release actually wrote.

The fixtures under `tests/fixtures/legacy_schemas/` are not written by this test.
Each one is the verbatim `contracts/database.sql` of a commit in this
repository's own history, taken with `git show <commit>:contracts/database.sql`:

    v001_20260914.sql  4e2700b  2026-09-14  22 tables, before conversations
    v002_20260921.sql  4aeb7cd  2026-09-21  30 tables, conversation data model
    v003_20260925.sql  8db48ab  2026-09-25  36 tables, near the current shape

Every other migration test builds its starting point from the *current* schema,
which is why this class of breakage stays invisible: a fresh install already has
the newest shape and takes the early-return branch, so the legacy rebuild path is
never executed. A real upgrade is the only thing that runs it.

Writing this file is what caught migration 0012 issuing a bare `COMMIT` against a
transaction pysqlite had never opened - every upgrade from a genuine older
database failed with `cannot commit - no transaction is active`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from guixu.infrastructure.db.database import Database


LEGACY_ERAS = [
    pytest.param("v001_20260914.sql", "0001", id="2026-09-14-22-tables"),
    pytest.param("v002_20260921.sql", "0004", id="2026-09-21-30-tables"),
    pytest.param("v003_20260925.sql", "0011", id="2026-09-25-36-tables"),
]


def _insert_if_present(connection: sqlite3.Connection, table: str, values: dict[str, object]) -> None:
    """Insert only the columns this era's schema actually has.

    Columns were added and dropped between the three fixtures, so nothing can be
    hard-coded. A value the era has no column for is a fact that era could not
    have stored, and skipping it is more honest than inventing a default.
    """
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    columns = [name for name in values if name in existing]
    if not columns:
        return
    connection.execute(
        f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
        [values[name] for name in columns],
    )


def _seed_a_real_history(connection: sqlite3.Connection) -> None:
    """One user, one task, one classified file, and the model call behind it.

    The classification is the point. `classifications.model_call_id` points at the
    very table that v12 rebuilds by dropping it, so a migration that forgets to
    suspend foreign keys nulls that link out and the audit trail silently stops
    saying which model call produced which decision.
    """
    _insert_if_present(connection, "model_profiles", {
        "id": "profile", "name": "本地模型", "provider": "deepseek", "runtime": "deepseek",
        "base_url": "https://api.deepseek.com", "model_id": "deepseek-chat", "secret_ref": None,
        "capabilities_json": "{}", "options_json": "{}", "trust_scope": "cloud",
        "enabled": 1, "revision": 1, "created_at": "2026-09-14 10:00:00",
        "updated_at": "2026-09-14 10:00:00",
    })
    _insert_if_present(connection, "tasks", {
        "id": "task", "name": "旧任务", "status": "DRAFT", "phase": "SETUP", "revision": 1,
        "settings_json": "{}", "settings_hash": "b" * 64, "classification_request_json": "{}",
        "model_snapshot_json": "{}", "rules_snapshot_json": "{}", "template_snapshot_json": "{}",
        "counters_json": "{}", "checkpoint_json": "{}",
        "created_at": "2026-09-14 10:00:00", "updated_at": "2026-09-14 10:00:00",
    })
    _insert_if_present(connection, "task_scopes", {
        "id": "scope", "task_id": "task", "kind": "whole_tree",
        "source_root": "C:/src", "destination_root": "C:/dst", "display_name": "全部",
        "settings_json": "{}",
    })
    _insert_if_present(connection, "files", {
        "id": "file", "task_id": "task", "scope_id": "scope",
        "original_path": "C:/src/a.jpg", "current_path": "C:/src/a.jpg", "path_key": "c:/src/a.jpg",
        "relative_path": "a.jpg", "basename": "a.jpg", "extension": ".jpg", "modality": "image",
        "size_bytes": 10, "mtime_ns": 1, "sha256": "c" * 64, "scan_status": "eligible",
        "metadata_json": "{}",
        "created_at": "2026-09-14 10:00:00", "updated_at": "2026-09-14 10:00:00",
    })
    _insert_if_present(connection, "taxonomies", {
        "id": "tax", "task_id": "task", "scope_id": "scope", "version": 1, "source": "auto",
        "status": "approved", "policy_json": "{}", "tree_hash": "d" * 64,
        "created_at": "2026-09-14 10:00:00",
    })
    # `categories` is keyed by `category_id` and carries its own tree columns in
    # every era; only the seed values differ from what the name suggests.
    _insert_if_present(connection, "categories", {
        "taxonomy_id": "tax", "category_id": "cat", "parent_id": None, "name": "照片",
        "path_segments_json": '["照片"]', "depth": 1, "ordinal": 0, "selectable": 1,
        "definition_json": "{}", "is_fallback": 0,
    })
    _insert_if_present(connection, "model_calls", {
        "id": "call", "task_id": "task", "provider_profile_id": "profile", "purpose": "classification",
        "model_id": "deepseek-chat", "request_hash": "e" * 64, "response_status": "ok",
        "input_tokens": 100, "output_tokens": 20, "latency_ms": 42,
        "created_at": "2026-09-14 10:00:00",
    })
    _insert_if_present(connection, "classifications", {
        "id": "cls", "task_id": "task", "file_id": "file", "taxonomy_id": "tax", "category_id": "cat",
        "attempt": 1, "source": "ai", "review_band": "high", "abstain": 0,
        "model_score": 0.9, "reason": "按内容归为照片",
        "evidence_refs_json": "[]", "warnings_json": "[]",
        "model_call_id": "call", "input_hash": "f" * 64, "created_at": "2026-09-14 10:00:00",
    })


def _build_legacy_database(project_root: Path, target: Path, fixture: str) -> None:
    legacy = project_root / "backend" / "tests" / "fixtures" / "legacy_schemas" / fixture
    connection = sqlite3.connect(target)
    try:
        connection.executescript(legacy.read_text(encoding="utf-8"))
        _seed_a_real_history(connection)
        connection.commit()
    finally:
        connection.close()


def _assert_genuinely_older(database_path: Path) -> None:
    """Guard that the fixture is not quietly the current schema in disguise.

    Table count is a poor proxy, so assert the property that actually decides
    which branch the migration takes: an old ledger has neither the conversation
    link nor the `chat` purpose, so the destructive rebuild runs. A fixture that
    already had both would pass while testing nothing.
    """
    connection = sqlite3.connect(database_path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(model_calls)")}
        definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='model_calls'"
        ).fetchone()[0]
        assert "conversation_id" not in columns
        assert "'chat'" not in definition
    finally:
        connection.close()


def _alembic_config(project_root: Path, database_path: Path) -> Config:
    config = Config(str(project_root / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


@pytest.mark.parametrize("fixture,stamp", LEGACY_ERAS)
def test_real_historical_database_upgrades_to_head_and_keeps_its_audit_trail(
    project_root: Path, tmp_path: Path, fixture: str, stamp: str
):
    """A database written by an actual earlier release must reach head with its data intact.

    This is the path a user who installed on 2026-09-14 takes on first launch of
    a new version.
    """
    database_path = tmp_path / "legacy.sqlite3"
    _build_legacy_database(project_root, database_path, fixture)
    _assert_genuinely_older(database_path)

    config = _alembic_config(project_root, database_path)
    command.stamp(config, stamp)
    command.upgrade(config, "head")

    upgraded = Database(database_path, project_root / "contracts" / "database.sql")
    with upgraded.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "0012"
        assert connection.exec_driver_sql("SELECT version FROM schema_metadata WHERE singleton=1").scalar_one() == 12
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []

        # The seeded user data is still there, field for field.
        assert connection.exec_driver_sql("SELECT name,status FROM tasks WHERE id='task'").one() == ("旧任务", "DRAFT")
        assert connection.exec_driver_sql("SELECT basename,size_bytes FROM files WHERE id='file'").one() == ("a.jpg", 10)
        assert connection.exec_driver_sql(
            "SELECT purpose,input_tokens,output_tokens,latency_ms FROM model_calls WHERE id='call'"
        ).one() == ("classification", 100, 20, 42)
        # The link that the destructive rebuild could have silently destroyed.
        assert connection.exec_driver_sql(
            "SELECT model_call_id FROM classifications WHERE id='cls'"
        ).scalar_one() == "call"

        definition = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='model_calls'"
        ).scalar_one()
        assert "conversation_id" in {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(model_calls)")}
        assert "'chat'" in definition, "the audit ledger must accept discussion calls after the upgrade"
    upgraded.close()

    # Re-opening through the application's own entry point proves the upgraded file
    # is usable, not merely structurally valid.
    reopened = Database(database_path, project_root / "contracts" / "database.sql")
    reopened.initialize()
    reopened.close()


@pytest.mark.parametrize("fixture,stamp", LEGACY_ERAS)
def test_historical_upgrade_is_repeatable_and_leaves_no_partial_state(
    project_root: Path, tmp_path: Path, fixture: str, stamp: str
):
    """Upgrading twice, and re-running a failed-looking upgrade, must both be safe.

    A migration that can only ever run once against a given file is a migration
    that strands anyone whose upgrade was interrupted by a crash or a closed
    laptop lid halfway through.
    """
    database_path = tmp_path / "legacy.sqlite3"
    _build_legacy_database(project_root, database_path, fixture)
    config = _alembic_config(project_root, database_path)
    command.stamp(config, stamp)

    command.upgrade(config, "head")
    first = sqlite3.connect(database_path)
    try:
        after_first = first.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        assert first.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0012"
    finally:
        first.close()

    # A second `upgrade head` is a no-op by definition, but re-stamping downwards and
    # climbing again is what a user who restored an old backup actually does.
    command.stamp(config, stamp)
    command.upgrade(config, "head")
    second = sqlite3.connect(database_path)
    try:
        assert second.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0] == after_first, "a repeated upgrade must not duplicate schema objects"
        assert second.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0012"
        assert second.execute("PRAGMA foreign_key_check").fetchall() == []
        assert second.execute("SELECT model_call_id FROM classifications WHERE id='cls'").fetchone()[0] == "call"
    finally:
        second.close()
