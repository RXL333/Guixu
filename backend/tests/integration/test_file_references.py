from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from guixu.application.file_references import ReferenceResolutionError, ReferenceResolver
from guixu.application.post_execution import AffectedScopeResolver, WorkspaceStateService
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import TaskRepository, canonical_json
from guixu.infrastructure.filesystem.identity import read_identity


def fixture_service(project_root: Path, tmp_path: Path):
    source = project_root / "backend" / "tests" / "integration" / "test_post_execution_conversation.py"
    spec = importlib.util.spec_from_file_location("post_execution_fixture_for_references", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_service(project_root, tmp_path, building_count=3, other_count=3)


def test_ui_selection_focus_snapshot_and_conversation_isolation(project_root: Path, tmp_path: Path):
    database, repository, _, conversation_id, _, _, file_ids, root, _ = fixture_service(project_root, tmp_path)
    resolver = ReferenceResolver(database, repository)
    selected = [file_ids["building-0.jpg"], file_ids["building-1.jpg"]]
    result = resolver.resolve(conversation_id, "这些放到风景", selected_file_ids=selected)
    assert result["source"] == "UI_SELECTION" and result["file_ids"] == selected
    selected_five = [
        file_ids["building-0.jpg"], file_ids["building-1.jpg"], file_ids["building-2.jpg"],
        file_ids["landscape-0.jpg"], file_ids["landscape-1.jpg"],
    ]
    five_result = resolver.resolve(
        conversation_id, "这些放到毕业旅行，其他不要动", selected_file_ids=selected_five,
    )
    assert five_result["source"] == "UI_SELECTION" and five_result["file_ids"] == selected_five
    workspace = WorkspaceStateService(database, repository).current_state(conversation_id)
    five_scope = AffectedScopeResolver().resolve(
        "这些放到毕业旅行，其他不要动", workspace, explicit_file_ids=selected_five,
    )
    assert five_scope["scope_type"] == "EXPLICIT"
    assert five_scope["candidate_file_ids"] == selected_five
    focused = resolver.resolve(conversation_id, "这个别动", focused_file_id=selected[0])
    assert focused["source"] == "FOCUSED_FILE" and focused["file_ids"] == selected[:1]

    message = repository.append_message(conversation_id, "USER", "这些放到风景",
                                        referenced_file_ids=selected, reference_source="UI_SELECTION")
    moved = root / "风景" / "building-0.jpg"
    original = root / "建筑" / "building-0.jpg"
    original.replace(moved)
    with database.begin() as connection:
        connection.execute(text("UPDATE files SET current_path=:path,path_key=:key WHERE id=:file"),
                           {"path": str(moved), "key": str(moved).casefold(), "file": selected[0]})
        connection.execute(text("UPDATE conversation_files SET current_known_path=:path WHERE conversation_id=:conversation AND file_id=:file"),
                           {"path": str(moved), "conversation": conversation_id, "file": selected[0]})
    persisted = repository.get_message(message["id"])
    assert persisted["referenced_file_ids"] == selected
    assert persisted["file_references"][0]["path_snapshot"].endswith("建筑\\building-0.jpg") or persisted["file_references"][0]["path_snapshot"].endswith("建筑/building-0.jpg")
    assert persisted["file_references"][0]["current_known_path"] == str(moved)

    other = repository.create("Other", model_profile_id="model-1", scope={"source_root": str(root), "display_name": "other"})
    with pytest.raises(ReferenceResolutionError, match="REFERENCE_SCOPE_VIOLATION"):
        resolver.resolve(other["id"], "这些", selected_file_ids=selected)
    database_path, schema_path = database.path, database.schema_path
    database.close()
    restarted = Database(database_path, schema_path)
    restarted.initialize()
    restored = ConversationRepository(restarted).get_message(message["id"])
    assert restored["referenced_file_ids"] == selected
    assert restored["file_references"][0]["current_known_path"] == str(moved)
    restarted.close()


def test_recent_message_exact_duplicate_ambiguity_and_priority(project_root: Path, tmp_path: Path):
    database, repository, _, conversation_id, _, _, file_ids, _, _ = fixture_service(project_root, tmp_path)
    resolver = ReferenceResolver(database, repository)
    recent = [file_ids["building-0.jpg"], file_ids["building-1.jpg"]]
    repository.append_message(conversation_id, "ASSISTANT", "我找到两张照片",
                              referenced_file_ids=recent, reference_source="LATEST_PLAN_AFFECTED", reference_role="RESULT")
    assert resolver.resolve(conversation_id, "刚才那几个单独放")["file_ids"] == recent
    override = [file_ids["landscape-0.jpg"]]
    assert resolver.resolve(conversation_id, "这些放旅行", selected_file_ids=override)["file_ids"] == override
    exact = resolver.resolve(conversation_id, "building-2.jpg 放到风景")
    assert exact["source"] == "EXPLICIT_FILENAME" and exact["file_ids"] == [file_ids["building-2.jpg"]]

    with database.begin() as connection:
        for file_id in (file_ids["building-0.jpg"], file_ids["landscape-0.jpg"]):
            current = connection.execute(text("SELECT current_known_path FROM conversation_files WHERE file_id=:id"),
                                         {"id": file_id}).scalar_one()
            connection.execute(text("UPDATE conversation_files SET current_known_path=:path WHERE file_id=:id"),
                               {"path": str(Path(current).with_name("same.jpg")), "id": file_id})
    with pytest.raises(ReferenceResolutionError, match="REFERENCE_DUPLICATE_FILENAME"):
        resolver.resolve(conversation_id, "same.jpg 放到风景")
    with database.begin() as connection:
        connection.execute(text("DELETE FROM conversation_message_file_references"))
    with pytest.raises(ReferenceResolutionError, match="REFERENCE_AMBIGUOUS"):
        resolver.resolve(conversation_id, "这些都放旅行")
    database.close()


def test_bulk_file_attachment_is_atomic_and_rejects_out_of_scope_ids(project_root: Path, tmp_path: Path):
    database, repository, _, conversation_id, _, _, file_ids, root, _ = fixture_service(project_root, tmp_path)
    outside_root = tmp_path / "other-conversation"
    outside_root.mkdir()
    outside_file = outside_root / "private.txt"
    outside_file.write_text("not authorized by this conversation", encoding="utf-8")
    identity = read_identity(outside_file)
    other_task = TaskRepository(database).create(
        "outside scope fixture", TaskSettings(operation_mode="report_only"), {}
    )
    scope_id = str(uuid.uuid4())
    now = utc_now()
    with database.begin() as connection:
        connection.execute(text("""
            INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
            VALUES(:id,:task,'whole_tree',:root,:root,'outside','{}')
        """), {"id": scope_id, "task": other_task["id"], "root": str(outside_root)})
        connection.execute(text("""
            INSERT INTO files(id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,
              extension,modality,mime,size_bytes,mtime_ns,volume_id,filesystem_file_id,sha256,scan_status,
              metadata_json,created_at,updated_at)
            VALUES('outside-file',:task,:scope,:path,:path,:key,'private.txt','private.txt','.txt','text',
              'text/plain',:size,:mtime,:volume,:fsid,:sha,'eligible','{}',:now,:now)
        """), {"task": other_task["id"], "scope": scope_id, "path": str(outside_file),
                "key": str(outside_file).casefold(), "size": identity.size_bytes, "mtime": identity.mtime_ns,
                "volume": identity.volume_id, "fsid": identity.file_id, "sha": identity.sha256, "now": now})

    before_ids = {item["file_id"] for item in repository.list_conversation_files(conversation_id)}
    with pytest.raises(ValueError, match="REFERENCE_SCOPE_VIOLATION"):
        repository.attach_files(conversation_id, [file_ids["building-0.jpg"], "outside-file"])
    after_ids = {item["file_id"] for item in repository.list_conversation_files(conversation_id)}
    assert after_ids == before_ids
    assert "outside-file" not in after_ids
    attached = repository.attach_files(conversation_id, [file_ids["building-0.jpg"], file_ids["building-0.jpg"]])
    assert len(attached) == 1 and attached[0]["file_id"] == file_ids["building-0.jpg"]
    assert outside_file.read_text(encoding="utf-8") == "not authorized by this conversation"
    database.close()


def test_rescan_keeps_history_but_counts_each_current_path_once(project_root: Path, tmp_path: Path):
    database, repository, _, conversation_id, _, _, file_ids, _, _ = fixture_service(project_root, tmp_path)
    originals = [file_ids["building-0.jpg"], file_ids["building-1.jpg"]]
    with database.begin() as connection:
        for index, file_id in enumerate(originals):
            old = connection.execute(text("SELECT * FROM files WHERE id=:id"), {"id": file_id}).mappings().one()
            new_id = f"rescan-{index}"
            values = dict(old)
            values["id"] = new_id
            values["path_key"] = f"rescan-{index}"
            columns = ",".join(values)
            params = ",".join(f":{key}" for key in values)
            connection.execute(text(f"INSERT INTO files({columns}) VALUES({params})"), values)
            connection.execute(text("""
                INSERT INTO conversation_files(id,conversation_id,file_id,first_seen_path,current_known_path,
                  first_seen_fingerprint,current_fingerprint,first_seen_size_bytes,current_size_bytes,
                  first_seen_mtime_ns,current_mtime_ns,added_at,state)
                VALUES(:id,:conversation,:file,:path,:path,:sha,:sha,:size,:size,:mtime,:mtime,
                  '9999-01-01T00:00:00+00:00','ACTIVE')
            """), {"id": f"cf-{new_id}", "conversation": conversation_id, "file": new_id,
                    "path": old["current_path"], "sha": old["sha256"], "size": old["size_bytes"],
                    "mtime": old["mtime_ns"]})
    assert len(repository.list_conversation_files(conversation_id, include_removed=True)) == 8
    visible = repository.list_conversation_files(conversation_id, unique_current=True)
    assert len(visible) == 6
    assert {item["file_id"] for item in visible}.isdisjoint(originals)
    state = WorkspaceStateService(database, repository).current_state(conversation_id)
    assert state["total_scope_files"] == 6
    assert ReferenceResolver(database, repository).resolve(
        conversation_id, "building-0.jpg 放到风景"
    )["file_ids"] == ["rescan-0"]
    database.close()


def test_latest_plan_and_actual_execution_references(project_root: Path, tmp_path: Path):
    database, repository, _, conversation_id, v1, round1, file_ids, root, _ = fixture_service(project_root, tmp_path)
    resolver = ReferenceResolver(database, repository)
    plan_ids = [file_ids["building-0.jpg"], file_ids["building-1.jpg"]]
    with database.begin() as connection:
        connection.execute(text("UPDATE conversation_plan_versions SET change_summary_json=:changes WHERE id=:id"),
                           {"changes": canonical_json({"moves": [{"file_id": item} for item in plan_ids]}), "id": v1["id"]})
        for ordinal, file_id in enumerate(plan_ids):
            path = root / "建筑" / f"building-{ordinal}.jpg"
            connection.execute(text("""
                INSERT INTO operations(id,plan_id,file_id,ordinal,action,source_path,target_path,target_key,
                  source_snapshot_json,expected_sha256,state,actual_target_path,result_sha256,updated_at)
                SELECT :id,:plan,:file,:ordinal,'move',:path,:path,:key,'{}',sha256,'COMMITTED',:path,sha256,datetime('now')
                FROM files WHERE id=:file
            """), {"id": f"op-{ordinal}", "plan": round1["execution_plan_id"], "file": file_id,
                    "ordinal": ordinal, "path": str(path), "key": str(path).casefold()})
    assert resolver.resolve(conversation_id, "刚才修改的文件再检查一下")["file_ids"] == plan_ids
    executed = resolver.resolve(conversation_id, "上一次移动的文件再检查一下")
    assert executed["source"] == "LATEST_EXECUTION_AFFECTED" and executed["file_ids"] == plan_ids
    database.close()


def test_missing_changed_and_explicit_affected_scope_never_expand(project_root: Path, tmp_path: Path):
    database, repository, _, conversation_id, _, _, file_ids, root, _ = fixture_service(project_root, tmp_path)
    resolver = ReferenceResolver(database, repository)
    missing_id = file_ids["building-0.jpg"]
    (root / "建筑" / "building-0.jpg").unlink()
    with database.begin() as connection:
        connection.execute(text("UPDATE conversation_files SET state='MISSING' WHERE conversation_id=:conversation AND file_id=:file"),
                           {"conversation": conversation_id, "file": missing_id})
    resolved = resolver.resolve(conversation_id, "这些", selected_file_ids=[missing_id])
    assert resolved["missing"] == [missing_id] and resolved["requires_confirmation"] is True

    selected = [file_ids["building-1.jpg"]]
    workspace = WorkspaceStateService(database, repository).current_state(conversation_id)
    scope = AffectedScopeResolver().resolve("这些放到风景，其他不要动", workspace, explicit_file_ids=selected)
    assert scope["scope_type"] == "EXPLICIT" and scope["candidate_file_ids"] == selected
    assert "选择整个C盘作为引用范围" not in scope["candidate_file_ids"]
    database.close()


def test_five_hundred_file_reference_is_one_batch(project_root: Path, tmp_path: Path):
    database, repository, _, conversation_id, _, _, file_ids, _, _ = fixture_service(project_root, tmp_path)
    # Expand the existing six stable IDs to a large request without per-file API
    # calls by attaching generated copies through one database fixture transaction.
    template_id = next(iter(file_ids.values()))
    with database.begin() as connection:
        template = connection.execute(text("SELECT * FROM files WHERE id=:id"), {"id": template_id}).mappings().one()
        for index in range(494):
            file_id = f"bulk-{index:04d}"
            values = dict(template)
            values.update({"id": file_id, "original_path": f"{template['original_path']}.{index}",
                           "current_path": template["current_path"], "path_key": f"bulk-{index}",
                           "relative_path": f"bulk-{index}.jpg", "basename": f"bulk-{index}.jpg"})
            columns = ",".join(values)
            params = ",".join(f":{key}" for key in values)
            connection.execute(text(f"INSERT INTO files({columns}) VALUES({params})"), values)
            connection.execute(text("""
                INSERT INTO conversation_files(id,conversation_id,file_id,first_seen_path,current_known_path,
                  first_seen_fingerprint,current_fingerprint,first_seen_size_bytes,current_size_bytes,
                  first_seen_mtime_ns,current_mtime_ns,current_category_id,added_at,state)
                VALUES(:id,:conversation,:file,:path,:path,:sha,:sha,:size,:size,:mtime,:mtime,'building',datetime('now'),'ACTIVE')
            """), {"id": f"cf-{file_id}", "conversation": conversation_id, "file": file_id,
                    "path": template["current_path"], "sha": template["sha256"], "size": template["size_bytes"],
                    "mtime": template["mtime_ns"]})
    ids = [item["file_id"] for item in repository.list_conversation_files(conversation_id)]
    assert len(ids) == 500
    resolved = ReferenceResolver(database, repository).resolve(conversation_id, "这些", selected_file_ids=ids)
    assert resolved["count"] == 500 and resolved["file_ids"] == ids
    database.close()
