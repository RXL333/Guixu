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


def model(app):
    return app.state.models.create({"name":"API AI","provider":"qwen_local","runtime":"openai_compatible",
        "base_url":"http://127.0.0.1:8000/v1","model_id":"fixture","trust_scope":"loopback",
        "options":{"thinking_mode":"disabled","timeout_seconds":5,"max_concurrency":1,"batch_size":20},"enabled":True})


def test_public_brand_assets_do_not_require_api_session(project_root: Path, tmp_path: Path):
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token="private",
                     allow_typed_grants=True)
    with TestClient(app) as client:
        for path in ("/app-icon.png", "/favicon.png"):
            response = client.get(path)
            assert response.status_code == (200 if (project_root / "frontend" / "dist" / path.lstrip("/")).exists() else 404)
        assert client.get("/api/v1/settings").status_code == 401
        assert client.get("/private.png").status_code == 401


def test_category_language_setting_persists_and_checks_revision(project_root: Path, tmp_path: Path):
    token = "test-session"
    data_dir = tmp_path / "data"
    app = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        original = client.get("/api/v1/settings", headers=headers(token)).json()["data"]
        assert original["values"]["category_language"] == "zh"
        changed = client.patch("/api/v1/settings/category-language", headers=headers(token),
                               json={"expected_revision": original["revision"], "category_language": "en"})
        assert changed.status_code == 200
        assert changed.json()["data"]["values"]["category_language"] == "en"
        stale = client.patch("/api/v1/settings/category-language", headers=headers(token),
                             json={"expected_revision": original["revision"], "category_language": "zh"})
        assert stale.status_code == 409
    reopened = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
                          allow_typed_grants=True)
    with TestClient(reopened) as client:
        assert client.get("/api/v1/settings", headers=headers(token)).json()["data"]["values"]["category_language"] == "en"


def test_authenticated_ai_only_read_scan_and_parse(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    sample = source / "说明.txt"; sample.write_text("计算机网络 TCP 笔记", encoding="utf-8")
    before = hashlib.sha256(sample.read_bytes()).hexdigest(); token = "test-session"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        assert client.get("/api/v1/settings").status_code == 401
        assert "/api/v1/templates" not in app.openapi()["paths"]
        grant = client.post("/api/v1/dev/grants", headers=headers(token),
            json={"path":str(source),"purpose":"source"}).json()["data"]["grant_id"]
        settings = client.get("/api/v1/settings", headers=headers(token)).json()["data"]["values"]
        settings.update({"operation_mode":"report_only","classification_source":"auto_plan",
                         "scan_mode":"current_only"})
        profile = model(app)
        create = client.post("/api/v1/tasks", headers=headers(token, True), json={
            "name":"API AI 只读扫描","source_grant":grant,"settings":settings,
            "model_profile_id":profile["id"],"user_instructions":"按课程内容整理"})
        assert create.status_code == 201, create.text
        task = create.json()["data"]
        app.state.tasks.start(task["id"], task["revision"])
        files = client.get(f"/api/v1/tasks/{task['id']}/files", headers=headers(token)).json()["data"]
        assert files["total"] == 1 and files["items"][0]["modality"] == "text"
        file_id = files["items"][0]["id"]
        current = app.state.repository.get(task["id"])
        parsed = client.post(f"/api/v1/tasks/{task['id']}/reanalyze", headers=headers(token, True),
            json={"expected_revision":current["revision"],"file_ids":[file_id]})
        assert parsed.status_code == 202
        detail = client.get(f"/api/v1/tasks/{task['id']}/files/{file_id}", headers=headers(token)).json()["data"]
        assert "TCP" in detail["profile"]["evidence"][0]["text"]
        assert hashlib.sha256(sample.read_bytes()).hexdigest() == before


def test_removed_rule_api_has_no_runtime_surface(project_root: Path, tmp_path: Path):
    token = "test-session"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        paths = set(app.openapi()["paths"])
        assert "/api/v1/rules" not in paths and "/api/v1/rules/test" not in paths


def test_path_outside_grant_cannot_create_task(project_root: Path, tmp_path: Path):
    token = "test-session"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        defaults = client.get("/api/v1/settings", headers=headers(token)).json()["data"]["values"]
        defaults.update({"operation_mode":"report_only","classification_source":"auto_plan"})
        profile = model(app)
        response = client.post("/api/v1/tasks", headers=headers(token, True), json={
            "name":"越界","source_grant":"not-a-grant","settings":defaults,"model_profile_id":profile["id"]})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PATH_OUTSIDE_GRANT"


def test_model_delete_hides_connection_but_keeps_audit_record(project_root: Path, tmp_path: Path):
    token = "test-session"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        created = client.post("/api/v1/models", headers=headers(token, True), json={
            "name":"本地测试连接","provider":"qwen_local","runtime":"openai_compatible",
            "base_url":"http://127.0.0.1:8000/v1","model_id":"qwen-test","trust_scope":"loopback",
            "options":{"thinking_mode":"server_default","timeout_seconds":5,"max_concurrency":1,"batch_size":20},
            "enabled":True}).json()["data"]
        deleted = client.request("DELETE", f"/api/v1/models/{created['id']}",
            headers={**headers(token, True),"Idempotency-Key":"delete-model"},
            json={"expected_revision":created["revision"]})
        assert deleted.status_code == 200 and deleted.json()["data"] == {"disabled":True}
        assert client.get("/api/v1/models", headers=headers(token)).json()["data"] == []
        with app.state.database.engine.connect() as connection:
            retained = connection.exec_driver_sql(
                "SELECT enabled,revision FROM model_profiles WHERE id=?", (created["id"],)).first()
        assert retained == (0, created["revision"] + 1)


def test_conversation_model_selection_updates_conversation_and_context(project_root: Path, tmp_path: Path):
    token = "conversation-model-selection"
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(token), json={
            "path": str(source), "purpose": "source",
        }).json()["data"]["grant_id"]
        first = model(app)
        second = app.state.models.create({"name": "API AI 2", "provider": "qwen_local", "runtime": "openai_compatible",
            "base_url": "http://127.0.0.1:8000/v1", "model_id": "fixture-2", "trust_scope": "loopback",
            "options": {"thinking_mode": "disabled", "timeout_seconds": 5, "max_concurrency": 1, "batch_size": 20},
            "enabled": True})
        created = client.post("/api/v1/conversations", headers=headers(token, True), json={
            "title": "模型选择", "model_profile_id": first["id"], "scope_grant": grant,
        })
        assert created.status_code == 201, created.text
        conversation_id = created.json()["data"]["id"]

        switched = client.patch(f"/api/v1/conversations/{conversation_id}", headers=headers(token), json={
            "model_profile_id": second["id"],
        })
        assert switched.status_code == 200, switched.text
        payload = switched.json()["data"]
        assert payload["model_profile_id"] == second["id"]
        assert payload["context"]["model_profile_id"] == second["id"]

        context = client.get(f"/api/v1/conversations/{conversation_id}/context", headers=headers(token))
        assert context.status_code == 200
        assert context.json()["data"]["model_profile_id"] == second["id"]


def test_conversation_message_file_reference_api_is_batched_and_scope_safe(project_root: Path, tmp_path: Path):
    source = tmp_path / "references"; source.mkdir()
    (source / "a.txt").write_text("alpha", encoding="utf-8")
    token = "reference-session"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(token),
                            json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
        settings = client.get("/api/v1/settings", headers=headers(token)).json()["data"]["values"]
        settings.update({"operation_mode": "report_only", "classification_source": "auto_plan", "scan_mode": "current_only"})
        profile = model(app)
        created = client.post("/api/v1/tasks", headers=headers(token, True), json={
            "name": "reference source", "source_grant": grant, "settings": settings,
            "model_profile_id": profile["id"], "user_instructions": "test",
        }).json()["data"]
        app.state.tasks.start(created["id"], created["revision"])
        file_id = app.state.repository.list_files(created["id"], 10, 0)[0][0]["id"]
        conversation = client.post("/api/v1/conversations", headers=headers(token, True), json={
            "title": "reference", "model_profile_id": profile["id"], "scope_grant": grant,
        }).json()["data"]
        attached = client.post(f"/api/v1/conversations/{conversation['id']}/files", headers=headers(token),
                               json={"file_id": file_id})
        assert attached.status_code == 201
        context = client.get(f"/api/v1/conversations/{conversation['id']}/context", headers=headers(token)).json()["data"]
        saved = client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=headers(token), json={
            "role": "USER", "content": "这些先别动", "selected_file_ids": [file_id],
            "expected_context_revision": context["context_revision"],
        })
        assert saved.status_code == 201, saved.text
        payload = saved.json()["data"]
        assert payload["referenced_file_ids"] == [file_id] and payload["reference_source"] == "UI_SELECTION"
        history = client.get(f"/api/v1/conversations/{conversation['id']}/messages", headers=headers(token)).json()["data"]
        assert history[0]["file_references"][0]["file_id"] == file_id

        other = client.post("/api/v1/conversations", headers={**headers(token), "Idempotency-Key": "other-conversation"}, json={
            "title": "other", "model_profile_id": profile["id"], "scope_grant": grant,
        }).json()["data"]
        violated = client.post(f"/api/v1/conversations/{other['id']}/messages", headers=headers(token), json={
            "role": "USER", "content": "这些", "selected_file_ids": [file_id],
        })
        assert violated.status_code == 409 and violated.json()["error"]["code"] == "REFERENCE_SCOPE_VIOLATION"
        ambiguous = client.post(f"/api/v1/conversations/{other['id']}/messages", headers=headers(token), json={
            "role": "USER", "content": "这些都放旅行",
        })
        assert ambiguous.status_code == 409 and ambiguous.json()["error"]["code"] == "REFERENCE_AMBIGUOUS"
