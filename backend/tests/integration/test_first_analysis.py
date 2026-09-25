from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import text

from guixu.api.app import create_app
from guixu.domain.profiles import Coverage, Evidence, EvidenceLocator, FileProfile, ParseOutcome
from guixu.domain.settings import TaskSettings
from guixu.application.models import unknown_capabilities
from guixu.application.models import ModelError
from guixu.application.pre_execution_replan_guard import begin_pre_execution_replan
from guixu.infrastructure.models.transport import ModelTransportError


class FakeAnalysisGateway:
    def __init__(self) -> None:
        self.seen_profiles = []
        self.classification_batches = []
        self.vision_batches = []

    def plan_taxonomy(self, **kwargs):
        self.seen_profiles.extend(profile for profile, _ in kwargs["profiles"])
        return {"categories": [{
            "category_id": "topic.network", "name": "网络资料",
            "description": "TCP、IP 与网络课程材料", "selection_criteria": "正文包含 TCP 或 IP",
        }]}

    def classify_batch(self, **kwargs):
        self.classification_batches.append([profile.file_id for profile, _ in kwargs["items"]])
        self.vision_batches.append(set(kwargs.get("vision_refresh_file_ids") or set()))
        return [{
            "file_id": profile.file_id, "taxonomy_id": kwargs["taxonomy"]["taxonomy_id"],
            "category_id": "topic.network", "abstain": False, "model_score": 0.98,
            "evidence_ids": [profile.evidence[0].id], "reason": "内容证据匹配",
            "visual_description": "照片中有街道、建筑和树木。" if profile.modality == "image" else None,
            "tags": [], "warnings": [],
        } for profile, _ in kwargs["items"]]


def _headers(token: str) -> dict[str, str]:
    return {"X-Guixu-Session": token}


def _prepare_model(app, *, vision: bool = False):
    model = app.state.models.create({
        "name": "Fixture AI", "provider": "qwen_local", "runtime": "openai_compatible",
        "base_url": "http://127.0.0.1:8000/v1", "model_id": "fixture",
        "trust_scope": "loopback", "options": {"thinking_mode": "disabled", "timeout_seconds": 5,
        "max_concurrency": 1, "batch_size": 20}, "enabled": True,
    })
    caps = unknown_capabilities()
    for key in ("reachable", "authentication", "text", "json_mode"):
        caps[key].update({"status": "supported", "verified": True})
    if vision:
        caps["vision"].update({"status": "supported", "verified": True, "vision": True, "vision_verified": True})
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


def test_first_plan_can_be_explicitly_approved_and_executed(project_root: Path, tmp_path: Path, monkeypatch):
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
        from guixu.infrastructure.filesystem.executor import FileOperationExecutor
        real_execute = FileOperationExecutor.execute

        def fail_before_operations(self, plan, approved_hash):
            raise ValueError("INJECTED_PRE_OPERATION_FAILURE")

        monkeypatch.setattr(FileOperationExecutor, "execute", fail_before_operations)
        failed = client.post(
            f"/api/v1/conversations/{conversation['id']}/plan-versions/{plan['id']}/execute",
            headers=_headers(token), json={"expected_context_revision": revision, "plan_hash": plan["plan_hash"]},
        )
        assert failed.status_code == 409
        assert sample.exists()
        monkeypatch.setattr(FileOperationExecutor, "execute", real_execute)
        revision = app.state.conversations.get_context(conversation["id"])["context_revision"]
        retried_approval = client.post(
            f"/api/v1/conversations/{conversation['id']}/plan-versions/{plan['id']}/approve",
            headers=_headers(token), json={
                "expected_context_revision": revision, "plan_hash": plan["plan_hash"],
                "authorization": {"kind": "interactive", "surface": "conversation_workspace"},
            },
        )
        assert retried_approval.status_code == 200, retried_approval.text
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


def test_first_plan_can_be_revised_to_v2_before_any_execution(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    sample = source / "network-notes.txt"
    sample.write_text("TCP 三次握手、IP 路由与 Wireshark 课程笔记", encoding="utf-8")
    before_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
    token = "first-analysis-revise"
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
            "title": "首次方案调整", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        first = client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                            headers=_headers(token), json={
                                "content": "按内容整理", "acknowledge_privacy": True,
                            }).json()["data"]
        message = client.post(f"/api/v1/conversations/{conversation['id']}/messages",
                              headers=_headers(token), json={
                                  "role": "USER", "content": "网络课程资料单独归类",
                                  "expected_context_revision": first["context"]["context_revision"],
                              }).json()["data"]
        revised_response = client.post(
            f"/api/v1/conversations/{conversation['id']}/refinements/prepare",
            headers=_headers(token), json={
                "user_message": "网络课程资料单独归类", "trigger_message_id": message["id"],
            },
        )
        assert revised_response.status_code == 200, revised_response.text
        revised = revised_response.json()["data"]
        assert revised["intent"] == "PRE_EXECUTION_REPLAN"
        assert revised["plan_version"]["version_number"] == 2
        assert revised["plan_version"]["parent_plan_version_id"] == first["plan_version"]["id"]
        assert revised["plan_version"]["plan_kind"] == "FULL"
        assert revised["plan_version"]["baseline_execution_round_id"] is None
        versions = app.state.conversations.list_plan_versions(conversation["id"])
        assert [item["status"] for item in versions] == ["SUPERSEDED", "PROPOSED"]
        assert not app.state.conversations.list_execution_rounds(conversation["id"])
        assert hashlib.sha256(sample.read_bytes()).hexdigest() == before_hash
        assert sample.exists()


@pytest.mark.parametrize("failed_stage", ["planning", "classification", "compile_commit"])
def test_failed_pre_execution_replan_preserves_approvable_v1(
    project_root: Path, tmp_path: Path, failed_stage: str,
):
    source = tmp_path / "source"
    source.mkdir()
    sample = source / "network-notes.txt"
    sample.write_text("TCP 网络课程笔记", encoding="utf-8")
    token = "first-analysis-revise-failure"
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
            "title": "失败重规划", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        conversation_id = conversation["id"]
        first = client.post(f"/api/v1/conversations/{conversation_id}/turns",
                            headers=_headers(token), json={
                                "content": "按内容整理", "acknowledge_privacy": True,
                            }).json()["data"]
        v1 = first["plan_version"]
        before_task = app.state.repository.get(first["task"]["id"])

    def reject_stage(**_kwargs):
        raise ModelError("INJECTED_REPLAN_FAILURE")

    if failed_stage == "planning":
        fake.plan_taxonomy = reject_stage
    elif failed_stage == "classification":
        fake.classify_batch = reject_stage
    else:
        compile_plan = app.state.operations.compile

        def compile_then_fail(*args, **kwargs):
            compile_plan(*args, **kwargs)
            raise ModelError("INJECTED_REPLAN_FAILURE_AFTER_COMPILE")

        # Exercise compensation after the new core Plan has been persisted but
        # before its Conversation PlanVersion can become current.
        app.state.operations.compile = compile_then_fail
        failed = client.post(f"/api/v1/conversations/{conversation_id}/refinements/prepare",
                             headers=_headers(token), json={"user_message": "网络课程单独归类"})
        assert failed.status_code == 409, failed.text
        assert app.state.conversations.get_current_plan_version(conversation_id)["id"] == v1["id"]
        after_task = app.state.repository.get(before_task["id"])
        assert after_task["revision"] == before_task["revision"]
        assert after_task["status"] == before_task["status"]
        assert after_task["classification_request"] == before_task["classification_request"]
        assert app.state.operations.journal.plan_metadata(v1["plan_id"])["status"] == "validated"

        revision = app.state.conversations.get_context(conversation_id)["context_revision"]
        approved = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v1['id']}/approve",
            headers=_headers(token), json={
                "expected_context_revision": revision,
                "plan_hash": v1["plan_hash"],
                "authorization": {"kind": "interactive", "surface": "conversation_workspace"},
            },
        )
        assert approved.status_code == 200, approved.text
        executed = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v1['id']}/execute",
            headers=_headers(token), json={"expected_context_revision": revision, "plan_hash": v1["plan_hash"]},
        )
        assert executed.status_code == 200, executed.text
        assert not sample.exists()


def test_interrupted_pre_execution_replan_restores_v1_on_restart(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "network-notes.txt").write_text("TCP 网络课程笔记", encoding="utf-8")
    data_dir = tmp_path / "data"
    token = "first-analysis-replan-restart"
    app = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
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
            "title": "异常退出恢复", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        first = client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                            headers=_headers(token), json={
                                "content": "按内容整理", "acknowledge_privacy": True,
                            }).json()["data"]
    task_id = first["task"]["id"]
    v1 = first["plan_version"]
    task_before = app.state.repository.get(task_id)
    turn_id = begin_pre_execution_replan(app.state.database, conversation["id"], task_id, v1["id"])
    with app.state.database.begin() as connection:
        connection.execute(text("UPDATE tasks SET revision=revision+1,status='AWAITING_TAXONOMY_APPROVAL' WHERE id=:id"),
                           {"id": task_id})
        connection.execute(text("UPDATE plans SET status='superseded' WHERE id=:id"), {"id": v1["plan_id"]})
    app.state.database.close()

    restarted = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
                           allow_typed_grants=True)
    assert restarted.state.repository.get(task_id)["revision"] == task_before["revision"]
    assert restarted.state.repository.get(task_id)["status"] == task_before["status"]
    assert restarted.state.operations.journal.plan_metadata(v1["plan_id"])["status"] == "validated"
    with restarted.state.database.engine.connect() as connection:
        status = connection.execute(text("SELECT status FROM conversation_agent_turns WHERE id=:id"),
                                    {"id": turn_id}).scalar_one()
    assert status == "INTERRUPTED"
    restarted.state.database.close()


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


def test_conversation_file_api_rejects_file_outside_authorized_folder(project_root: Path, tmp_path: Path):
    authorized = tmp_path / "authorized"
    foreign = tmp_path / "foreign"
    authorized.mkdir()
    foreign.mkdir()
    (foreign / "private.txt").write_text("foreign conversation content", encoding="utf-8")
    token = "conversation-file-scope-api"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    model = _prepare_model(app)

    with TestClient(app) as client:
        authorized_grant = client.post("/api/v1/dev/grants", headers=_headers(token), json={
            "path": str(authorized), "purpose": "source",
        }).json()["data"]["grant_id"]
        foreign_grant = client.post("/api/v1/dev/grants", headers=_headers(token), json={
            "path": str(foreign), "purpose": "source",
        }).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=_headers(token), json={
            "title": "授权目录隔离", "model_profile_id": model["id"], "scope_grant": authorized_grant,
        }).json()["data"]
        foreign_task = app.state.tasks.create_task(
            "foreign task", foreign_grant, None, TaskSettings(operation_mode="report_only"), {},
            model["id"], model,
        )
        app.state.tasks.start(foreign_task["id"], foreign_task["revision"])
        foreign_files, foreign_count = app.state.repository.list_files(foreign_task["id"], limit=10)
        assert foreign_count == 1

        response = client.post(f"/api/v1/conversations/{conversation['id']}/files", headers=_headers(token),
                               json={"file_id": foreign_files[0]["id"]})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "REFERENCE_SCOPE_VIOLATION"
        visible = client.get(f"/api/v1/conversations/{conversation['id']}/files", headers=_headers(token))
        assert visible.status_code == 200
        assert visible.json()["data"] == []


def test_first_turn_model_contract_failure_settles_task(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "notes.txt").write_text("TCP 网络课程笔记", encoding="utf-8")
    token = "first-analysis-model-error"
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=token,
                     allow_typed_grants=True)
    model = _prepare_model(app)
    fake = FakeAnalysisGateway()

    def reject_taxonomy(**_kwargs):
        raise ModelTransportError("PLANNER_SCHEMA_INVALID", provider_code="CATEGORY_PATH_UNSAFE")

    fake.plan_taxonomy = reject_taxonomy
    app.state.ai_planner.gateway = fake
    app.state.ai_classifier.gateway = fake
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=_headers(token), json={
            "path": str(source), "purpose": "source",
        }).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=_headers(token), json={
            "title": "模型契约失败", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        response = client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                               headers=_headers(token), json={
                                   "content": "按内容整理", "acknowledge_privacy": True,
                               })
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PLANNER_SCHEMA_INVALID"
        assert response.json()["error"]["details"] == {"validation_reason": "CATEGORY_PATH_UNSAFE"}
        tasks = app.state.repository.list("all")
        assert len(tasks) == 1
        task = app.state.repository.get(tasks[0]["id"])
        assert task["status"] == "FAILED"
        assert task["last_error_code"] == "PLANNER_SCHEMA_INVALID"
        assert not app.state.conversations.list_plan_versions(conversation["id"])


def test_visual_classification_reuses_persisted_result_after_restart(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (24, 24), (40, 120, 180)).save(source / "photo.jpg", format="JPEG")
    data_dir = tmp_path / "data"
    token = "first-analysis-visual-cache-restart"
    app = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
                     allow_typed_grants=True)
    model = _prepare_model(app, vision=True)
    initial_gateway = FakeAnalysisGateway()
    app.state.ai_planner.gateway = initial_gateway
    app.state.ai_classifier.gateway = initial_gateway
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=_headers(token), json={
            "path": str(source), "purpose": "source",
        }).json()["data"]["grant_id"]
        conversation = client.post("/api/v1/conversations", headers=_headers(token), json={
            "title": "视觉缓存恢复", "model_profile_id": model["id"], "scope_grant": grant,
        }).json()["data"]
        response = client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                               headers=_headers(token), json={
                                   "content": "按照片内容整理", "acknowledge_privacy": True,
                               })
        assert response.status_code == 200, response.text
        task_id = response.json()["data"]["task"]["id"]
        taxonomy_id = response.json()["data"]["plan_version"]["taxonomy_id"]
        assert len(initial_gateway.classification_batches) == 1
    app.state.database.close()

    restarted = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
                           allow_typed_grants=True)
    retry_gateway = FakeAnalysisGateway()
    restarted.state.ai_classifier.gateway = retry_gateway
    taxonomy = restarted.state.taxonomies.get(task_id, taxonomy_id)
    results = restarted.state.ai_classifier.classify_taxonomy(task_id, taxonomy)
    assert len(results) == 1
    assert results[0]["source"] == "cache"
    assert retry_gateway.classification_batches == []
    restarted.state.database.close()


def test_first_analysis_vision_crash_after_31_resumes_only_19_after_restart(
    project_root: Path, tmp_path: Path,
):
    source = tmp_path / "source"
    source.mkdir()
    for index in range(50):
        Image.new("RGB", (24, 24), ((index * 37) % 255, (index * 73) % 255, (index * 109) % 255)).save(
            source / f"photo-{index:02}.jpg", format="JPEG"
        )
    disk_before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.iterdir()}
    data_dir = tmp_path / "data"
    token = "first-analysis-vision-crash"
    app = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
                     allow_typed_grants=True)
    model = _prepare_model(app, vision=True)
    planner_gateway = FakeAnalysisGateway()
    app.state.ai_planner.gateway = planner_gateway
    app.state.ai_classifier.gateway = planner_gateway

    def parser_fixture(path: Path, file_id: str, preset: str = "standard", cancel_event=None):
        profile = FileProfile(
            file_id=file_id,
            modality="image",
            metadata={"format": "JPEG"},
            evidence=[Evidence(id=f"meta-{file_id}", kind="metadata", text="JPEG image",
                               locator=EvidenceLocator(), quality="high", origin="test-parser")],
            coverage=Coverage(mode="full"),
            parser_version="phase-n-crash-fixture",
        )
        return ParseOutcome(status="ready", profile=profile, cache_artifacts=[str(path)])

    app.state.parsing.runner.parse = parser_fixture
    with TestClient(app) as client:
        grant_response = client.post("/api/v1/dev/grants", headers=_headers(token), json={
            "path": str(source), "purpose": "source",
        })
        assert grant_response.status_code == 200, grant_response.text
        conversation_response = client.post("/api/v1/conversations", headers=_headers(token), json={
            "title": "分析崩溃恢复", "model_profile_id": model["id"],
            "scope_grant": grant_response.json()["data"]["grant_id"],
        })
        assert conversation_response.status_code == 201, conversation_response.text
        conversation_id = conversation_response.json()["data"]["id"]
        message = app.state.conversations.append_message(conversation_id, "USER", "按照片内容整理")

        def stop_before_vision(*_args, **_kwargs):
            raise RuntimeError("TEST_SETUP_BEFORE_CRASH_PROCESS")

        app.state.ai_classifier.classify_taxonomy = stop_before_vision
        with pytest.raises(RuntimeError, match="TEST_SETUP_BEFORE_CRASH_PROCESS"):
            app.state.first_analysis.run(
                conversation_id, user_message="按照片内容整理", message_id=message["id"],
                acknowledge_privacy=True,
            )
        with app.state.database.engine.connect() as connection:
            task_id = connection.execute(text(
                "SELECT id FROM tasks WHERE conversation_id=:conversation ORDER BY created_at DESC LIMIT 1"
            ), {"conversation": conversation_id}).scalar_one()
            taxonomy_id = connection.execute(text(
                "SELECT id FROM taxonomies WHERE task_id=:task AND status='approved' LIMIT 1"
            ), {"task": task_id}).scalar_one()
            assert connection.execute(text(
                "SELECT count(*) FROM files WHERE task_id=:task AND scan_status='eligible'"
            ), {"task": task_id}).scalar_one() == 50
    app.state.database.close()

    helper = project_root / "backend" / "tests" / "helpers" / "crash_first_analysis.py"
    crashed = subprocess.run(
        [sys.executable, str(helper), str(project_root), str(data_dir), task_id, taxonomy_id, "31"],
        cwd=project_root / "backend", check=False, timeout=60,
    )
    assert crashed.returncode == 91

    restarted = create_app(project_root=project_root, data_dir=data_dir, session_token=token,
                           allow_typed_grants=True)
    retry_gateway = FakeAnalysisGateway()
    restarted.state.ai_classifier.gateway = retry_gateway

    def parser_cache_hit(path: Path, file_id: str, preset: str = "standard", cancel_event=None):
        profile = FileProfile(
            file_id=file_id,
            modality="image",
            metadata={"format": "JPEG"},
            evidence=[Evidence(id=f"meta-{file_id}", kind="metadata", text="JPEG image",
                               locator=EvidenceLocator(), quality="high", origin="test-parser")],
            coverage=Coverage(mode="full"),
            parser_version="phase-n-crash-fixture",
        )
        return ParseOutcome(status="ready", profile=profile, cache_artifacts=[str(path)])

    restarted.state.parsing.runner.parse = parser_cache_hit
    with restarted.state.database.engine.connect() as connection:
        completed_before = {
            str(row[0]) for row in connection.execute(text(
                "SELECT file_id FROM classifications WHERE task_id=:task AND taxonomy_id=:taxonomy"
            ), {"task": task_id, "taxonomy": taxonomy_id})
        }
        visual_file_ids_before = {
            str(row[0]) for row in connection.execute(text(
                "SELECT DISTINCT file_id FROM file_evidence WHERE evidence_kind='VISUAL_DESCRIPTION' AND state='VALID' "
                "AND file_id IN (SELECT id FROM files WHERE task_id=:task)"
            ), {"task": task_id})
        }
    assert len(visual_file_ids_before) == 31
    assert len(completed_before) == 28
    all_file_ids = set(restarted.state.repository.eligible_file_ids(
        task_id, restarted.state.repository.list_scopes(task_id)[0]["id"]
    ))
    remaining_classification_ids = all_file_ids - completed_before
    remaining_vision_ids = all_file_ids - visual_file_ids_before
    assert len(remaining_classification_ids) == 22
    assert len(remaining_vision_ids) == 19

    with TestClient(restarted) as client:
        resumed = client.post(
            f"/api/v1/tasks/{task_id}/taxonomies/{taxonomy_id}/classify",
            headers={**_headers(token), "Idempotency-Key": "analysis-resume-31-50"},
        )
        assert resumed.status_code == 202, resumed.text
    requested_ids = [file_id for batch in retry_gateway.classification_batches for file_id in batch]
    refreshed_vision_ids = set().union(*retry_gateway.vision_batches) if retry_gateway.vision_batches else set()
    assert set(requested_ids) == remaining_classification_ids
    assert len(requested_ids) == 22
    assert refreshed_vision_ids == remaining_vision_ids
    assert refreshed_vision_ids.isdisjoint(visual_file_ids_before)
    recovered_plan = restarted.state.conversations.get_current_plan_version(conversation_id)
    assert recovered_plan["version_number"] == 1
    assert recovered_plan["status"] == "PROPOSED"
    assert recovered_plan["created_by_message_id"] == message["id"]
    assert restarted.state.conversations.get_context(conversation_id)["current_plan_version_id"] == recovered_plan["id"]
    recovered_messages = restarted.state.conversations.list_messages(conversation_id)
    assert any(item.get("referenced_plan_version_id") == recovered_plan["id"]
               and item.get("message_type") == "PLAN_PROPOSAL" for item in recovered_messages)
    with restarted.state.database.engine.connect() as connection:
        assert connection.execute(text(
            "SELECT count(*) FROM classifications WHERE task_id=:task AND taxonomy_id=:taxonomy"
        ), {"task": task_id, "taxonomy": taxonomy_id}).scalar_one() == 50
        assert connection.execute(text(
            "SELECT count(*) FROM file_evidence WHERE evidence_kind='VISUAL_DESCRIPTION' AND state='VALID' "
            "AND file_id IN (SELECT id FROM files WHERE task_id=:task)"
        ), {"task": task_id}).scalar_one() == 50
    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in source.iterdir()} == disk_before
    restarted.state.database.close()
