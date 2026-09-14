from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from guixu.api.app import create_app


TOKEN = "safe-operations-test"


def headers(key: str | None = None):
    result = {"X-Guixu-Session": TOKEN}
    if key:
        result["Idempotency-Key"] = key
    return result


def test_preview_move_approval_execute_and_undo_api(project_root: Path, tmp_path: Path, monkeypatch):
    source = tmp_path / "source"; source.mkdir(); original = source / "说明.txt"
    original.write_text("safe move", encoding="utf-8"); original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]
        settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
        settings.update({"operation_mode": "preview_move", "classification_source": "template"})
        created = client.post("/api/v1/tasks", headers=headers("create"), json={
            "name": "安全移动", "source_grant": grant["grant_id"], "settings": settings,
        }).json()["data"]
        scanned_response = client.post(
            f"/api/v1/tasks/{created['id']}/start", headers=headers("start"),
            json={"expected_revision": created["revision"]},
        )
        assert scanned_response.status_code == 202
        scanned = scanned_response.json()["data"]
        assert scanned["status"] == "AWAITING_EXECUTION_APPROVAL"
        compiled = client.post(
            f"/api/v1/tasks/{created['id']}/plan/compile", headers=headers("compile")
        ).json()["data"]
        target = Path(compiled["operations"][0]["target_path"])
        assert target == source / "文本" / "说明.txt" and original.exists() and not target.exists()
        rejected = client.post(f"/api/v1/tasks/{created['id']}/plan/approve", headers=headers("bad"), json={
            "expected_revision": scanned["revision"], "plan_id": compiled["plan_id"], "plan_hash": "0" * 64,
        })
        assert rejected.status_code == 409 and original.exists()
        approved = client.post(f"/api/v1/tasks/{created['id']}/plan/approve", headers=headers("approve"), json={
            "expected_revision": scanned["revision"], "plan_id": compiled["plan_id"], "plan_hash": compiled["plan_hash"],
        })
        assert approved.status_code == 200
        approved_retry = client.post(f"/api/v1/tasks/{created['id']}/plan/approve", headers=headers("approve-retry"), json={
            "expected_revision": scanned["revision"], "plan_id": compiled["plan_id"], "plan_hash": compiled["plan_hash"],
        })
        assert approved_retry.status_code == 200
        executed = client.post(f"/api/v1/tasks/{created['id']}/execute", headers=headers("execute"), json={
            "expected_revision": scanned["revision"], "plan_id": compiled["plan_id"], "plan_hash": compiled["plan_hash"],
        })
        assert executed.status_code == 202, executed.text
        assert not original.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == original_hash
        after_execute = client.get(f"/api/v1/tasks/{created['id']}", headers=headers()).json()["data"]
        undo = client.post(f"/api/v1/tasks/{created['id']}/undo/plan", headers=headers("undo-plan"), json={
            "expected_revision": after_execute["revision"], "plan_id": compiled["plan_id"], "plan_hash": compiled["plan_hash"],
        }).json()["data"]
        approved_undo = client.post(f"/api/v1/tasks/{created['id']}/plan/approve", headers=headers("undo-approve"), json={
            "expected_revision": after_execute["revision"], "plan_id": undo["plan_id"], "plan_hash": undo["plan_hash"],
        })
        assert approved_undo.status_code == 200
        undone = client.post(f"/api/v1/tasks/{created['id']}/execute", headers=headers("undo-execute"), json={
            "expected_revision": after_execute["revision"], "plan_id": undo["plan_id"], "plan_hash": undo["plan_hash"],
        })
        assert undone.status_code == 202, undone.text
        assert original.exists() and hashlib.sha256(original.read_bytes()).hexdigest() == original_hash and not target.exists()
        report = client.get(f"/api/v1/tasks/{created['id']}/report", headers=headers()).json()["data"]
        assert report["execution_summary"]["executed_count"] == 1
        assert report["undo_summary"]["available"] is False and report["undo_summary"]["recoverable"] == 0


def test_direct_move_is_disabled_in_production_and_available_only_with_test_gate(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); (source / "a.txt").write_text("direct")
    for allowed, expected in ((False, 400), (True, 201)):
        app = create_app(
            project_root=project_root, data_dir=tmp_path / f"data-{allowed}", session_token=TOKEN,
            allow_typed_grants=True, allow_direct_move=allowed,
        )
        with TestClient(app) as client:
            grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]
            settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
            settings.update({"operation_mode": "direct_move", "classification_source": "template"})
            response = client.post("/api/v1/tasks", headers=headers(f"direct-{allowed}"), json={
                "name": "直接移动测试门", "source_grant": grant["grant_id"], "settings": settings,
            })
            assert response.status_code == expected
