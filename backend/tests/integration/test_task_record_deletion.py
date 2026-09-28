from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from guixu.api.app import create_app
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import utc_now


TOKEN = "task-record-deletion"


def headers(key: str | None = None) -> dict[str, str]:
    result = {"X-Guixu-Session": TOKEN}
    if key:
        result["Idempotency-Key"] = key
    return result


def create_task(app, client: TestClient, source: Path, name: str) -> dict:
    grant = client.post("/api/v1/dev/grants", headers=headers(),
                        json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
    model = app.state.models.list()
    if not model:
        model = [app.state.models.create({"name":"Cleanup AI","provider":"qwen_local","runtime":"openai_compatible",
            "base_url":"http://127.0.0.1:8000/v1","model_id":"fixture","trust_scope":"loopback",
            "options":{"thinking_mode":"disabled","timeout_seconds":5,"max_concurrency":1,"batch_size":20},
            "enabled":True})]
    settings = client.get("/api/v1/settings", headers=headers()).json()["data"]["values"]
    settings.update({"scan_mode":"current_only", "operation_mode":"report_only", "classification_source":"auto_plan"})
    response = client.post("/api/v1/tasks", headers=headers(str(uuid.uuid4())), json={
        "name":name, "source_grant":grant, "settings":settings,
        "model_profile_id":model[0]["id"], "user_instructions":"按内容整理",
    })
    assert response.status_code == 201, response.text
    return response.json()["data"]


def snapshot(folder: Path) -> dict[str, str]:
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(folder.rglob("*")) if path.is_file()}


def test_single_batch_restore_and_disk_invariance(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    (source / "a.txt").write_text("alpha", "utf-8")
    (source / "b.txt").write_text("beta", "utf-8")
    before = snapshot(source)
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        first = create_task(app, client, source, "单删任务")
        second = create_task(app, client, source, "批量一")
        third = create_task(app, client, source, "批量二")

        deleted = client.request("DELETE", f"/api/v1/tasks/{first['id']}", headers=headers("single-delete"),
                                 json={"expected_revision": first["revision"], "delete_reason":"测试清理"})
        assert deleted.status_code == 200 and deleted.json()["data"]["deleted_at"]
        assert {item["id"] for item in client.get("/api/v1/tasks", headers=headers()).json()["data"]["items"]} == {second["id"], third["id"]}
        assert {item["id"] for item in client.get("/api/v1/tasks?view=deleted", headers=headers()).json()["data"]["items"]} == {first["id"]}

        batch = client.post("/api/v1/tasks/batch-delete", headers=headers("batch-delete"),
                            json={"task_ids":[second["id"], third["id"]]})
        assert batch.status_code == 200 and batch.json()["data"]["deleted"] == 2
        trash = client.get("/api/v1/tasks?view=deleted", headers=headers()).json()["data"]["items"]
        assert {item["id"] for item in trash} == {first["id"], second["id"], third["id"]}

        restored = client.post(f"/api/v1/tasks/{first['id']}/restore", headers=headers("restore"),
                               json={"expected_revision": deleted.json()["data"]["revision"]})
        assert restored.status_code == 200 and restored.json()["data"]["deleted_at"] is None
        batch_restore = client.post("/api/v1/tasks/batch-restore", headers=headers("batch-restore"),
                                    json={"task_ids":[second["id"], third["id"]]})
        assert batch_restore.status_code == 200 and batch_restore.json()["data"]["restored"] == 2
        assert snapshot(source) == before


def test_running_task_delete_is_blocked(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); (source / "live.txt").write_text("still here", "utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_task(app, client, source, "运行中")
        with app.state.database.begin() as connection:
            connection.execute(text("UPDATE tasks SET status='RUNNING',phase='EXTRACT' WHERE id=:id"), {"id":task["id"]})
        response = client.request("DELETE", f"/api/v1/tasks/{task['id']}", headers=headers("blocked"),
                                  json={"expected_revision":task["revision"]})
        assert response.status_code == 409 and response.json()["error"]["code"] == "TASK_DELETE_BLOCKED"
        assert (source / "live.txt").read_text("utf-8") == "still here"


def test_completed_task_soft_delete_retains_plan_and_blocks_permanent_delete(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); file = source / "kept.txt"; file.write_text("never touch me", "utf-8")
    before = snapshot(source)
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_task(app, client, source, "已执行历史")
        plan_id = str(uuid.uuid4())
        with app.state.database.begin() as connection:
            connection.execute(text("UPDATE tasks SET status='COMPLETED',phase='REPORT' WHERE id=:id"), {"id":task["id"]})
            connection.execute(text("""
                INSERT INTO plans(id,task_id,version,plan_hash,status,operation_mode,settings_hash,
                  taxonomy_hashes_json,source_snapshot_hash,summary_json,created_at,plan_basis_revision)
                SELECT :plan,id,1,:hash,'finished','report_only',settings_hash,'[]',:source,'{}',:now,revision
                FROM tasks WHERE id=:id
            """), {"plan":plan_id,"hash":"a"*64,"source":"b"*64,"now":utc_now(),"id":task["id"]})
        current = app.state.repository.get(task["id"])
        removed = client.request("DELETE", f"/api/v1/tasks/{task['id']}", headers=headers("completed-delete"),
                                 json={"expected_revision":current["revision"]})
        assert removed.status_code == 200
        with app.state.database.engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM plans WHERE task_id=:id"), {"id":task["id"]}).scalar_one() == 1
        assert client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).status_code == 200
        purge = client.request("DELETE", f"/api/v1/tasks/{task['id']}/permanent", headers=headers("purge-blocked"),
                               json={"expected_revision":removed.json()["data"]["revision"]})
        assert purge.status_code == 409 and purge.json()["error"]["code"] == "TASK_SAFETY_HISTORY_RETAINED"
        assert snapshot(source) == before


def test_permanent_delete_of_record_without_safety_history_never_touches_disk(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); (source / "failed.txt").write_text("preserved", "utf-8")
    before = snapshot(source)
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_task(app, client, source, "可永久清理")
        removed = client.request("DELETE", f"/api/v1/tasks/{task['id']}", headers=headers("soft-before-purge"),
                                 json={"expected_revision":task["revision"]}).json()["data"]
        purge = client.request("DELETE", f"/api/v1/tasks/{task['id']}/permanent", headers=headers("purge"),
                               json={"expected_revision":removed["revision"]})
        assert purge.status_code == 200 and purge.json()["data"]["disk_files_changed"] is False
        assert client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).status_code == 404
        assert snapshot(source) == before


def test_batch_permanent_delete_is_atomic_and_never_touches_disk(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); (source / "batch.txt").write_text("preserved", "utf-8")
    before = snapshot(source)
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        first = create_task(app, client, source, "批量永久一")
        second = create_task(app, client, source, "批量永久二")
        response = client.post("/api/v1/tasks/batch-delete", headers=headers("batch-before-purge"),
                               json={"task_ids":[first["id"], second["id"]]})
        assert response.status_code == 200
        purge = client.post("/api/v1/tasks/batch-permanent-delete", headers=headers("batch-purge"),
                            json={"task_ids":[first["id"], second["id"]]})
        assert purge.status_code == 200
        assert purge.json()["data"] == {"permanently_deleted":2, "disk_files_changed":False}
        assert client.get("/api/v1/tasks?view=all", headers=headers()).json()["data"]["items"] == []
        assert snapshot(source) == before


def test_clear_trash_removes_safe_records_and_hides_safety_history(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir(); (source / "kept.txt").write_text("preserved", "utf-8")
    before = snapshot(source)
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        safe = create_task(app, client, source, "可清理")
        protected = create_task(app, client, source, "保留日志")
        conversation = app.state.conversations.create_conversation(title="已删除对话")
        app.state.conversations.soft_delete_conversation(conversation["id"])
        with app.state.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO plans(id,task_id,version,plan_hash,status,operation_mode,settings_hash,
                  taxonomy_hashes_json,source_snapshot_hash,summary_json,created_at,plan_basis_revision)
                SELECT :plan,id,1,:hash,'finished','report_only',settings_hash,'[]',:source,'{}',:now,revision
                FROM tasks WHERE id=:id
            """), {"plan":str(uuid.uuid4()),"hash":"a"*64,"source":"b"*64,"now":utc_now(),"id":protected["id"]})
        app.state.repository.soft_delete([safe["id"], protected["id"]])
        cleared = client.post("/api/v1/trash/clear", headers=headers("clear-trash"))
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["data"] == {"permanently_deleted_tasks": 1, "retained_safety_records": 1,
                                          "permanently_deleted_conversations": 1, "disk_files_changed": False}
        assert client.get("/api/v1/tasks?view=deleted", headers=headers()).json()["data"]["items"] == []
        assert client.get("/api/v1/conversations?view=deleted", headers=headers()).json()["data"] == []
        assert client.get(f"/api/v1/tasks/{safe['id']}", headers=headers()).status_code == 404
        retained = client.get(f"/api/v1/tasks/{protected['id']}", headers=headers()).json()["data"]
        assert retained["deletion_source"] == "trash_cleared"
        with app.state.database.engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM plans WHERE task_id=:id"), {"id":protected["id"]}).scalar_one() == 1
        assert client.post("/api/v1/trash/clear", headers=headers("clear-again")).json()["data"]["retained_safety_records"] == 0
        assert snapshot(source) == before


def test_new_task_rejects_legacy_modes_and_does_not_seed_templates(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    with TestClient(app) as client:
        task = create_task(app, client, source, "AI-only")
        stored = app.state.repository.get(task["id"])
        assert stored["settings"]["classification_source"] == "auto_plan"
        assert "template_key" not in stored["classification_request"] and "fixed_tree" not in stored["classification_request"]
        with app.state.database.engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM template_versions")).scalar_one() == 0
        bad = {**stored["settings"], "classification_source":"template"}
        grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path":str(source),"purpose":"source"}).json()["data"]["grant_id"]
        response = client.post("/api/v1/tasks", headers=headers("legacy-create"), json={
            "name":"legacy","source_grant":grant,"settings":bad,"model_profile_id":stored["model_profile_id"],
            "classification_request":{"template_key":"text.purpose"},
        })
        assert response.status_code == 400 and "LEGACY_CLASSIFICATION_SOURCE_NOT_ALLOWED" in response.text


def test_legacy_template_task_history_opens_from_snapshots_without_template_api(project_root: Path, tmp_path: Path):
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN,
                     allow_typed_grants=True)
    definition = {"template_id":"legacy.academic","version":1,"name":"旧版学习模板","nodes":[
        {"category_id":"legacy.notes","parent_id":None,"name":"旧版笔记","selectable":True,
         "definition":{"include":"历史快照","exclude":"","evidence_required_any":["extracted_text"],"tie_breaker":"历史"},
         "is_fallback":False}
    ]}
    now = utc_now()
    with TestClient(app) as client:
        with app.state.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO template_versions(id,template_key,version,name,origin,definition_json,definition_hash,created_at)
                VALUES(:id,:key,1,:name,'builtin',:definition,:hash,:now)
            """), {"id":"legacy-template","key":"legacy.academic","name":definition["name"],
                   "definition":json.dumps(definition,ensure_ascii=False),"hash":"c"*64,"now":now})
        task = app.state.repository.create("旧版任务", TaskSettings(operation_mode="report_only", classification_source="template"),
                                           {"template_key":"legacy.academic"})
        scope_id = str(uuid.uuid4()); taxonomy_id = str(uuid.uuid4()); plan_id = str(uuid.uuid4())
        with app.state.database.begin() as connection:
            connection.execute(text("UPDATE tasks SET template_snapshot_json=:snapshot WHERE id=:task"),
                               {"snapshot":json.dumps(definition,ensure_ascii=False),"task":task["id"]})
            connection.execute(text("""
                INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
                VALUES(:scope,:task,'current_only','C:/legacy','C:/legacy','legacy','{}')
            """), {"scope":scope_id,"task":task["id"]})
            connection.execute(text("""
                INSERT INTO taxonomies(id,task_id,scope_id,version,source,status,policy_json,tree_hash,created_at,approved_at)
                VALUES(:taxonomy,:task,:scope,1,'template','approved','{}',:hash,:now,:now)
            """), {"taxonomy":taxonomy_id,"task":task["id"],"scope":scope_id,"hash":"d"*64,"now":now})
            connection.execute(text("""
                INSERT INTO categories(taxonomy_id,category_id,parent_id,name,path_segments_json,depth,ordinal,selectable,definition_json,is_fallback)
                VALUES(:taxonomy,'legacy.notes',NULL,'旧版笔记','["旧版笔记"]',1,0,1,:definition,0)
            """), {"taxonomy":taxonomy_id,"definition":json.dumps(definition["nodes"][0]["definition"],ensure_ascii=False)})
            connection.execute(text("""
                INSERT INTO plans(id,task_id,version,plan_hash,status,operation_mode,settings_hash,taxonomy_hashes_json,
                  source_snapshot_hash,summary_json,created_at,plan_basis_revision)
                SELECT :plan,id,1,:hash,'finished','report_only',settings_hash,:taxonomies,:source,'{}',:now,revision
                FROM tasks WHERE id=:task
            """), {"plan":plan_id,"hash":"e"*64,"taxonomies":json.dumps(["d"*64]),"source":"f"*64,"now":now,"task":task["id"]})
        detail = client.get(f"/api/v1/tasks/{task['id']}", headers=headers()).json()["data"]
        assert detail["template_snapshot"]["name"] == "旧版学习模板"
        trees = client.get(f"/api/v1/tasks/{task['id']}/taxonomies", headers=headers()).json()["data"]
        assert trees[0]["nodes"][0]["name"] == "旧版笔记"
        plan = client.get(f"/api/v1/tasks/{task['id']}/plan", headers=headers()).json()["data"]
        assert plan["plan_id"] == plan_id and "/api/v1/templates" not in app.openapi()["paths"]
