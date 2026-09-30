from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from guixu.api.app import create_app
from guixu.application.parser_runner import ParserRunner
from guixu.desktop.single_instance import SingleInstance
from guixu.infrastructure.db.database import Database
from guixu.main import application_data_dir


def test_dt02_single_instance_lock(tmp_path: Path):
    first = SingleInstance(tmp_path / "guixu.lock")
    second = SingleInstance(tmp_path / "guixu.lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="already running"):
            second.acquire()
    finally:
        first.release()


def test_dt02_rejects_wrong_host_and_origin(project_root: Path, tmp_path: Path):
    app = create_app(
        project_root=project_root,
        data_dir=tmp_path / "data",
        session_token="desktop-session",
        allowed_origins={"http://127.0.0.1:45678"},
    )
    with TestClient(app, base_url="http://127.0.0.1:45678") as client:
        valid_headers = {"X-Guixu-Session": "desktop-session", "Origin": "http://127.0.0.1:45678"}
        assert client.get("/api/v1/settings", headers=valid_headers).status_code == 200
        assert client.get(
            "/api/v1/settings",
            headers={**valid_headers, "Host": "evil.example"},
        ).json()["error"]["code"] == "HOST_REJECTED"
        assert client.get(
            "/api/v1/settings",
            headers={**valid_headers, "Origin": "https://evil.example"},
        ).json()["error"]["code"] == "ORIGIN_REJECTED"


def test_legacy_template_table_is_not_seeded_or_exposed_at_runtime(project_root: Path, tmp_path: Path):
    app = create_app(
        project_root=project_root,
        data_dir=tmp_path / "data",
        session_token="test",
        allow_typed_grants=True,
    )
    with TestClient(app):
        with app.state.database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM template_versions").scalar_one() == 0
        assert "/api/v1/templates" not in app.openapi()["paths"]


def test_dt04_frozen_worker_reuses_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import guixu.application.parser_runner as runner_module

    monkeypatch.setattr(runner_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runner_module.sys, "executable", r"C:\Program Files\Guixu\Guixu.exe")
    command = ParserRunner(tmp_path / "cache")._command(tmp_path / "job.json", tmp_path / "result.json")
    assert command[:2] == [r"C:\Program Files\Guixu\Guixu.exe", "--worker"]
    assert "-m" not in command


def test_dt07_database_version_and_consistent_backup(project_root: Path, tmp_path: Path):
    database = Database(tmp_path / "data" / "app.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version FROM schema_metadata WHERE singleton=1").scalar_one() == 12
    backup = database.backup_for_migration()
    assert backup.is_file() and backup.parent.name == "backups"
    copy = sqlite3.connect(backup)
    try:
        assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert copy.execute("SELECT version FROM schema_metadata WHERE singleton=1").fetchone()[0] == 12
    finally:
        copy.close()
        database.close()


def test_dt07_test_data_override_requires_explicit_test_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("GUIXU_TEST_DATA_DIR", str(tmp_path / "isolated"))
    monkeypatch.delenv("GUIXU_TEST_MODE", raising=False)
    assert application_data_dir() != (tmp_path / "isolated").resolve()
    monkeypatch.setenv("GUIXU_TEST_MODE", "1")
    assert application_data_dir() == (tmp_path / "isolated").resolve()
