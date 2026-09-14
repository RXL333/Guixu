from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from guixu.api.app import create_app


def headers(token: str, idempotency: bool = False) -> dict[str, str]:
    values = {"X-Guixu-Session": token}
    if idempotency:
        values["Idempotency-Key"] = "test-request-1"
    return values


def test_authenticated_report_only_flow(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    sample = source / "说明.txt"
    sample.write_text("只读样本", encoding="utf-8")
    before = hashlib.sha256(sample.read_bytes()).hexdigest()
    token = "test-session"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token, allow_typed_grants=True)
    with TestClient(app) as client:
        assert client.get("/api/v1/settings").status_code == 401
        templates = client.get("/api/v1/templates", headers=headers(token)).json()["data"]
        assert templates["total"] == 24 and any(item["template_id"] == "universal.types" for item in templates["items"])
        grant_response = client.post(
            "/api/v1/dev/grants", headers=headers(token), json={"path": str(source), "purpose": "source"}
        )
        assert grant_response.status_code == 200
        grant_id = grant_response.json()["data"]["grant_id"]
        defaults = client.get("/api/v1/settings", headers=headers(token)).json()["data"]["values"]
        defaults.update({"operation_mode": "report_only", "classification_source": "template"})
        create = client.post(
            "/api/v1/tasks",
            headers=headers(token, True),
            json={"name": "API只读扫描", "source_grant": grant_id, "settings": defaults},
        )
        assert create.status_code == 201, create.text
        task = create.json()["data"]
        started = client.post(
            f"/api/v1/tasks/{task['id']}/start",
            headers=headers(token, True),
            json={"expected_revision": task["revision"]},
        )
        assert started.status_code == 202, started.text
        result = started.json()["data"]
        assert result["status"] == "COMPLETED"
        files = client.get(f"/api/v1/tasks/{task['id']}/files", headers=headers(token)).json()["data"]
        assert files["total"] == 1
        assert files["items"][0]["modality"] == "text"
        file_id = files["items"][0]["id"]
        before_profile = client.get(f"/api/v1/tasks/{task['id']}/files/{file_id}", headers=headers(token))
        assert before_profile.status_code == 200 and before_profile.json()["data"]["profile"] is None
        parsed = client.post(
            f"/api/v1/tasks/{task['id']}/reanalyze",
            headers=headers(token, True),
            json={"expected_revision": result["revision"], "file_ids": [file_id]},
        )
        assert parsed.status_code == 202, parsed.text
        detail = client.get(f"/api/v1/tasks/{task['id']}/files/{file_id}", headers=headers(token)).json()["data"]
        assert detail["profile"]["file_id"] == file_id
        assert detail["profile"]["evidence"][0]["text"] == "只读样本"
        taxonomy = client.get(f"/api/v1/tasks/{task['id']}/taxonomies", headers=headers(token)).json()["data"][0]
        assert taxonomy["status"] == "draft" and taxonomy["policy"]["template_key"] == "universal.types"
        approved = client.post(f"/api/v1/tasks/{task['id']}/taxonomies/{taxonomy['taxonomy_id']}/approve", headers=headers(token, True), json={"expected_revision": result["revision"], "tree_hash": taxonomy["tree_hash"]})
        assert approved.status_code == 202, approved.text
        detail = client.get(f"/api/v1/tasks/{task['id']}/files/{file_id}", headers=headers(token)).json()["data"]
        assert detail["suggestion"]["category_id"] == "universal.types.text" and detail["latest_review"] is None
        task_after_approve = client.get(f"/api/v1/tasks/{task['id']}", headers=headers(token)).json()["data"]
        reviewed = client.post(f"/api/v1/tasks/{task['id']}/reviews/bulk", headers=headers(token, True), json={"expected_revision": task_after_approve["revision"], "items": [{"file_id": file_id, "taxonomy_id": taxonomy["taxonomy_id"], "category_id": "universal.types.image", "decision": "change", "note": "人工纠正测试"}]})
        assert reviewed.status_code == 200 and reviewed.json()["data"]["new_revision"] == task_after_approve["revision"] + 1
        detail = client.get(f"/api/v1/tasks/{task['id']}/files/{file_id}", headers=headers(token)).json()["data"]
        assert detail["suggestion"]["category_id"] == "universal.types.text"
        assert detail["latest_review"]["category_id"] == "universal.types.image"
        report = client.get(f"/api/v1/tasks/{task['id']}/report", headers=headers(token)).json()["data"]
        assert report["execution_summary"]["executed_count"] == 0
        assert hashlib.sha256(sample.read_bytes()).hexdigest() == before


def test_rule_api_persists_ast_and_read_only_preview(project_root: Path, tmp_path: Path):
    token = "test-session"; source = tmp_path / "source"; source.mkdir(); (source / "cache.tmp").write_text("test")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token, allow_typed_grants=True)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(token), json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
        defaults = client.get("/api/v1/settings", headers=headers(token)).json()["data"]["values"]
        defaults.update({"operation_mode": "report_only", "classification_source": "template"})
        task = client.post("/api/v1/tasks", headers=headers(token, True), json={"name": "规则试跑", "source_grant": grant, "settings": defaults}).json()["data"]
        task = client.post(f"/api/v1/tasks/{task['id']}/start", headers=headers(token, True), json={"expected_revision": task["revision"]}).json()["data"]
        file_id = client.get(f"/api/v1/tasks/{task['id']}/files", headers=headers(token)).json()["data"]["items"][0]["id"]
        rule = {"name": "排除 tmp", "priority": 10, "enabled": True, "scope": {}, "condition": {"field": "extension", "op": "eq", "value": ".tmp"}, "action": {"type": "exclude", "category_id": None, "template_key": None}}
        created = client.post("/api/v1/rules", headers=headers(token, True), json=rule)
        assert created.status_code == 201 and created.json()["data"]["condition"] == rule["condition"]
        preview = client.post("/api/v1/rules/test", headers=headers(token, True), json={"task_id": task["id"], "file_ids": [file_id], "draft_rule": rule})
        assert preview.status_code == 200 and preview.json()["data"]["matched_file_ids"] == [file_id]
        assert (source / "cache.tmp").exists()


def test_path_outside_grant_cannot_create_task(project_root: Path, tmp_path: Path):
    token = "test-session"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token, allow_typed_grants=True)
    with TestClient(app) as client:
        defaults = client.get("/api/v1/settings", headers=headers(token)).json()["data"]["values"]
        defaults.update({"operation_mode": "report_only", "classification_source": "template"})
        response = client.post(
            "/api/v1/tasks",
            headers=headers(token, True),
            json={"name": "越界", "source_grant": "not-a-grant", "settings": defaults},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PATH_OUTSIDE_GRANT"


def test_model_delete_hides_connection_but_keeps_audit_record(project_root: Path, tmp_path: Path):
    token = "test-session"
    app = create_app(
        project_root=project_root,
        data_dir=tmp_path / "data",
        session_token=token,
        allow_typed_grants=True,
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/models",
            headers=headers(token, True),
            json={
                "name": "本地测试连接",
                "provider": "qwen_local",
                "runtime": "openai_compatible",
                "base_url": "http://127.0.0.1:8000/v1",
                "model_id": "qwen-test",
                "trust_scope": "loopback",
                "options": {"thinking_mode": "server_default", "timeout_seconds": 5, "max_concurrency": 1},
                "enabled": True,
            },
        ).json()["data"]
        deleted = client.request(
            "DELETE",
            f"/api/v1/models/{created['id']}",
            headers={**headers(token, True), "Idempotency-Key": "delete-model"},
            json={"expected_revision": created["revision"]},
        )
        assert deleted.status_code == 200 and deleted.json()["data"] == {"disabled": True}
        assert client.get("/api/v1/models", headers=headers(token)).json()["data"] == []
        with app.state.database.engine.connect() as connection:
            retained = connection.exec_driver_sql(
                "SELECT enabled,revision FROM model_profiles WHERE id=?", (created["id"],)
            ).first()
        assert retained == (0, created["revision"] + 1)
