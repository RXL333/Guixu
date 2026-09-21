from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from guixu.application.coordinator import TaskCoordinator
from guixu.application.operations import OperationService
from guixu.application.post_execution import (
    AffectedScopeResolver,
    PostExecutionConversationService,
    WorkspaceStateService,
)
from guixu.domain.settings import TaskSettings
from guixu.domain.profiles import ParseOutcome
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository, canonical_json
from guixu.infrastructure.filesystem.identity import read_identity


class ParsingMustNotRun:
    def parse(self, *args, **kwargs):
        raise AssertionError("valid evidence must be reused")


def taxonomy_snapshot() -> dict:
    return {
        "taxonomy_id": "taxonomy-1",
        "nodes": [
            {"category_id": "building", "name": "建筑", "parent_id": None, "selectable": True},
            {"category_id": "landscape", "name": "风景", "parent_id": None, "selectable": True},
            {"category_id": "people", "name": "人物", "parent_id": None, "selectable": True},
        ],
    }


def profile(file_id: str, path: Path, description: str) -> dict:
    return {
        "schema_version": 1,
        "file_id": file_id,
        "source_path": str(path),
        "name": path.name,
        "extension": path.suffix,
        "mime_type": "image/jpeg",
        "modality": "image",
        "document_kind": None,
        "metadata": {},
        "content_summary": description,
        "summary_origin": "model",
        "evidence": [{"id": f"ev-{file_id}", "kind": "visual_description", "text": description,
                      "locator": {}, "quality": "high", "origin": "test-model"}],
        "coverage": {"mode": "full", "sampled_pages": [], "sampled_intervals": [], "truncated": False},
        "warnings": [],
        "capabilities_used": ["vision"],
        "parser_version": "test-v1",
        "parser_status": "ready",
        "parser_warnings": [],
    }


def make_service(project_root: Path, tmp_path: Path, *, building_count: int = 5, other_count: int = 5):
    root = tmp_path / "workspace"
    building = root / "建筑"
    landscape = root / "风景"
    building.mkdir(parents=True)
    landscape.mkdir()
    database = Database(tmp_path / "data" / "app.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    tasks = TaskRepository(database)
    conversations = ConversationRepository(database)
    journal = SqliteOperationJournal(database)
    operations = OperationService(tasks, journal)
    coordinator = TaskCoordinator(tasks, journal, operations)
    now = utc_now()
    with database.begin() as connection:
        connection.execute(text("""
            INSERT INTO model_profiles(id,name,provider,runtime,base_url,model_id,capabilities_json,options_json,
              trust_scope,enabled,revision,created_at,updated_at)
            VALUES('model-1','Test Model','qwen_local','ollama','http://127.0.0.1','test','{}','{}','loopback',1,1,:now,:now)
        """), {"now": now})
    task = tasks.create("post execution", TaskSettings(operation_mode="preview_move", max_depth=2), {},
                        model_profile_id="model-1", model_snapshot={"name": "Test Model"})
    scope_id = str(uuid.uuid4())
    with database.begin() as connection:
        connection.execute(text("""
            INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
            VALUES(:id,:task,'whole_tree',:root,:root,'workspace','{}')
        """), {"id": scope_id, "task": task["id"], "root": str(root)})
        connection.execute(text("""
            INSERT INTO taxonomies(id,task_id,scope_id,version,source,status,policy_json,tree_hash,created_at,approved_at)
            VALUES('taxonomy-1',:task,:scope,1,'auto','approved','{}',:hash,:now,:now)
        """), {"task": task["id"], "scope": scope_id, "hash": "d" * 64, "now": now})
        for ordinal, node in enumerate(taxonomy_snapshot()["nodes"]):
            connection.execute(text("""
                INSERT INTO categories(taxonomy_id,category_id,parent_id,name,path_segments_json,depth,ordinal,selectable,definition_json,is_fallback)
                VALUES('taxonomy-1',:id,NULL,:name,:segments,1,:ordinal,1,'{}',0)
            """), {"id": node["category_id"], "name": node["name"],
                    "segments": canonical_json([node["name"]]), "ordinal": ordinal})
    file_ids: dict[str, str] = {}
    rows = []
    for index in range(building_count):
        path = building / f"building-{index}.jpg"
        description = "明显的夜晚城市建筑与灯光" if index < 2 else "白天的建筑外观"
        path.write_bytes(f"building-{index}".encode())
        rows.append((path, "building", description))
    for index in range(other_count):
        path = landscape / f"landscape-{index}.jpg"
        description = "人物自拍照，背景是自然风景" if index == 0 else "白天的自然风景"
        path.write_bytes(f"landscape-{index}".encode())
        rows.append((path, "landscape", description))
    with database.begin() as connection:
        for path, category, description in rows:
            file_id = str(uuid.uuid4())
            file_ids[path.name] = file_id
            identity = read_identity(path)
            connection.execute(text("""
                INSERT INTO files(id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,
                  extension,modality,mime,size_bytes,mtime_ns,volume_id,filesystem_file_id,sha256,scan_status,
                  metadata_json,created_at,updated_at)
                VALUES(:id,:task,:scope,:path,:path,:key,:relative,:name,'.jpg','image','image/jpeg',:size,:mtime,
                  :volume,:fsid,:sha,'eligible','{}',:now,:now)
            """), {"id": file_id, "task": task["id"], "scope": scope_id, "path": str(path),
                    "key": str(path).casefold(), "relative": str(path.relative_to(root)), "name": path.name,
                    "size": identity.size_bytes, "mtime": identity.mtime_ns, "volume": identity.volume_id,
                    "fsid": identity.file_id, "sha": identity.sha256, "now": now})
            connection.execute(text("""
                INSERT INTO file_profiles(id,file_id,cache_key,parser_version,options_hash,status,profile_json,created_at)
                VALUES(:id,:file,:cache,'test-v1',:options,'ready',:profile,:now)
            """), {"id": str(uuid.uuid4()), "file": file_id, "cache": identity.sha256,
                    "options": "e" * 64, "profile": canonical_json(profile(file_id, path, description)), "now": now})
        baseline_plan_id = str(uuid.uuid4())
        connection.execute(text("""
            INSERT INTO plans(id,task_id,version,plan_hash,plan_kind,status,operation_mode,settings_hash,
              taxonomy_hashes_json,source_snapshot_hash,plan_basis_revision,summary_json,created_at)
            VALUES(:id,:task,1,:hash,'forward','finished','preview_move',:settings,:taxonomies,:snapshot,1,'{}',:now)
        """), {"id": baseline_plan_id, "task": task["id"], "hash": "a" * 64,
                "settings": task["settings_hash"], "taxonomies": canonical_json(["d" * 64]),
                "snapshot": "b" * 64, "now": now})
    conversation = conversations.create("持续整理", model_profile_id="model-1", scope={
        "source_root": str(root), "display_name": "workspace", "authorization_ref": "test-grant",
    })
    conversation_id = conversation["id"]
    for path, category, _ in rows:
        file_id = file_ids[path.name]
        conversations.attach_file(conversation_id, file_id)
        with database.begin() as connection:
            connection.execute(text("""
                UPDATE conversation_files SET current_category_id=:category
                WHERE conversation_id=:conversation AND file_id=:file
            """), {"category": category, "conversation": conversation_id, "file": file_id})
    v1 = conversations.create_plan_version(
        conversation_id, expected_context_revision=1, basis_context_revision=1, source="USER_REQUEST",
        status="PROPOSED", taxonomy_id="taxonomy-1", taxonomy_snapshot=taxonomy_snapshot(),
        plan_id=baseline_plan_id, plan_hash="a" * 64, summary="第一次整理", affected_file_count=len(rows),
    )
    round1 = conversations.create_execution_round(
        conversation_id, v1["id"], baseline_plan_id, expected_context_revision=2,
        status="COMPLETED", affected_file_count=len(rows), summary={"description": "第一次整理完成"},
    )
    with database.begin() as connection:
        connection.execute(text("UPDATE conversation_plan_versions SET status='EXECUTED',executed_at=:now WHERE id=:id"),
                           {"now": now, "id": v1["id"]})

    calls: list[dict] = []

    def evaluator(**kwargs):
        calls.append(kwargs)
        instruction = kwargs["instruction"]
        results = []
        for item, _, _ in kwargs["items"]:
            text_value = " ".join(e.text for e in item.evidence)
            matches = ("夜景" in instruction and "夜晚" in text_value) or ("自拍" in instruction and "自拍" in text_value)
            results.append({"file_id": item.file_id, "matches": matches,
                            "target_category_id": kwargs["target_category_id"], "reason": "semantic evidence"})
        return results

    service = PostExecutionConversationService(
        database=database, conversations=conversations, tasks=tasks, journal=journal,
        coordinator=coordinator, parsing=ParsingMustNotRun(), evaluator=evaluator,
    )
    return database, conversations, service, conversation_id, v1, round1, file_ids, root, calls


def test_post_execution_local_delta_and_three_rounds(project_root: Path, tmp_path: Path):
    database, repository, service, conversation_id, v1, round1, file_ids, root, calls = make_service(project_root, tmp_path)
    assert repository.get(conversation_id)["status"] == "ACTIVE"
    repository.append_message(conversation_id, "USER", "建筑里的夜景放到风景，其他不要动。")
    before = {path.name: path.read_bytes() for path in root.rglob("*.jpg")}

    prepared = service.prepare_refinement(conversation_id, user_message="建筑里的夜景放到风景，其他不要动。")
    assert prepared["intent"] == "POST_EXECUTION_REFINEMENT"
    assert prepared["status"] == "WAITING_FOR_APPROVAL"
    assert prepared["affected_scope"]["scope_type"] == "LOCAL"
    assert prepared["affected_scope"]["affected_category_ids"] == ["building"]
    assert len(prepared["affected_scope"]["candidate_file_ids"]) == 5
    assert prepared["metrics"] == {
        "total_scope_files": 10, "affected_files": 5, "evidence_reused": 5,
        "evidence_refreshed": 0, "invalid_evidence": 0, "delta_plan_count": 2, "ai_calls": 1,
    }
    version2 = prepared["plan_version"]
    assert version2["plan_kind"] == "DELTA"
    assert version2["baseline_execution_round_id"] == round1["id"]
    with database.engine.connect() as connection:
        operations = connection.execute(text("SELECT file_id,source_path,target_path,state FROM operations WHERE plan_id=:plan"),
                                        {"plan": version2["plan_id"]}).mappings().all()
    assert len(operations) == 2
    assert {row["file_id"] for row in operations} == {file_ids["building-0.jpg"], file_ids["building-1.jpg"]}
    assert {path.name: path.read_bytes() for path in root.rglob("*.jpg")} == before

    context = repository.get_context(conversation_id)
    service.approve(conversation_id, version2["id"], expected_context_revision=context["context_revision"],
                    plan_hash=version2["plan_hash"], authorization={"kind": "interactive"})
    assert {path.name: path.read_bytes() for path in root.rglob("*.jpg")} == before
    result2 = service.execute(conversation_id, version2["id"],
                              expected_context_revision=context["context_revision"], plan_hash=version2["plan_hash"])
    round2 = result2["execution_round"]
    assert round2["round_number"] == 2 and round2["status"] == "COMPLETED"
    assert repository.get(conversation_id)["status"] == "ACTIVE"
    for name in ("building-0.jpg", "building-1.jpg"):
        item = repository.get_conversation_file(conversation_id, file_ids[name])
        assert item["file_id"] == file_ids[name]
        assert Path(item["current_known_path"]).parent.name == "风景"
        assert Path(item["current_known_path"]).read_bytes() == before[name]

    prepared3 = service.prepare_refinement(conversation_id, user_message="风景里的自拍放到人物，其他不要动。")
    version3 = prepared3["plan_version"]
    assert version3["baseline_execution_round_id"] == round2["id"]
    context3 = repository.get_context(conversation_id)
    service.approve(conversation_id, version3["id"], expected_context_revision=context3["context_revision"],
                    plan_hash=version3["plan_hash"], authorization={"kind": "interactive"})
    result3 = service.execute(conversation_id, version3["id"],
                              expected_context_revision=context3["context_revision"], plan_hash=version3["plan_hash"])
    assert result3["execution_round"]["round_number"] == 3
    assert Path(repository.get_conversation_file(conversation_id, file_ids["landscape-0.jpg"])["current_known_path"]).parent.name == "人物"
    versions = repository.list_plan_versions(conversation_id)
    rounds = repository.list_execution_rounds(conversation_id)
    assert [item["version_number"] for item in versions] == [1, 2, 3]
    assert [item["round_number"] for item in rounds] == [1, 2, 3]
    assert versions[0]["id"] == v1["id"] and rounds[0]["id"] == round1["id"]
    assert repository.get_context(conversation_id)["current_execution_round_id"] == rounds[-1]["id"]
    assert len(calls) == 2
    database.close()


def test_global_warning_external_changes_and_restart(project_root: Path, tmp_path: Path):
    database, repository, service, conversation_id, _, _, file_ids, root, calls = make_service(project_root, tmp_path)
    warning = service.prepare_refinement(conversation_id, user_message="不要按照内容分了，全部按照活动分类。")
    assert warning["status"] == "GLOBAL_REPLAN_CONFIRMATION_REQUIRED"
    assert warning["affected_scope"]["scope_type"] == "GLOBAL"
    assert warning["metrics"]["total_scope_files"] == 10
    assert calls == []

    def global_evaluator(**kwargs):
        return [{"file_id": item.file_id, "matches": "building-" in item.name,
                 "target_category_id": "landscape", "reason": "semantic evidence"}
                for item, _, _ in kwargs["items"]]

    service.evaluator = global_evaluator
    global_plan = service.prepare_refinement(
        conversation_id, user_message="全部文件从建筑移到风景。", confirmed_global=True,
    )
    assert global_plan["plan_version"]["plan_kind"] == "FULL"
    assert global_plan["metrics"]["affected_files"] == 10
    assert global_plan["metrics"]["evidence_reused"] == 10
    assert global_plan["metrics"]["evidence_refreshed"] == 0

    changed = root / "建筑" / "building-2.jpg"
    changed.write_bytes(b"changed-content")
    with pytest.raises(ValueError, match="FILE_CHANGED"):
        service.prepare_refinement(conversation_id, user_message="建筑里的夜景放到风景，其他不要动。")

    # Restart keeps the executed baseline and accepts another persisted user turn.
    data_path = database.path
    database.close()
    reopened = Database(data_path, project_root / "contracts" / "database.sql")
    reopened.initialize()
    reopened_repo = ConversationRepository(reopened)
    state = WorkspaceStateService(reopened, reopened_repo).current_state(conversation_id)
    assert state["latest_execution_round_id"] is not None
    message = reopened_repo.append_message(conversation_id, "USER", "继续调整")
    assert message["sequence_number"] >= 1
    reopened.close()


def test_external_move_missing_and_only_insufficient_evidence_refreshes(project_root: Path, tmp_path: Path):
    database, repository, service, conversation_id, _, _, file_ids, root, _ = make_service(project_root, tmp_path)
    moved_from = root / "建筑" / "building-3.jpg"
    moved_to = root / "建筑" / "building-external.jpg"
    moved_from.rename(moved_to)
    state = service.workspace.sync_workspace_state(conversation_id, file_ids=[file_ids["building-3.jpg"]])
    assert state["sync_events"][0]["state"] == "FILE_MOVED_EXTERNALLY"
    assert state["current_files"][0]["file_id"] == file_ids["building-3.jpg"]
    assert Path(state["current_files"][0]["core_current_path"]).name == "building-external.jpg"

    missing = root / "建筑" / "building-4.jpg"
    missing.unlink()
    missing_state = service.workspace.sync_workspace_state(conversation_id, file_ids=[file_ids["building-4.jpg"]])
    assert missing_state["sync_events"][0]["state"] == "FILE_MISSING"

    refresh_id = file_ids["building-2.jpg"]
    with database.begin() as connection:
        raw = connection.execute(text("SELECT profile_json FROM file_profiles WHERE file_id=:file"), {"file": refresh_id}).scalar_one()
        decoded = json.loads(raw)
        decoded["evidence"] = []
        connection.execute(text("UPDATE file_profiles SET profile_json=:profile WHERE file_id=:file"),
                           {"profile": canonical_json(decoded), "file": refresh_id})

    refreshed: list[str] = []

    class OneFileParser:
        def parse(self, task_id, file_id, preset):
            refreshed.append(file_id)
            path = Path(repository.get_conversation_file(conversation_id, file_id)["current_known_path"])
            return ParseOutcome.model_validate({"status": "ready", "profile": profile(file_id, path, "补充后的语义证据"),
                                                "cache_artifacts": []})

    service.parsing = OneFileParser()
    service.evaluator = lambda **kwargs: [
        {"file_id": item.file_id, "matches": item.file_id == refresh_id,
         "target_category_id": "landscape", "reason": "semantic evidence"}
        for item, _, _ in kwargs["items"]
    ]
    # Exclude the deliberately missing row from the category before preparing.
    with database.begin() as connection:
        connection.execute(text("UPDATE conversation_files SET current_category_id='people' WHERE file_id=:file"),
                           {"file": file_ids["building-4.jpg"]})
    prepared = service.prepare_refinement(conversation_id, user_message="建筑里的夜景放到风景，其他不要动。")
    assert refreshed == [refresh_id]
    assert prepared["metrics"]["evidence_refreshed"] == 1
    assert prepared["metrics"]["evidence_reused"] == 3
    database.close()


def test_affected_scope_500_to_20_and_prompt_content_is_not_an_instruction():
    files = [
        {"file_id": f"f-{index}", "category_id": "building" if index < 20 else "other"}
        for index in range(500)
    ]
    workspace = {
        "latest_execution_round_id": "round-1",
        "current_taxonomy": {"nodes": [
            {"category_id": "building", "name": "建筑"},
            {"category_id": "landscape", "name": "风景"},
            {"category_id": "other", "name": "其他"},
        ]},
        "current_files": files,
    }
    resolved = AffectedScopeResolver().resolve("建筑里的夜景放到风景，其他不要动。", workspace)
    assert resolved["scope_type"] == "LOCAL"
    assert len(resolved["candidate_file_ids"]) == 20
    assert set(resolved["candidate_file_ids"]) == {f"f-{index}" for index in range(20)}
    assert resolved["preserve_unaffected"] is True
    assert "f-499" not in resolved["candidate_file_ids"]
