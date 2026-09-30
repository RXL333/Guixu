from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from sqlalchemy import text

from guixu.application import post_execution

from guixu.application.post_execution import WorkspaceStateService
from guixu.application.semantic_cache import EvidenceCacheService
from guixu.application.session_recovery import (
    RecoveryValidationService,
    SessionRecoveryService,
    WorkspaceReconciliationService,
)
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository, canonical_json
from guixu.infrastructure.filesystem.identity import read_identity


def _fixture(project_root: Path, tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    paths = [root / "a.txt", root / "b.txt", root / "c.txt", root / "d.txt"]
    for index, path in enumerate(paths):
        path.write_text(f"file-{index}", encoding="utf-8")
    database = Database(tmp_path / "data" / "app.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    tasks = TaskRepository(database)
    repository = ConversationRepository(database)
    task = tasks.create("recovery", TaskSettings(operation_mode="preview_move"), {})
    scope_id = str(uuid.uuid4())
    now = utc_now()
    with database.begin() as connection:
        connection.execute(text("""
            INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
            VALUES(:id,:task,'whole_tree',:root,:root,'workspace','{}')
        """), {"id": scope_id, "task": task["id"], "root": str(root)})
        for path in paths:
            identity = read_identity(path)
            connection.execute(text("""
                INSERT INTO files(id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,
                  extension,modality,mime,size_bytes,mtime_ns,volume_id,filesystem_file_id,sha256,scan_status,
                  metadata_json,created_at,updated_at)
                VALUES(:id,:task,:scope,:path,:path,:key,:relative,:name,'.txt','text','text/plain',:size,:mtime,
                  :volume,:fsid,:sha,'eligible','{}',:now,:now)
            """), {"id": f"file-{path.stem}", "task": task["id"], "scope": scope_id,
                    "path": str(path), "key": str(path).casefold(), "relative": path.name,
                    "name": path.name, "size": identity.size_bytes, "mtime": identity.mtime_ns,
                    "volume": identity.volume_id, "fsid": identity.file_id, "sha": identity.sha256, "now": now})
    conversation = repository.create("恢复测试", scope={"source_root": str(root), "display_name": "workspace", "authorization_ref": "grant-1"})
    for path in paths:
        repository.attach_file(conversation["id"], f"file-{path.stem}")
    cache = EvidenceCacheService(database)
    journal = SqliteOperationJournal(database)
    return database, repository, conversation["id"], root, paths, cache, journal


def test_workspace_reconciliation_detects_external_changes_and_new_files(project_root: Path, tmp_path: Path):
    database, repository, conversation_id, root, paths, cache, journal = _fixture(project_root, tmp_path)
    try:
        renamed = root / "renamed.txt"
        paths[0].rename(renamed)
        moved_dir = root / "moved"
        moved_dir.mkdir()
        paths[1].rename(moved_dir / paths[1].name)
        paths[2].write_text("changed", encoding="utf-8")
        paths[3].unlink()
        (root / "new.txt").write_text("new", encoding="utf-8")
        result = WorkspaceReconciliationService(database, repository, cache).reconcile(conversation_id)
        assert result["renamed"] == 1
        assert result["moved"] == 1
        assert result["modified"] == 1
        assert result["missing"] == 1
        assert result["new_files"] == 1
        rows = {row["file_id"]: row for row in repository.list_conversation_files(conversation_id)}
        assert rows["file-a"]["state"] == "ACTIVE"
        assert rows["file-a"]["current_known_path"].endswith("renamed.txt")
        assert rows["file-c"]["state"] == "FILE_CHANGED"
        assert rows["file-d"]["state"] == "MISSING"
    finally:
        database.close()


def test_reconciliation_does_not_rehash_untouched_files(project_root: Path, tmp_path: Path, monkeypatch):
    """A turn that changes nothing must not re-read the whole library.

    The 5,001-file benchmark used tiny text fixtures, so an unconditional re-hash
    looked cheap there. On a real photo collection it turns every conversational turn
    into a full read of the library, so the guard is asserted directly: with the files
    untouched, no hash may be computed at all.
    """
    database, repository, conversation_id, root, paths, cache, journal = _fixture(project_root, tmp_path)
    try:
        workspace = WorkspaceStateService(database, repository)
        workspace.sync_workspace_state(conversation_id)

        hashed: list[str] = []
        original = post_execution.read_identity

        def counting_read_identity(path: Path):
            hashed.append(path.name)
            return original(path)

        monkeypatch.setattr(post_execution, "read_identity", counting_read_identity)
        result = workspace.sync_workspace_state(conversation_id)

        assert hashed == []
        assert result["workspace_changed"] is False
        assert all(item["state"] == "UNCHANGED" for item in result["sync_events"])
    finally:
        database.close()


def test_reconciliation_still_detects_a_same_name_edit_with_a_new_mtime(project_root: Path, tmp_path: Path):
    database, repository, conversation_id, root, paths, cache, journal = _fixture(project_root, tmp_path)
    try:
        workspace = WorkspaceStateService(database, repository)
        workspace.sync_workspace_state(conversation_id)

        # Same byte length as the original, so only the mtime gives the edit away.
        paths[2].write_text("file-9", encoding="utf-8")
        result = workspace.sync_workspace_state(conversation_id)

        rows = {row["file_id"]: row for row in repository.list_conversation_files(conversation_id)}
        assert rows["file-c"]["state"] == "FILE_CHANGED"
        assert [item["state"] for item in result["sync_events"] if item["file_id"] == "file-c"] == ["FILE_CHANGED"]
        assert result["workspace_changed"] is True
    finally:
        database.close()


def test_reconciliation_detects_a_content_edit_that_restores_size_and_mtime(project_root: Path, tmp_path: Path):
    """The documented limit of the stat guard: a forged mtime hides the edit here.

    This is why the executor re-hashes independently before moving anything; the
    matching assertion on that guarantee lives in
    `test_forged_mtime_still_fails_the_pre_move_identity_check`.
    """
    database, repository, conversation_id, root, paths, cache, journal = _fixture(project_root, tmp_path)
    try:
        workspace = WorkspaceStateService(database, repository)
        workspace.sync_workspace_state(conversation_id)
        before = repository.list_conversation_files(conversation_id)
        original = {row["file_id"]: (row["current_size_bytes"], row["current_mtime_ns"]) for row in before}

        paths[1].write_text("file-9", encoding="utf-8")
        size, mtime = original["file-b"]
        os.utime(paths[1], ns=(mtime, mtime))
        assert paths[1].stat().st_size == size

        result = workspace.sync_workspace_state(conversation_id)
        assert [item["state"] for item in result["sync_events"] if item["file_id"] == "file-b"] == ["UNCHANGED"]
    finally:
        database.close()


def test_agent_turns_are_interrupted_on_restart_without_replay(project_root: Path, tmp_path: Path):
    database, repository, conversation_id, root, paths, cache, journal = _fixture(project_root, tmp_path)
    service = SessionRecoveryService(database, repository, journal, cache)
    turn = service.create_agent_turn(conversation_id, turn_kind="ANALYSIS", status="RUNNING")
    database.close()
    reopened = Database(tmp_path / "data" / "app.sqlite3", project_root / "contracts" / "database.sql")
    reopened.initialize()
    try:
        service = SessionRecoveryService(reopened, ConversationRepository(reopened), SqliteOperationJournal(reopened), EvidenceCacheService(reopened))
        assert service.audit_startup()["agent_turns_interrupted"] == 1
        interrupted = service.get_agent_turn(turn["id"])
        assert interrupted["status"] == "INTERRUPTED"
        assert interrupted["interruption_code"] == "APP_RESTARTED_DURING_TURN"
        retry = service.retry_agent_turn(turn["id"])
        assert retry["status"] == "QUEUED"
        assert retry["retry_of_turn_id"] == turn["id"]
    finally:
        reopened.close()


def test_semantic_cache_survives_restart_and_scope_unavailable_keeps_history(project_root: Path, tmp_path: Path):
    database, repository, conversation_id, root, paths, cache, journal = _fixture(project_root, tmp_path)
    fingerprint = read_identity(paths[0]).sha256
    cache.store_evidence(file_id="file-a", content_fingerprint=fingerprint, evidence_kind="TEXT_EXTRACT",
                         payload={"text": "persisted"}, normalized_content="persisted",
                         producer_type="LOCAL_PARSER", producer_name="test")
    database.close()
    root.rename(tmp_path / "workspace-offline")
    reopened = Database(tmp_path / "data" / "app.sqlite3", project_root / "contracts" / "database.sql")
    reopened.initialize()
    try:
        repo = ConversationRepository(reopened)
        cache = EvidenceCacheService(reopened)
        assert cache.get_valid_evidence("file-a", fingerprint, "TEXT_EXTRACT")["normalized_content"] == "persisted"
        result = WorkspaceReconciliationService(reopened, repo, cache).reconcile(conversation_id)
        assert result["scope_status"] == "SCOPE_UNAVAILABLE"
        assert repo.get(conversation_id)["status"] == "ACTIVE"
        assert repo.list_messages(conversation_id) == []
    finally:
        reopened.close()


def test_plan_revalidation_blocks_modified_referenced_file(project_root: Path, tmp_path: Path):
    database, repository, conversation_id, root, paths, cache, journal = _fixture(project_root, tmp_path)
    now = utc_now()
    file_id = "file-a"
    plan_id = str(uuid.uuid4())
    identity = read_identity(paths[0])
    with database.begin() as connection:
        connection.execute(text("""
            INSERT INTO plans(id,task_id,version,plan_hash,plan_kind,status,operation_mode,settings_hash,
              taxonomy_hashes_json,source_snapshot_hash,plan_basis_revision,summary_json,created_at)
            SELECT :id,t.id,1,:hash,'forward','validated','preview_move',t.settings_hash,'[]',:snapshot,1,'{}',:now
            FROM tasks t WHERE t.id=(SELECT task_id FROM files WHERE id=:file)
        """), {"id": plan_id, "hash": "a" * 64, "snapshot": "b" * 64, "now": now, "file": file_id})
        connection.execute(text("""
            INSERT INTO operations(id,plan_id,file_id,ordinal,action,source_path,target_path,target_key,source_snapshot_json,
              expected_sha256,state,updated_at)
            VALUES(:id,:plan,:file,0,'move',:source,:target,:key,:snapshot,:sha,'PLANNED',:now)
        """), {"id": str(uuid.uuid4()), "plan": plan_id, "file": file_id, "source": str(paths[0]),
                "target": str(root / "target.txt"), "key": str(root / "target.txt").casefold(),
                "snapshot": canonical_json({"volume_id": identity.volume_id, "file_id": identity.file_id,
                                             "size_bytes": identity.size_bytes, "mtime_ns": identity.mtime_ns,
                                             "sha256": identity.sha256, "link_count": identity.link_count}),
                "sha": identity.sha256, "now": now})
    version = repository.create_plan_version(conversation_id, expected_context_revision=1,
                                             basis_context_revision=1, basis_file_state_revision=1,
                                             plan_id=plan_id, plan_hash="a" * 64, status="PROPOSED")
    paths[0].write_text("changed", encoding="utf-8")
    validation = RecoveryValidationService(database, repository, WorkspaceReconciliationService(database, repository, cache)).validate(conversation_id, version["id"])
    assert not validation["valid"]
    assert "PLAN_FILE_STATE_STALE" in validation["reason_codes"]
    database.close()
