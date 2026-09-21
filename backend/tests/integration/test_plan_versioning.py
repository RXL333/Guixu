from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from guixu.api.app import create_app
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import utc_now
from guixu.infrastructure.db.repository import TaskRepository


TOKEN = "plan-versioning-test"


def headers(key: str | None = None) -> dict[str, str]:
    result = {"X-Guixu-Session": TOKEN}
    if key:
        result["Idempotency-Key"] = key
    return result


def create_conversation(client: TestClient, source: Path) -> dict:
    grant = client.post("/api/v1/dev/grants", headers=headers(), json={"path": str(source), "purpose": "source"}).json()["data"]["grant_id"]
    response = client.post(
        "/api/v1/conversations",
        headers=headers(str(uuid.uuid4())),
        json={"title": "版本测试", "scope_grant": grant},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def create_core_plans(app, source: Path) -> tuple[str, str, str]:
    task = TaskRepository(app.state.database).create(
        "版本核心任务", TaskSettings(operation_mode="report_only", classification_source="auto_plan"), {}
    )
    scope_id, file_id = str(uuid.uuid4()), str(uuid.uuid4())
    plan_one, plan_two = str(uuid.uuid4()), str(uuid.uuid4())
    now = utc_now()
    sample = source / "photo.txt"
    with app.state.database.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
                VALUES(:id,:task,'whole_tree',:root,:root,'源目录','{}')
            """),
            {"id": scope_id, "task": task["id"], "root": str(source)},
        )
        connection.execute(
            text("""
                INSERT INTO files(id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,
                  extension,modality,size_bytes,mtime_ns,scan_status,metadata_json,created_at,updated_at)
                VALUES(:id,:task,:scope,:path,:path,:key,'photo.txt','photo.txt','.txt','text',:size,:mtime,'eligible','{}',:now,:now)
            """),
            {
                "id": file_id,
                "task": task["id"],
                "scope": scope_id,
                "path": str(sample),
                "key": str(sample).casefold(),
                "size": sample.stat().st_size,
                "mtime": sample.stat().st_mtime_ns,
                "now": now,
            },
        )
        for number, plan_id, plan_hash in ((1, plan_one, "1" * 64), (2, plan_two, "2" * 64)):
            connection.execute(
                text("""
                    INSERT INTO plans(id,task_id,version,plan_hash,status,operation_mode,settings_hash,
                      taxonomy_hashes_json,source_snapshot_hash,plan_basis_revision,summary_json,created_at)
                    VALUES(:id,:task,:version,:hash,'validated','report_only',:settings,'[]',:snapshot,1,'{}',:now)
                """),
                {
                    "id": plan_id,
                    "task": task["id"],
                    "version": number,
                    "hash": plan_hash,
                    "settings": "b" * 64,
                    "snapshot": str(number) * 64,
                    "now": now,
                },
            )
        for plan_id, target in ((plan_one, source / "A" / "photo.txt"), (plan_two, source / "B" / "photo.txt")):
            connection.execute(
                text("""
                    INSERT INTO operations(id,plan_id,file_id,ordinal,action,source_path,target_path,target_key,
                      source_snapshot_json,expected_sha256,state,updated_at)
                    VALUES(:id,:plan,:file,0,'move',:source,:target,:key,'{}',:sha,'PLANNED',:now)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "plan": plan_id,
                    "file": file_id,
                    "source": str(sample),
                    "target": str(target),
                    "key": str(target).casefold(),
                    "sha": "a" * 64,
                    "now": now,
                },
            )
    return task["id"], file_id, plan_one, plan_two


def test_plan_versions_diff_approval_execution_and_restore(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "photo.txt").write_text("stable", encoding="utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        conversation = create_conversation(client, source)
        conversation_id = conversation["id"]
        task_id, file_id, plan_one, plan_two = create_core_plans(app, source)

        first = client.post(
            f"/api/v1/conversations/{conversation_id}/plans",
            headers=headers(str(uuid.uuid4())),
            json={
                "expected_context_revision": 1,
                "basis_context_revision": 1,
                "plan_id": plan_one,
                "taxonomy_snapshot": {"nodes": [{"id": "travel", "name": "旅行"}]},
                "summary": "第一版",
            },
        )
        assert first.status_code == 201, first.text
        v1 = first.json()["data"]
        assert v1["version_number"] == 1

        second = client.post(
            f"/api/v1/conversations/{conversation_id}/plans",
            headers=headers(str(uuid.uuid4())),
            json={
                "expected_context_revision": 2,
                "basis_context_revision": 2,
                "parent_plan_version_id": v1["id"],
                "plan_id": plan_two,
                "taxonomy_snapshot": {"nodes": [{"id": "travel", "name": "旅行照片"}, {"id": "people", "name": "人物"}]},
                "summary": "第二版",
            },
        )
        assert second.status_code == 201, second.text
        v2 = second.json()["data"]
        assert v2["version_number"] == 2
        assert v2["parent_plan_version_id"] == v1["id"]
        refreshed_v1 = client.get(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v1['id']}", headers=headers()
        ).json()["data"]
        assert refreshed_v1["status"] == "SUPERSEDED"

        diff = client.get(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v2['id']}/diff",
            headers=headers(),
        )
        assert diff.status_code == 200, diff.text
        diff_data = diff.json()["data"]
        assert diff_data["summary_counts"]["target_changed"] == 1
        assert diff_data["summary_counts"]["categories_added"] == 1
        assert diff_data["summary_counts"]["categories_changed"] == 1
        assert diff_data["affected_file_ids"] == [file_id]

        wrong_hash = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v2['id']}/approve",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 3, "plan_hash": "1" * 64},
        )
        assert wrong_hash.status_code == 409
        assert wrong_hash.json()["error"]["code"] == "PLAN_HASH_MISMATCH"
        approval = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v2['id']}/approve",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 3, "plan_hash": "2" * 64, "authorization": {"kind": "interactive"}},
        )
        assert approval.status_code == 200, approval.text
        assert approval.json()["data"]["status"] == "ACTIVE"
        approval_retry = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v2['id']}/approve",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 3, "plan_hash": "2" * 64},
        )
        assert approval_retry.status_code == 200, approval_retry.text
        assert approval_retry.json()["data"]["id"] == approval.json()["data"]["id"]
        current = client.get(f"/api/v1/conversations/{conversation_id}/plan-versions/current", headers=headers())
        assert current.status_code == 200 and current.json()["data"]["id"] == v2["id"]

        execution = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v2['id']}/execution-rounds",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 3, "plan_hash": "2" * 64, "status": "PENDING", "affected_file_count": 1},
        )
        assert execution.status_code == 201, execution.text
        assert execution.json()["data"]["plan_version_id"] == v2["id"]
        assert execution.json()["data"]["execution_plan_id"] == plan_two

        # The old approval cannot be reused once a new immutable version advances the context.
        third = client.post(
            f"/api/v1/conversations/{conversation_id}/plans",
            headers=headers(str(uuid.uuid4())),
            json={
                "expected_context_revision": 4,
                "basis_context_revision": 4,
                "parent_plan_version_id": v2["id"],
                "plan_id": plan_one,
                "summary": "第三版",
            },
        )
        assert third.status_code == 201, third.text
        v3 = third.json()["data"]
        assert v3["version_number"] == 3
        stale = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v2['id']}/execution-rounds",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 5, "plan_hash": "2" * 64},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] in {"PLAN_VERSION_NOT_CURRENT", "PLAN_APPROVAL_STALE"}

        restored = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{v1['id']}/restore",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 5, "expected_current_plan_version_id": v3["id"]},
        )
        assert restored.status_code == 201, restored.text
        restored_data = restored.json()["data"]
        assert restored_data["version_number"] == 4
        assert restored_data["restored_from_version_id"] == v1["id"]
        assert restored_data["plan_id"] == plan_one

        history = client.get(f"/api/v1/conversations/{conversation_id}/plan-versions", headers=headers()).json()["data"]
        assert [item["version_number"] for item in history] == [1, 2, 3, 4]
        assert history[0]["plan_hash"] == "1" * 64
        assert task_id


def test_restore_is_blocked_when_conversation_file_changes(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    sample = source / "photo.txt"
    sample.write_text("before", encoding="utf-8")
    app = create_app(project_root=project_root, data_dir=tmp_path / "data", session_token=TOKEN, allow_typed_grants=True)
    with TestClient(app) as client:
        conversation = create_conversation(client, source)
        conversation_id = conversation["id"]
        _, file_id, plan_one, _ = create_core_plans(app, source)
        version = client.post(
            f"/api/v1/conversations/{conversation_id}/plans",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 1, "basis_context_revision": 1, "plan_id": plan_one},
        )
        assert version.status_code == 201, version.text
        attached = client.post(
            f"/api/v1/conversations/{conversation_id}/files",
            headers=headers(str(uuid.uuid4())),
            json={"file_id": file_id},
        )
        assert attached.status_code == 201, attached.text
        sample.write_text("after", encoding="utf-8")
        verification = client.post(
            f"/api/v1/conversations/{conversation_id}/files/{file_id}/verify",
            headers=headers(str(uuid.uuid4())),
        )
        assert verification.status_code == 200
        assert verification.json()["data"]["state"] == "FILE_CHANGED"
        restore = client.post(
            f"/api/v1/conversations/{conversation_id}/plan-versions/{version.json()['data']['id']}/restore",
            headers=headers(str(uuid.uuid4())),
            json={"expected_context_revision": 2},
        )
        assert restore.status_code == 409
        assert restore.json()["error"]["code"] == "PLAN_RESTORE_FILE_CHANGED"
