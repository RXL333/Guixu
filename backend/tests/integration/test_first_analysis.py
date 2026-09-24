from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from guixu.api.app import create_app
from guixu.application.models import unknown_capabilities


class FakeAnalysisGateway:
    def __init__(self) -> None:
        self.seen_profiles = []

    def plan_taxonomy(self, **kwargs):
        self.seen_profiles.extend(profile for profile, _ in kwargs["profiles"])
        return {"categories": [{
            "category_id": "topic.network", "name": "网络资料",
            "description": "TCP、IP 与网络课程材料", "selection_criteria": "正文包含 TCP 或 IP",
        }]}

    def classify_batch(self, **kwargs):
        return [{
            "file_id": profile.file_id, "taxonomy_id": kwargs["taxonomy"]["taxonomy_id"],
            "category_id": "topic.network", "abstain": False, "model_score": 0.98,
            "evidence_ids": [profile.evidence[0].id], "reason": "内容证据匹配",
            "tags": [], "warnings": [],
        } for profile, _ in kwargs["items"]]


def _headers(token: str) -> dict[str, str]:
    return {"X-Guixu-Session": token}


def _prepare_model(app):
    model = app.state.models.create({
        "name": "Fixture AI", "provider": "qwen_local", "runtime": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1", "model_id": "fixture",
        "trust_scope": "loopback", "options": {"thinking_mode": "disabled", "timeout_seconds": 5,
        "max_concurrency": 1, "batch_size": 20}, "enabled": True,
    })
    caps = unknown_capabilities()
    for key in ("reachable", "authentication", "text", "json_mode"):
        caps[key].update({"status": "supported", "verified": True})
    app.state.models._save_capabilities(model["id"], caps)
    return model


def test_first_turn_scans_real_evidence_and_only_creates_full_preview(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    sample = source / "network-notes.txt"
    sample.write_text("TCP 三次握手、IP 路由与 Wireshark 课程笔记", encoding="utf-8")
    before_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
    token = "first-analysis"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    model = _prepare_model(app)
    fake = FakeAnalysisGateway()
    app.state.ai_planner.gateway = fake
    app.state.ai_classifier.gateway = fake

    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=_headers(token), json={
            "path": str(source), "purpose": "source",
        }).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=_headers(token), json={
            "title": "首次分析", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        response = client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                               headers=_headers(token), json={
                                   "content": "帮我按照内容整理这些文件，不要分得太细。", "acknowledge_privacy": True,
                               })
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        assert result["plan_version"]["version_number"] == 1
        assert result["plan_version"]["plan_kind"] == "FULL"
        assert result["plan_version"]["baseline_execution_round_id"] is None
        assert result["metrics"]["file_count"] == 1
        assert result["disk_files_changed"] is False
        assert result["assistant_message"]["message_type"] == "PLAN_PROPOSAL"
        assert not app.state.conversations.list_execution_rounds(conversation["id"])
        assert fake.seen_profiles and "TCP" in " ".join(item.text for item in fake.seen_profiles[0].evidence)
        assert hashlib.sha256(sample.read_bytes()).hexdigest() == before_hash
        assert sample.exists()


def test_first_plan_can_be_explicitly_approved_and_executed(project_root: Path, tmp_path: Path):
    """The first FULL plan is preview-only until the user explicitly approves it."""
    source = tmp_path / "source"
    source.mkdir()
    sample = source / "network-notes.txt"
    sample.write_text("TCP 三次握手、IP 路由与 Wireshark 课程笔记", encoding="utf-8")
    token = "first-analysis-execute"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    model = _prepare_model(app)
    fake = FakeAnalysisGateway()
    app.state.ai_planner.gateway = fake
    app.state.ai_classifier.gateway = fake

    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=_headers(token), json={
            "path": str(source), "purpose": "source",
        }).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=_headers(token), json={
            "title": "首次执行", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        result = client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                             headers=_headers(token), json={
                                 "content": "帮我按照内容整理这些文件，不要分得太细。", "acknowledge_privacy": True,
                             }).json()["data"]
        plan = result["plan_version"]
        revision = result["context"]["context_revision"]
        assert plan["plan_kind"] == "FULL"
        assert plan["baseline_execution_round_id"] is None
        assert not list(source.glob("网络资料/*"))

        approved = client.post(
            f"/api/v1/conversations/{conversation['id']}/plan-versions/{plan['id']}/approve",
            headers=_headers(token), json={
                "expected_context_revision": revision,
                "plan_hash": plan["plan_hash"],
                "authorization": {"kind": "interactive", "surface": "conversation_workspace"},
            },
        )
        assert approved.status_code == 200, approved.text
        executed = client.post(
            f"/api/v1/conversations/{conversation['id']}/plan-versions/{plan['id']}/execute",
            headers=_headers(token), json={
                "expected_context_revision": revision,
                "plan_hash": plan["plan_hash"],
            },
        )
        assert executed.status_code == 200, executed.text
        assert not sample.exists()
        assert list(source.rglob("network-notes.txt"))
        assert app.state.conversations.list_execution_rounds(conversation["id"])[0]["status"] == "COMPLETED"


def test_first_turn_requires_conversation_scope(project_root: Path, tmp_path: Path):
    token = "first-analysis-scope"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    model = _prepare_model(app)
    conversation = app.state.conversations.create_conversation(title="无目录", model_profile_id=model["id"])
    with TestClient(app) as client:
        response = client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                               headers=_headers(token), json={
                                   "content": "按内容整理", "acknowledge_privacy": True,
                               })
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FIRST_ANALYSIS_SCOPE_REQUIRED"
