from __future__ import annotations

import csv
import json
import threading
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from guixu.api.app import create_app
from guixu.domain.plans import ExecutionPlan


TOKEN = "phase-07-session"


def headers(*, mutate: bool = False, key: str | None = None) -> dict[str, str]:
    result = {"X-Guixu-Session": TOKEN}
    if mutate:
        result["Idempotency-Key"] = key or str(uuid.uuid4())
    return result


def create_report_task(client: TestClient, source: Path) -> dict:
    grant = client.post(
        "/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}
    ).json()["data"]["grant_id"]
    settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
    settings.update({"operation_mode": "report_only", "classification_source": "template"})
    task = client.post(
        "/api/v1/tasks", headers=headers(mutate=True),
        json={"name": "阶段七可靠性", "source_grant": grant, "settings": settings},
    ).json()["data"]
    return client.post(
        f"/api/v1/tasks/{task['id']}/start", headers=headers(mutate=True),
        json={"expected_revision": task["revision"]},
    ).json()["data"]


def test_mutation_idempotency_replays_response_and_rejects_changed_body(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
        settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
        settings["operation_mode"] = "report_only"
        payload = {"name": "幂等创建", "source_grant": grant, "settings": settings}
        key = "same-logical-create"
        first = client.post("/api/v1/tasks", headers=headers(mutate=True, key=key), json=payload)
        second = client.post("/api/v1/tasks", headers=headers(mutate=True, key=key), json=payload)
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        assert len(client.get("/api/v1/tasks", headers=headers()).json()["data"]["items"]) == 1
        changed = client.post("/api/v1/tasks", headers=headers(mutate=True, key=key), json={**payload, "name": "不同正文"})
        assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
def test_parse_cache_reuses_content_but_keeps_independent_file_ids(project_root: Path, tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "first.txt").write_text("identical", encoding="utf-8")
    (source / "second.txt").write_text("identical", encoding="utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_report_task(client, source)
        files = client.get(f"/api/v1/tasks/{task['id']}/files", headers=headers()).json()["data"]["items"]
        calls = 0
        original = app.state.parsing.runner.parse

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(app.state.parsing.runner, "parse", counted)
        for item in files:
            response = client.post(
                f"/api/v1/tasks/{task['id']}/reanalyze", headers=headers(mutate=True),
                json={"expected_revision": task["revision"], "file_ids": [item["id"]]},
            )
            assert response.status_code == 202
        assert calls == 1
        details = [client.get(f"/api/v1/tasks/{task['id']}/files/{item['id']}", headers=headers()).json()["data"] for item in files]
        assert details[0]["profile"]["file_id"] != details[1]["profile"]["file_id"]


def test_startup_marks_active_task_recovery_required_and_events_are_monotonic(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.txt").write_text("recovery", encoding="utf-8")
    data_dir = tmp_path / "data"
    first = create_app(project_root=project_root, data_dir=data_dir, session_token=TOKEN, allow_typed_grants=True)
    with TestClient(first) as client:
        task = create_report_task(client, source)
        with first.state.database.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tasks SET status='RUNNING',phase='EXTRACT' WHERE id=?", (task["id"],)
            )
    second = create_app(project_root=project_root, data_dir=data_dir, session_token=TOKEN, allow_typed_grants=True)
    with TestClient(second) as client:
        recovered = client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).json()["data"]
        assert recovered["status"] == "RECOVERY_REQUIRED"
        events = client.get(f"/api/v1/tasks/{task['id']}/events?after_seq=0", headers=headers()).json()["data"]["items"]
        seqs = [event["seq"] for event in events]
        assert seqs == sorted(set(seqs))
        assert events[-1]["event_type"] == "recovery_required"
        checked = client.post(
            f"/api/v1/tasks/{task['id']}/recover", headers=headers(mutate=True),
            json={"expected_revision": recovered["revision"]},
        )
        assert checked.status_code == 202
        assert checked.json()["data"]["task"]["status"] == "PAUSED"


def test_pause_resume_cancel_use_revisioned_durable_transitions(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.txt").write_text("control", encoding="utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_report_task(client, source)
        with app.state.database.begin() as connection:
            connection.exec_driver_sql("UPDATE tasks SET status='RUNNING',phase='EXTRACT' WHERE id=?", (task["id"],))
        current = client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).json()["data"]
        paused = client.post(f"/api/v1/tasks/{task['id']}/pause", headers=headers(mutate=True), json={"expected_revision": current["revision"]})
        assert paused.status_code == 202 and paused.json()["data"]["status"] == "PAUSED"
        stale = client.post(f"/api/v1/tasks/{task['id']}/resume", headers=headers(mutate=True), json={"expected_revision": current["revision"]})
        assert stale.status_code == 409
        paused_task = paused.json()["data"]
        resumed = client.post(f"/api/v1/tasks/{task['id']}/resume", headers=headers(mutate=True), json={"expected_revision": paused_task["revision"]})
        assert resumed.status_code == 202 and resumed.json()["data"]["status"] == "RUNNING"
        running = resumed.json()["data"]
        cancelled = client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=headers(mutate=True), json={"expected_revision": running["revision"]})
        assert cancelled.status_code == 202 and cancelled.json()["data"]["status"] == "CANCELLED"


def test_report_export_requires_grant_is_no_clobber_and_csv_is_formula_safe(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    export_dir = tmp_path / "export"
    source.mkdir(); export_dir.mkdir()
    (source / "note.txt").write_text("report", encoding="utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_report_task(client, source)
        with app.state.database.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tasks SET checkpoint_json=? WHERE id=?",
                (json.dumps({"warnings": ["=CMD|' /C calc'!A0"]}), task["id"]),
            )
        grant = client.post(
            "/api/v1/dev/grants", headers=headers(), json={"path": str(export_dir), "purpose": "export"}
        ).json()["data"]["grant_id"]
        payload = {"export_grant": grant, "format": "csv", "filename": "report.csv"}
        first = client.post(f"/api/v1/tasks/{task['id']}/report/export", headers=headers(mutate=True), json=payload)
        assert first.status_code == 201
        with (export_dir / "report.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        assert any(row[2].startswith("'=") for row in rows if len(row) == 3)
        second = client.post(f"/api/v1/tasks/{task['id']}/report/export", headers=headers(mutate=True), json=payload)
        assert second.status_code == 409 and second.json()["error"]["code"] == "TARGET_APPEARED"
        outside = client.post(
            f"/api/v1/tasks/{task['id']}/report/export", headers=headers(mutate=True),
            json={"export_grant": grant, "format": "json", "filename": "../escape.json"},
        )
        assert outside.status_code == 422


def test_active_execution_pause_is_cooperative_and_keeps_plan_recoverable(project_root: Path, tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.txt").write_text("pause", encoding="utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_report_task(client, source)
        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()), task_id=task["id"], version=1, operation_mode="preview_move",
            settings_hash="a" * 64, taxonomy_hashes=("b" * 64,), source_snapshot_hash="c" * 64,
            plan_hash="d" * 64, operations=(),
        )
        app.state.operations.journal.persist_plan(plan)
        app.state.operations.journal.approve(plan.plan_id, plan.plan_hash)
        started = threading.Event()

        class BlockingExecutor:
            def __init__(self, journal, should_cancel):
                self.journal = journal
                self.should_cancel = should_cancel

            def execute(self, execution_plan, approved_hash):
                assert approved_hash == execution_plan.plan_hash
                self.journal.begin_execution(execution_plan.plan_id)
                started.set()
                assert threading.Event().wait(0.01) is False
                while not self.should_cancel():
                    threading.Event().wait(0.005)
                return False

        monkeypatch.setattr("guixu.application.coordinator.FileOperationExecutor", BlockingExecutor)
        current = client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).json()["data"]
        outcome: list[object] = []
        worker = threading.Thread(
            target=lambda: outcome.append(app.state.coordinator.execute(task["id"], plan.plan_id, plan.plan_hash, current["revision"])),
            daemon=True,
        )
        worker.start()
        assert started.wait(2)
        running = client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).json()["data"]
        response = client.post(
            f"/api/v1/tasks/{task['id']}/pause", headers=headers(mutate=True),
            json={"expected_revision": running["revision"]},
        )
        assert response.status_code == 202 and response.json()["data"]["status"] == "PAUSE_REQUESTED"
        worker.join(2)
        assert not worker.is_alive() and len(outcome) == 1
        paused = client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).json()["data"]
        assert paused["status"] == "PAUSED"
        with app.state.database.engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT status FROM plans WHERE id=?", (plan.plan_id,)).scalar_one() == "executing"
