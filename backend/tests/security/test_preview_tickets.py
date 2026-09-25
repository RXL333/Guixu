from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from guixu.api.app import create_app


TOKEN = "preview-session"


def headers(mutate: bool = False) -> dict[str, str]:
    result = {"X-Guixu-Session": TOKEN}
    if mutate:
        result["Idempotency-Key"] = "preview-ticket-request"
    return result


def test_preview_ticket_is_short_lived_file_scoped_range_capability(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    media = source / "pixel.png"; media.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(64)))
    unsafe = source / "active.html"; unsafe.write_text("<script>alert(1)</script>", encoding="utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
        settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
        settings.update({"operation_mode": "report_only", "scan_mode": "current_only", "classification_source":"auto_plan"})
        model = app.state.models.create({"name":"Preview AI","provider":"qwen_local","runtime":"openai_compatible",
            "base_url":"http://127.0.0.1:8000/v1","model_id":"fixture","trust_scope":"loopback",
            "options":{"thinking_mode":"disabled","timeout_seconds":5,"max_concurrency":1,"batch_size":20},"enabled":True})
        task = client.post("/api/v1/tasks", headers=headers(True), json={"name":"preview","source_grant":grant,
            "settings":settings,"model_profile_id":model["id"],"user_instructions":"按内容整理"}).json()["data"]
        app.state.tasks.start(task["id"], task["revision"])
        files = client.get(f"/api/v1/tasks/{task['id']}/files", headers=headers()).json()["data"]["items"]
        image_id = next(item["id"] for item in files if item["basename"] == "pixel.png")
        html_id = next(item["id"] for item in files if item["basename"] == "active.html")
        assert client.post(f"/api/v1/tasks/{task['id']}/files/{image_id}/preview-ticket").status_code == 401
        issued = client.post(f"/api/v1/tasks/{task['id']}/files/{image_id}/preview-ticket", headers=headers(True))
        assert issued.status_code == 201
        ticket = issued.json()["data"]["ticket"]
        ranged = client.get(f"/api/v1/previews/{ticket}", headers={"Range": "bytes=8-15"})
        assert ranged.status_code == 206 and ranged.content == bytes(range(8))
        assert ranged.headers["content-range"] == f"bytes 8-15/{media.stat().st_size}"
        assert ranged.headers["cache-control"] == "no-store" and ranged.headers["x-content-type-options"] == "nosniff"
        assert client.get("/api/v1/previews/not-a-ticket").status_code == 404
        blocked = client.post(f"/api/v1/tasks/{task['id']}/files/{html_id}/preview-ticket", headers={**headers(), "Idempotency-Key": "html-ticket"})
        assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "PREVIEW_UNSUPPORTED"
        media.write_bytes(media.read_bytes() + b"changed")
        assert client.get(f"/api/v1/previews/{ticket}").status_code == 409


def test_conversation_photo_preview_uses_bound_scope_before_analysis(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    image = source / "photo.jpg"; Image.new("RGB", (2, 2), "blue").save(image)
    outside = tmp_path / "outside.jpg"; outside.write_bytes(b"private")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=headers(), json={"scope_grant": grant}).json()["data"]
        endpoint = f"/api/v1/conversations/{conversation['id']}/preview-ticket"
        assert client.post(endpoint, json={"source_path": str(image)}).status_code == 401
        issued = client.post(endpoint, headers=headers(), json={"source_path": str(image)})
        assert issued.status_code == 201, issued.text
        streamed = client.get(issued.json()["data"]["url"])
        assert streamed.headers["content-type"] == "image/jpeg"
        assert streamed.content == image.read_bytes() and streamed.content.startswith(b"\xff\xd8")
        blocked = client.post(endpoint, headers=headers(), json={"source_path": str(outside)})
        assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "PREVIEW_OUTSIDE_SCOPE"
