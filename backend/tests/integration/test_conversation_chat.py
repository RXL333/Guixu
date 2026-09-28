from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from guixu.api.app import create_app
from guixu.application.models import unknown_capabilities
from guixu.infrastructure.models.transport import ModelResponse


def _headers(token: str) -> dict[str, str]:
    return {"X-Guixu-Session": token}


def test_chat_is_multiturn_and_does_not_start_organization(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "first.jpg").write_bytes(b"photo-one")
    (source / "second.jpg").write_bytes(b"photo-two")
    token = "chat-test"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    model = app.state.models.create({
        "name": "Text fixture", "provider": "qwen_local", "runtime": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1", "model_id": "fixture",
        "trust_scope": "loopback", "options": {"timeout_seconds": 5}, "enabled": True,
    })
    capabilities = unknown_capabilities()
    capabilities["text"].update({"status": "supported", "verified": True})
    app.state.models._save_capabilities(model["id"], capabilities)
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs["messages"])
        return ModelResponse(content="可以按场景分类，文件夹用中文。", input_tokens=12,
                             output_tokens=12, latency_ms=1, request_hash="fake", attempts=1)

    app.state.models.transport.chat = fake_chat
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=_headers(token),
                            json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=_headers(token), json={
            "title": "讨论照片", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        conversation_id = conversation["id"]
        inventory = client.get(f"/api/v1/conversations/{conversation_id}/source-files", headers=_headers(token))
        assert inventory.status_code == 200
        assert len(inventory.json()["data"]["files"]) == 2
        page = client.get(f"/api/v1/conversations/{conversation_id}/source-files?limit=1",
                          headers=_headers(token)).json()["data"]
        assert len(page["files"]) == 1 and page["truncated"] is True
        next_page = client.get(f"/api/v1/conversations/{conversation_id}/source-files?limit=1&offset=1",
                               headers=_headers(token)).json()["data"]
        assert len(next_page["files"]) == 1 and next_page["truncated"] is False
        assert page["files"][0]["path"] != next_page["files"][0]["path"]
        searched = client.get(f"/api/v1/conversations/{conversation_id}/source-files?q=second",
                              headers=_headers(token)).json()["data"]
        assert [Path(item["path"]).name for item in searched["files"]] == ["second.jpg"]
        recovery = client.get(f"/api/v1/conversations/{conversation_id}/recovery-status?reconcile=true",
                              headers=_headers(token))
        assert recovery.status_code == 200
        assert recovery.json()["data"]["reconciliation"]["new_files"] == 0
        assert recovery.json()["data"]["reconciliation"]["requires_user_action"] is False

        for user_text in ("你好", "文件夹名称用中文，可以吗？"):
            response = client.post(f"/api/v1/conversations/{conversation_id}/chat", headers=_headers(token),
                                   json={"content": user_text})
            assert response.status_code == 200, response.text
            assert response.json()["data"]["assistant_message"]["content"] == "可以按场景分类，文件夹用中文。"
        assert len(calls) == 2
        assert any(item["content"] == "你好" for item in calls[1])
        assert any(item["role"] == "assistant" for item in calls[1])
        assert app.state.conversations.list_plan_versions(conversation_id) == []
        assert app.state.conversations.list_execution_rounds(conversation_id) == []
        assert (source / "first.jpg").read_bytes() == b"photo-one"
        assert (source / "second.jpg").read_bytes() == b"photo-two"


def test_selected_image_chat_requires_consent_and_stays_inside_scope(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    image = source / "selected.jpg"
    Image.new("RGB", (1200, 800), "blue").save(image)
    outside = tmp_path / "private.jpg"
    Image.new("RGB", (8, 8), "red").save(outside)
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token="visual-chat",
                     allow_typed_grants=True)
    model = app.state.models.create({
        "name": "Vision fixture", "provider": "qwen_local", "runtime": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1", "model_id": "fixture",
        "trust_scope": "loopback", "options": {"timeout_seconds": 5}, "enabled": True,
    })
    capabilities = unknown_capabilities()
    for key in ("text", "vision"):
        capabilities[key].update({"status": "supported", "verified": True})
    app.state.models._save_capabilities(model["id"], capabilities)
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs["messages"])
        return ModelResponse(content="这张照片以蓝色为主。", input_tokens=12,
                             output_tokens=12, latency_ms=1, request_hash="fake", attempts=1)

    app.state.models.transport.chat = fake_chat
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=_headers("visual-chat"),
                            json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=_headers("visual-chat"), json={
            "title": "讨论图片", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        url = f"/api/v1/conversations/{conversation['id']}/chat"
        payload = {"content": "这张图是什么？", "selected_source_paths": [str(image)]}
        denied = client.post(url, headers=_headers("visual-chat"), json=payload)
        assert denied.status_code == 409 and denied.json()["error"]["code"] == "CHAT_IMAGE_CONSENT_REQUIRED"
        assert calls == []
        escaped = client.post(url, headers=_headers("visual-chat"), json={
            **payload, "selected_source_paths": [str(outside)], "acknowledge_image_content": True,
        })
        assert escaped.status_code == 409 and escaped.json()["error"]["code"] == "CHAT_IMAGE_OUTSIDE_SCOPE"
        assert calls == []
        accepted = client.post(url, headers=_headers("visual-chat"), json={**payload, "acknowledge_image_content": True})
        assert accepted.status_code == 200, accepted.text
        parts = calls[0][-1]["content"]
        assert parts[0]["type"] == "text"
        assert parts[-1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert len(parts[-1]["image_url"]["url"]) < 1_000_000
        assert app.state.conversations.list_plan_versions(conversation["id"]) == []
        assert image.is_file() and outside.is_file()
