from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from guixu.api.app import create_app
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.db.database import utc_now


TOKEN = "conversation-model-test"


def headers(key: str | None = None) -> dict[str, str]:
    result = {"X-Guixu-Session": TOKEN}
    if key:
        result["Idempotency-Key"] = key
    return result


def create_conversation(client: TestClient, source: Path, title: str = "会话测试") -> dict:
    grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
    response = client.post("/api/v1/conversations", headers=headers(str(uuid.uuid4())), json={"title": title, "scope_grant": grant})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def insert_core_task_file_and_plan(app, source: Path) -> tuple[dict, str, str]:
    task = TaskRepository(app.state.database).create("会话核心任务", TaskSettings(operation_mode="report_only", classification_source="auto_plan"), {})
    scope_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())
    now = utc_now()
    with app.state.database.begin() as connection:
        connection.execute(text("""
            INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
            VALUES(:id,:task,'whole_tree',:root,:root,'源目录','{}')
        """), {"id": scope_id, "task": task["id"], "root": str(source)})
        connection.execute(text("""
            INSERT INTO files(id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,
              extension,modality,size_bytes,mtime_ns,scan_status,metadata_json,created_at,updated_at)
            VALUES(:id,:task,:scope,:path,:path,:key,'photo.txt','photo.txt','.txt','text',:size,:mtime,'eligible','{}',:now,:now)
        """), {"id": file_id, "task": task["id"], "scope": scope_id, "path": str(source / "photo.txt"),
                "key": str(source / "photo.txt").casefold(), "size": (source / "photo.txt").stat().st_size,
                "mtime": (source / "photo.txt").stat().st_mtime_ns, "now": now})
        connection.execute(text("""
            INSERT INTO plans(id,task_id,version,plan_hash,status,operation_mode,settings_hash,
              taxonomy_hashes_json,source_snapshot_hash,plan_basis_revision,summary_json,created_at)
            VALUES(:id,:task,1,:hash,'validated','report_only',:settings,'[]',:snapshot,1,'{}',:now)
        """), {"id": plan_id, "task": task["id"], "hash": "a" * 64, "settings": "b" * 64,
                "snapshot": "c" * 64, "now": now})
    return task, file_id, plan_id


def test_conversation_messages_context_versions_rounds_files_and_restart(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    sample = source / "photo.txt"
    sample.write_text("same bytes", encoding="utf-8")
    before = hashlib.sha256(sample.read_bytes()).hexdigest()
    data_dir = tmp_path / "data"

    app = create_app(project_root=project_root, data_dir=data_dir, session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        conversation = create_conversation(client, source)
        conversation_id = conversation["id"]
        assert conversation["status"] == "ACTIVE"
        assert conversation["context"]["context_revision"] == 1
        assert conversation["scopes"][0]["source_root"] == str(source.resolve())

        for role, content in (("USER", "按内容整理"), ("ASSISTANT", "已保存状态"), ("SYSTEM_EVENT", "状态已持久化")):
            response = client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=headers(str(uuid.uuid4())),
                                   json={"role": role, "content": content})
            assert response.status_code == 201, response.text
        updated = client.patch(f"/api/v1/conversations/{conversation_id}/context", headers=headers(str(uuid.uuid4())),
                               json={"expected_revision": 1, "changes": {"confirmed_requirements": [{"id": "req_1", "text": "建筑单独分类", "status": "active"}]}})
        assert updated.status_code == 200 and updated.json()["data"]["context_revision"] == 2
        conflict = client.patch(f"/api/v1/conversations/{conversation_id}/context", headers=headers(str(uuid.uuid4())),
                                json={"expected_revision": 1, "changes": {"selection_state": {"file_ids": []}}})
        assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "CONTEXT_REVISION_CONFLICT"

        task, file_id, plan_id = insert_core_task_file_and_plan(app, source)
        plan_version = client.post(f"/api/v1/conversations/{conversation_id}/plans", headers=headers(str(uuid.uuid4())),
                                   json={"expected_context_revision": 2, "basis_context_revision": 2,
                                         "plan_id": plan_id, "summary": "v1"})
        assert plan_version.status_code == 201, plan_version.text
        pv = plan_version.json()["data"]
        round_response = client.post(f"/api/v1/conversations/{conversation_id}/executions", headers=headers(str(uuid.uuid4())),
                                     json={"expected_context_revision": 3, "plan_version_id": pv["id"], "execution_plan_id": plan_id,
                                           "status": "COMPLETED", "affected_file_count": 1})
        assert round_response.status_code == 201, round_response.text
        execution_round = round_response.json()["data"]
        assert execution_round["round_number"] == 1

        attached = client.post(f"/api/v1/conversations/{conversation_id}/files", headers=headers(str(uuid.uuid4())), json={"file_id": file_id})
        assert attached.status_code == 201, attached.text
        moved = source / "moved.txt"
        sample.rename(moved)
        with app.state.database.begin() as connection:
            connection.execute(text("UPDATE files SET current_path=:path,path_key=:key,updated_at=:now WHERE id=:id"),
                               {"path": str(moved), "key": str(moved).casefold(), "now": utc_now(), "id": file_id})
        verified = client.post(f"/api/v1/conversations/{conversation_id}/files/{file_id}/verify", headers=headers(str(uuid.uuid4())))
        assert verified.status_code == 200 and verified.json()["data"]["file_id"] == file_id
        assert verified.json()["data"]["state"] == "ACTIVE"
        moved.write_text("changed bytes", encoding="utf-8")
        changed = client.post(f"/api/v1/conversations/{conversation_id}/files/{file_id}/verify", headers=headers(str(uuid.uuid4())))
        assert changed.status_code == 200 and changed.json()["data"]["state"] == "FILE_CHANGED"

        deleted = client.delete(f"/api/v1/conversations/{conversation_id}", headers=headers(str(uuid.uuid4())))
        assert deleted.status_code == 200 and deleted.json()["data"]["disk_files_changed"] is False
        assert client.get("/api/v1/conversations", headers=headers()).json()["data"] == []
        assert client.get("/api/v1/conversations?view=deleted", headers=headers()).json()["data"][0]["id"] == conversation_id
        with app.state.database.engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM conversation_messages WHERE conversation_id=:id"), {"id": conversation_id}).scalar_one() == 3
            assert connection.execute(text("SELECT COUNT(*) FROM conversation_execution_rounds WHERE conversation_id=:id"), {"id": conversation_id}).scalar_one() == 1
            assert connection.execute(text("SELECT COUNT(*) FROM plans WHERE id=:id"), {"id": plan_id}).scalar_one() == 1
        assert hashlib.sha256(moved.read_bytes()).hexdigest() != before
        restored = client.post(f"/api/v1/conversations/{conversation_id}/restore", headers=headers(str(uuid.uuid4())))
        assert restored.status_code == 200 and restored.json()["data"]["status"] == "ACTIVE"

    app2 = create_app(project_root=project_root, data_dir=data_dir, session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app2) as client:
        persisted = client.get(f"/api/v1/conversations/{conversation_id}", headers=headers())
        assert persisted.status_code == 200
        payload = persisted.json()["data"]
        assert [item["sequence_number"] for item in client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=headers()).json()["data"]] == [1, 2, 3]
        assert payload["context"]["current_plan_version_id"] == pv["id"]
        assert payload["context"]["current_execution_round_id"] == execution_round["id"]
        assert payload["tasks"][0]["id"] == task["id"]


def test_legacy_task_remains_unlinked_after_v4_schema(project_root: Path, tmp_path: Path):
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    task = TaskRepository(app.state.database).create("旧任务", TaskSettings(operation_mode="report_only", classification_source="auto_plan"), {})
    assert task["conversation_id"] is None
    assert app.state.repository.get(task["id"])["conversation_plan_version_id"] is None
    app.state.database.close()
