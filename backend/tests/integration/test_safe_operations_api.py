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


def model_payload():
    return {"name":"Contract AI","provider":"qwen_local","runtime":"openai_compatible",
            "base_url":"http://127.0.0.1:8000/v1","model_id":"contract-ai","trust_scope":"loopback",
            "options":{"thinking_mode":"disabled","timeout_seconds":5,"max_concurrency":1,"batch_size":20},
            "enabled":True}


def prepare_ai_classified_task(app, client: TestClient, source: Path, *, operation_mode: str = "preview_move"):
    grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]
    model = app.state.models.create(model_payload())
    settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
    settings.update({"operation_mode": operation_mode, "classification_source": "auto_plan",
                     "scan_mode": "current_only"})
    nodes = [{"category_id":"docs","name":"文本资料","parent_id":None,"selectable":True,
              "definition":{"description":"文本内容","selection_criteria":"正文是说明或笔记"},"is_fallback":False}]
    created = client.post("/api/v1/tasks", headers=headers("create"), json={
        "name":"AI 安全移动","source_grant":grant["grant_id"],"settings":settings,
        "model_profile_id":model["id"],"user_instructions":"按正文内容整理",
    }).json()["data"]
    app.state.tasks.start(created["id"], created["revision"])
    file = app.state.repository.list_files(created["id"])[0][0]
    scope = app.state.repository.list_scopes(created["id"])[0]
    profile = app.state.parsing.parse(created["id"], file["id"]).profile
    draft = app.state.taxonomies.save_draft(created["id"], scope["id"], nodes, "fixed",
        max_depth=2, max_siblings=12, max_nodes=80)
    taxonomy = app.state.taxonomies.approve(created["id"], draft["taxonomy_id"], draft["tree_hash"])
    result = {"file_id":file["id"],"taxonomy_id":taxonomy["taxonomy_id"],"category_id":"docs",
              "abstain":False,"model_score":0.99,"evidence_ids":[profile.evidence[0].id],
              "reason":"AI 根据正文判断为文本资料","tags":[],"warnings":[]}
    app.state.classifications.classify(task_id=created["id"], file_id=file["id"], taxonomy=taxonomy,
        profile=profile, model_callback=lambda _: result)
    return app.state.repository.advance_after_classification(created["id"])


def test_preview_move_compile_approve_revalidate_execute_and_undo(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); original = source / "说明.txt"
    original.write_text("safe semantic move", encoding="utf-8")
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        ready = prepare_ai_classified_task(app, client, source)
        assert ready["status"] == "AWAITING_EXECUTION_APPROVAL"
        compiled_response = client.post(f"/api/v1/tasks/{ready['id']}/plan/compile", headers=headers("compile"), json={})
        assert compiled_response.status_code == 201
        compiled = compiled_response.json()["data"]
        target = Path(compiled["operations"][0]["target_path"])
        assert target == source / "文本资料" / "说明.txt"
        assert compiled["plan_basis_revision"] == ready["revision"] and compiled["approved"] is False

        bad = client.post(f"/api/v1/tasks/{ready['id']}/plan/approve", headers=headers("bad"), json={
            "expected_revision":ready["revision"],"plan_id":compiled["plan_id"],"plan_hash":"0" * 64})
        assert bad.status_code == 409 and bad.json()["error"]["code"] == "PLAN_HASH_MISMATCH"

        approved = client.post(f"/api/v1/tasks/{ready['id']}/plan/approve", headers=headers("approve"), json={
            "expected_revision":ready["revision"],"plan_id":compiled["plan_id"],"plan_hash":compiled["plan_hash"]})
        assert approved.status_code == 200 and approved.json()["data"]["approved"] is True
        verified = client.get(f"/api/v1/tasks/{ready['id']}/plan?plan_id={compiled['plan_id']}", headers=headers()).json()["data"]
        assert verified["plan_id"] == compiled["plan_id"] and verified["plan_hash"] == compiled["plan_hash"]
        assert verified["status"] == "approved" and verified["approved_task_revision"] == ready["revision"]

        executed = client.post(f"/api/v1/tasks/{ready['id']}/execute", headers=headers("execute"), json={
            "expected_revision":ready["revision"],"plan_id":verified["plan_id"],"plan_hash":verified["plan_hash"]})
        assert executed.status_code == 202, executed.text
        assert not original.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == original_hash

        after = client.get(f"/api/v1/tasks/{ready['id']}", headers=headers()).json()["data"]
        undo = client.post(f"/api/v1/tasks/{ready['id']}/undo/plan", headers=headers("undo-plan"), json={
            "expected_revision":after["revision"],"plan_id":compiled["plan_id"],"plan_hash":compiled["plan_hash"]}).json()["data"]
        client.post(f"/api/v1/tasks/{ready['id']}/plan/approve", headers=headers("undo-approve"), json={
            "expected_revision":after["revision"],"plan_id":undo["plan_id"],"plan_hash":undo["plan_hash"]}).raise_for_status()
        undone = client.post(f"/api/v1/tasks/{ready['id']}/execute", headers=headers("undo-execute"), json={
            "expected_revision":after["revision"],"plan_id":undo["plan_id"],"plan_hash":undo["plan_hash"]})
        assert undone.status_code == 202, undone.text
        assert original.exists() and not target.exists()


def test_review_change_supersedes_compiled_plan(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); (source / "a.txt").write_text("semantic")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        ready = prepare_ai_classified_task(app, client, source)
        plan = client.post(f"/api/v1/tasks/{ready['id']}/plan/compile", headers=headers("compile"), json={}).json()["data"]
        file = app.state.repository.list_files(ready["id"])[0][0]
        taxonomy = app.state.taxonomies.list_task(ready["id"])[-1]
        review = client.post(f"/api/v1/tasks/{ready['id']}/reviews/bulk", headers=headers("review"), json={
            "expected_revision":ready["revision"],"items":[{"file_id":file["id"],"taxonomy_id":taxonomy["taxonomy_id"],
            "category_id":"docs","decision":"accept","note":"确认"}]})
        assert review.status_code == 200
        stale = client.post(f"/api/v1/tasks/{ready['id']}/plan/approve", headers=headers("stale"), json={
            "expected_revision":review.json()["data"]["new_revision"],"plan_id":plan["plan_id"],"plan_hash":plan["plan_hash"]})
        assert stale.status_code == 409 and stale.json()["error"]["code"] == "PLAN_STALE"


def test_source_change_after_approval_is_reported_and_not_moved(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); original = source / "a.txt"; original.write_text("before")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        ready = prepare_ai_classified_task(app, client, source)
        plan = client.post(f"/api/v1/tasks/{ready['id']}/plan/compile", headers=headers("compile"), json={}).json()["data"]
        client.post(f"/api/v1/tasks/{ready['id']}/plan/approve", headers=headers("approve"), json={
            "expected_revision":ready["revision"],"plan_id":plan["plan_id"],"plan_hash":plan["plan_hash"]}).raise_for_status()
        original.write_text("changed outside Guixu")
        executed = client.post(f"/api/v1/tasks/{ready['id']}/execute", headers=headers("execute"), json={
            "expected_revision":ready["revision"],"plan_id":plan["plan_id"],"plan_hash":plan["plan_hash"]})
        assert executed.status_code == 202
        result = executed.json()["data"]["results"][0]
        assert result["state"] == "CONFLICT" and result["error_code"] == "SOURCE_CHANGED"
        assert original.exists() and not Path(plan["operations"][0]["target_path"]).exists()


def test_direct_move_is_disabled_in_production(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); (source / "a.txt").write_text("direct")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True, allow_direct_move=False)
    with TestClient(app) as client:
        grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path":str(source),"purpose":"source"}).json()["data"]
        model = app.state.models.create(model_payload())
        settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
        settings.update({"operation_mode":"direct_move","classification_source":"auto_plan"})
        response = client.post("/api/v1/tasks", headers=headers("direct"), json={
            "name":"直接移动测试门","source_grant":grant["grant_id"],"settings":settings,
            "model_profile_id":model["id"]})
        assert response.status_code == 400
