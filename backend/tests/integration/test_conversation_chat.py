from pathlib import Path

from fastapi.testclient import TestClient

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
