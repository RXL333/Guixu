from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from guixu.application.conversational_undo import ConversationalUndoService, UndoError
from guixu.application.plan_compiler import PlanCompiler
from guixu.application.recovery import RecoveryService
from guixu.application.session_recovery import SessionRecoveryService
from guixu.domain.plans import PlanCandidate
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.executor import FileOperationExecutor
from guixu.infrastructure.filesystem.identity import read_identity


def _environment(project_root: Path, tmp_path: Path, count: int = 3):
    root = tmp_path / "workspace"
    source = root / "原始"
    output = root / "整理后"
    source.mkdir(parents=True)
    output.mkdir()
    database = Database(tmp_path / "data" / "app.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    tasks = TaskRepository(database)
    conversations = ConversationRepository(database)
    journal = SqliteOperationJournal(database)
    task = tasks.create("undo fixture", TaskSettings(operation_mode="preview_move", max_depth=2), {})
    scope_id = str(uuid.uuid4())
    with database.begin() as connection:
        connection.execute(text("""
            INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
            VALUES(:id,:task,'whole_tree',:root,:root,'workspace','{}')
        """), {"id": scope_id, "task": task["id"], "root": str(root)})
    candidates = []
    file_ids = []
    for index in range(count):
        path = source / f"file-{index}.txt"
        path.write_text(f"content-{index}", encoding="utf-8")
        identity = read_identity(path)
        file_id = str(uuid.uuid4())
        file_ids.append(file_id)
        with database.begin() as connection:
            connection.execute(text("""
                INSERT INTO files(id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,
                  extension,modality,mime,size_bytes,mtime_ns,volume_id,filesystem_file_id,sha256,scan_status,
                  metadata_json,created_at,updated_at)
                VALUES(:id,:task,:scope,:path,:path,:key,:relative,:name,'.txt','text','text/plain',:size,:mtime,
                  :volume,:fsid,:sha,'eligible','{}',datetime('now'),datetime('now'))
            """), {"id": file_id, "task": task["id"], "scope": scope_id, "path": str(path),
                    "key": str(path).casefold(), "relative": str(path.relative_to(root)), "name": path.name,
                    "size": identity.size_bytes, "mtime": identity.mtime_ns, "volume": identity.volume_id,
                    "fsid": identity.file_id, "sha": identity.sha256})
        candidates.append(PlanCandidate(file_id, path, root, root, "organized", ("整理后",), "text"))
    forward = PlanCompiler().compile(task_id=task["id"], version=1, operation_mode="preview_move",
                                     settings_hash=task["settings_hash"], taxonomy_hashes=("a" * 64,),
                                     candidates=candidates, max_depth=2)
    journal.persist_plan(forward, task["revision"])
    journal.approve(forward.plan_id, forward.plan_hash, task["revision"])
    conversation = conversations.create("可撤销整理", scope={"source_root": str(root), "display_name": "workspace",
                                                              "authorization_ref": "test"})
    for file_id in file_ids:
        conversations.attach_file(conversation["id"], file_id)
    version = conversations.create_plan_version(conversation["id"], expected_context_revision=1,
                                                 basis_context_revision=1, plan_id=forward.plan_id,
                                                 plan_hash=forward.plan_hash, status="PROPOSED",
                                                 summary="第一次整理", affected_file_count=count)
    execution = conversations.create_execution_round(conversation["id"], version["id"], forward.plan_id,
                                                      expected_context_revision=2, status="RUNNING",
                                                      affected_file_count=count)
    FileOperationExecutor(journal).execute(forward, forward.plan_hash)
    conversations.complete_execution_round(execution["id"], summary={"description": "第一次整理完成"})
    return database, tasks, conversations, journal, ConversationalUndoService(database, journal), conversation["id"], execution, file_ids, source, output


def test_latest_undo_requires_preview_and_preserves_history(project_root: Path, tmp_path: Path):
    database, _, conversations, _, service, conversation_id, execution, file_ids, source, output = _environment(project_root, tmp_path)
    before_revision = conversations.get_context(conversation_id)["file_state_revision"]
    result = service.request(conversation_id, user_message="撤销刚才那次调整。")
    preview = result["undo_plan"]
    assert result["target"]["execution_round_id"] == execution["id"]
    assert preview["status"] == "WAITING_FOR_APPROVAL"
    assert len(preview["items"]) == 3
    assert not any(source.iterdir()) and len(list(output.iterdir())) == 3

    service.approve(conversation_id, preview["id"], preview["plan_hash"], {"surface": "test"})
    completed = service.execute(conversation_id, preview["id"], preview["plan_hash"])
    assert completed["status"] == "COMPLETED"
    assert len(list(source.iterdir())) == 3 and not any(output.iterdir())
    rounds = conversations.list_execution_rounds(conversation_id)
    assert [row["round_kind"] for row in rounds] == ["FORWARD", "UNDO"]
    assert rounds[0]["undo_state"] == "FULLY_UNDONE" and rounds[1]["target_execution_round_id"] == execution["id"]
    assert conversations.get_context(conversation_id)["file_state_revision"] == before_revision + 1
    for file_id in file_ids:
        assert Path(conversations.get_conversation_file(conversation_id, file_id)["current_known_path"]).parent == source
    database.close()


def test_conversation_soft_delete_preserves_disk_journal_and_undo(project_root: Path, tmp_path: Path):
    database, _, conversations, journal, undo_service, conversation_id, execution, _, source, output = _environment(
        project_root, tmp_path, count=2
    )
    workspace = source.parent

    def disk_snapshot():
        return sorted(
            (path.relative_to(workspace).as_posix(), read_identity(path).sha256)
            for path in workspace.rglob("*")
            if path.is_file()
        )

    before_disk = disk_snapshot()
    with database.engine.connect() as connection:
        before_journal = connection.execute(text("""
            SELECT COUNT(*), SUM(CASE WHEN state='COMMITTED' THEN 1 ELSE 0 END)
            FROM operations
        """)).one()
        before_events = connection.execute(text("SELECT COUNT(*) FROM operation_events")).scalar_one()
    assert before_disk and before_journal[0] == before_journal[1] > 0 and before_events > 0

    deleted = conversations.soft_delete(conversation_id)
    assert deleted["status"] == "DELETED" and deleted["deleted_at"]
    assert conversations.list("active") == []
    assert [item["id"] for item in conversations.list("deleted")] == [conversation_id]
    assert disk_snapshot() == before_disk
    with database.engine.connect() as connection:
        after_journal = connection.execute(text("""
            SELECT COUNT(*), SUM(CASE WHEN state='COMMITTED' THEN 1 ELSE 0 END)
            FROM operations
        """)).one()
        after_events = connection.execute(text("SELECT COUNT(*) FROM operation_events")).scalar_one()
        retained_round = connection.execute(text(
            "SELECT COUNT(*) FROM conversation_execution_rounds WHERE id=:id"
        ), {"id": execution["id"]}).scalar_one()
    assert tuple(after_journal) == tuple(before_journal)
    assert after_events == before_events and retained_round == 1

    restored = conversations.restore(conversation_id)
    assert restored["status"] == "ACTIVE"
    preview = undo_service.request(conversation_id, user_message="撤销刚才那次整理。")["undo_plan"]
    assert preview["status"] == "WAITING_FOR_APPROVAL"
    assert disk_snapshot() == before_disk
    assert output.exists()
    database.close()


def test_partial_undo_and_double_confirm_are_idempotent(project_root: Path, tmp_path: Path):
    database, _, conversations, _, service, conversation_id, execution, file_ids, source, output = _environment(project_root, tmp_path)
    preview = service.request(conversation_id, user_message="只把这几个恢复回去。",
                              referenced_file_ids=file_ids[:2])["undo_plan"]
    service.approve(conversation_id, preview["id"], preview["plan_hash"])
    first = service.execute(conversation_id, preview["id"], preview["plan_hash"])
    second = service.execute(conversation_id, preview["id"], preview["plan_hash"])
    assert first["execution_round_id"] == second["execution_round_id"]
    assert len(list(source.iterdir())) == 2 and len(list(output.iterdir())) == 1
    target = conversations.get_execution_round(execution["id"])
    assert target["undo_state"] == "PARTIALLY_UNDONE" and target["undone_file_count"] == 2
    database.close()


@pytest.mark.parametrize(("mutation", "code"), [
    ("modify", "UNDO_SOURCE_MODIFIED"),
    ("occupy", "UNDO_TARGET_CONFLICT"),
    ("move", "FILE_MOVED_EXTERNALLY"),
])
def test_external_changes_are_blocked_in_preview(project_root: Path, tmp_path: Path, mutation: str, code: str):
    database, _, _, _, service, conversation_id, _, file_ids, source, output = _environment(project_root, tmp_path, 1)
    moved = output / "file-0.txt"
    if mutation == "modify":
        moved.write_text("changed outside", encoding="utf-8")
    elif mutation == "occupy":
        (source / "file-0.txt").write_text("new occupant", encoding="utf-8")
    else:
        external = output / "manual"
        external.mkdir()
        moved.rename(external / moved.name)
        with database.begin() as connection:
            connection.execute(text("UPDATE conversation_files SET current_known_path=:path WHERE conversation_id=:conversation AND file_id=:file"),
                               {"path": str(external / moved.name), "conversation": conversation_id, "file": file_ids[0]})
    preview = service.request(conversation_id, user_message="撤销上一次整理")["undo_plan"]
    assert preview["status"] == "BLOCKED"
    assert preview["items"][0]["block_reason"] == code
    database.close()


def test_historical_dependency_blocks_older_round(project_root: Path, tmp_path: Path):
    database, tasks, conversations, journal, service, conversation_id, first_round, file_ids, _, output = _environment(project_root, tmp_path, 2)
    root = output.parent
    later_dir = root / "再次调整"
    later_dir.mkdir()
    task = tasks.get(journal.load_plan(first_round["execution_plan_id"]).task_id)
    current = output / "file-0.txt"
    later = PlanCompiler().compile(task_id=task["id"], version=2, operation_mode="preview_move",
                                   settings_hash=task["settings_hash"], taxonomy_hashes=("a" * 64,),
                                   candidates=[PlanCandidate(file_ids[0], current, root, root, "later", ("再次调整",), "text")], max_depth=2)
    journal.persist_plan(later, task["revision"])
    journal.approve(later.plan_id, later.plan_hash, task["revision"])
    context = conversations.get_context(conversation_id)
    version = conversations.create_plan_version(conversation_id, expected_context_revision=context["context_revision"],
                                                 basis_context_revision=context["context_revision"], plan_id=later.plan_id,
                                                 plan_hash=later.plan_hash, status="PROPOSED", summary="第二次调整", affected_file_count=1)
    context = conversations.get_context(conversation_id)
    round2 = conversations.create_execution_round(conversation_id, version["id"], later.plan_id,
                                                  expected_context_revision=context["context_revision"], status="RUNNING", affected_file_count=1)
    FileOperationExecutor(journal).execute(later, later.plan_hash)
    conversations.complete_execution_round(round2["id"])
    preview = service.request(conversation_id, user_message="撤销第一次整理")["undo_plan"]
    assert preview["status"] == "BLOCKED"
    blocked = {item["file_id"] for item in preview["items"] if item["status"] == "BLOCKED_DEPENDENCY"}
    assert blocked == {file_ids[0]}
    database.close()


def test_real_twenty_file_conversational_undo_smoke(project_root: Path, tmp_path: Path):
    database, tasks, conversations, journal, service, conversation_id, round1, file_ids, _, output = _environment(project_root, tmp_path, 20)
    root = output.parent

    def execute_next(names: list[int], folder: str, version_number: int):
        task = tasks.get(journal.load_plan(round1["execution_plan_id"]).task_id)
        candidates = [PlanCandidate(file_ids[index], Path(tasks.get_file(task["id"], file_ids[index])["current_path"]), root, root,
                                    folder, (folder,), "text") for index in names]
        plan = PlanCompiler().compile(task_id=task["id"], version=version_number, operation_mode="preview_move",
                                      settings_hash=task["settings_hash"], taxonomy_hashes=("a" * 64,),
                                      candidates=candidates, max_depth=2)
        journal.persist_plan(plan, task["revision"])
        journal.approve(plan.plan_id, plan.plan_hash, task["revision"])
        context = conversations.get_context(conversation_id)
        version = conversations.create_plan_version(conversation_id, expected_context_revision=context["context_revision"],
                                                     basis_context_revision=context["context_revision"], plan_id=plan.plan_id,
                                                     plan_hash=plan.plan_hash, status="PROPOSED", summary=folder,
                                                     affected_file_count=len(names))
        context = conversations.get_context(conversation_id)
        execution = conversations.create_execution_round(conversation_id, version["id"], plan.plan_id,
                                                          expected_context_revision=context["context_revision"], status="RUNNING",
                                                          affected_file_count=len(names))
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)
        return conversations.complete_execution_round(execution["id"])

    round2 = execute_next(list(range(5)), "局部调整", 2)
    task_id = journal.load_plan(round1["execution_plan_id"]).task_id
    before_others = {index: Path(tasks.get_file(task_id, file_ids[index])["current_path"]) for index in range(5, 20)}
    preview = service.request(conversation_id, user_message="撤销刚才那次调整。")
    assert preview["target"]["execution_round_id"] == round2["id"]
    assert preview["undo_plan"]["summary"]["ready"] == 5
    assert len(list((root / "局部调整").glob("*.txt"))) == 5
    plan = preview["undo_plan"]
    service.approve(conversation_id, plan["id"], plan["plan_hash"])
    service.execute(conversation_id, plan["id"], plan["plan_hash"])
    assert len(list(output.glob("*.txt"))) == 20
    assert all(Path(tasks.get_file(task_id, file_ids[index])["current_path"]) == before_others[index] for index in range(5, 20))

    continued = execute_next([0, 1], "新分类", 4)
    assert continued["round_number"] == 4
    assert len(list((root / "新分类").glob("*.txt"))) == 2
    assert len(conversations.list_execution_rounds(conversation_id)) == 4
    database.close()


def test_undo_process_crash_after_four_restores_resumes_six_without_replay(project_root: Path, tmp_path: Path):
    database, _, conversations, journal, service, conversation_id, forward_round, _, source, output = _environment(
        project_root, tmp_path, 10
    )
    preview = service.request(conversation_id, user_message="撤销刚才那次整理。")["undo_plan"]
    service.approve(conversation_id, preview["id"], preview["plan_hash"])
    database_path = tmp_path / "data" / "app.sqlite3"
    helper = project_root / "backend" / "tests" / "helpers" / "crash_conversation_undo.py"
    database.close()

    crashed = subprocess.run(
        [sys.executable, str(helper), str(project_root), str(database_path), conversation_id,
         preview["id"], preview["plan_hash"], "4"],
        cwd=project_root / "backend", check=False, timeout=30,
    )
    assert crashed.returncode == 91

    reopened = Database(database_path, project_root / "contracts" / "database.sql")
    conversations = ConversationRepository(reopened)
    journal = SqliteOperationJournal(reopened)
    recovery = SessionRecoveryService(reopened, conversations, journal)
    startup = recovery.audit_startup()
    interrupted = ConversationalUndoService(reopened, journal).get(preview["id"])
    assert startup["execution_rounds_recovery_required"] == 1
    assert interrupted["status"] == "RECOVERY_REQUIRED"
    undo_round = conversations.get_execution_round(interrupted["execution_round_id"])
    assert undo_round["status"] == "RECOVERY_REQUIRED"
    states = [row["state"] for row in journal.operation_results(interrupted["core_plan_id"])]
    assert states.count("UNDONE") == 4
    assert states.count("PLANNED") == 6
    assert len(list(source.iterdir())) == 4
    assert len(list(output.iterdir())) == 6

    resumed = ConversationalUndoService(reopened, journal).execute(
        conversation_id, preview["id"], preview["plan_hash"]
    )
    assert resumed["status"] == "COMPLETED"
    assert len(list(source.iterdir())) == 10
    assert not any(output.iterdir())
    final_states = [row["state"] for row in journal.operation_results(interrupted["core_plan_id"])]
    assert final_states.count("UNDONE") == 10
    assert conversations.get_execution_round(forward_round["id"])["undo_state"] == "FULLY_UNDONE"
    assert len(conversations.list_execution_rounds(conversation_id)) == 2
    reopened.close()


def test_execution_process_crash_after_eight_moves_recovers_remaining_twelve(project_root: Path, tmp_path: Path):
    database, tasks, conversations, journal, _, conversation_id, first_round, file_ids, _, output = _environment(
        project_root, tmp_path, 20
    )
    root = output.parent
    task_id = journal.load_plan(first_round["execution_plan_id"]).task_id
    task = tasks.get(task_id)
    candidates = [
        PlanCandidate(file_id, Path(tasks.get_file(task_id, file_id)["current_path"]), root, root,
                      "再次整理", ("再次整理",), "text")
        for file_id in file_ids
    ]
    plan = PlanCompiler().compile(task_id=task_id, version=2, operation_mode="preview_move",
                                  settings_hash=task["settings_hash"], taxonomy_hashes=("b" * 64,),
                                  candidates=candidates, max_depth=2)
    journal.persist_plan(plan, task["revision"])
    journal.approve(plan.plan_id, plan.plan_hash, task["revision"])
    context = conversations.get_context(conversation_id)
    current_version = conversations.get_current_plan_version(conversation_id)
    version = conversations.create_plan_version(
        conversation_id, expected_context_revision=context["context_revision"],
        basis_context_revision=context["context_revision"], basis_file_state_revision=context["file_state_revision"],
        parent_plan_version_id=current_version["id"], baseline_execution_round_id=first_round["id"],
        plan_kind="DELTA", plan_id=plan.plan_id, plan_hash=plan.plan_hash,
        status="PROPOSED", summary="第二轮整理", affected_file_count=20,
    )
    context = conversations.get_context(conversation_id)
    conversations.approve_plan_version(
        conversation_id, version["id"], expected_context_revision=context["context_revision"],
        plan_hash=plan.plan_hash, authorization={"surface": "test"},
    )
    context = conversations.get_context(conversation_id)
    execution_round = conversations.request_execution(
        conversation_id, version["id"], expected_context_revision=context["context_revision"],
        plan_hash=plan.plan_hash, status="RUNNING", affected_file_count=20,
    )
    database_path = tmp_path / "data" / "app.sqlite3"
    helper = project_root / "backend" / "tests" / "helpers" / "crash_operation.py"
    database.close()

    crashed = subprocess.run(
        [sys.executable, str(helper), str(project_root), str(database_path), plan.plan_id, "COMMITTED", "8"],
        cwd=project_root / "backend", check=False, timeout=30,
    )
    assert crashed.returncode == 91

    reopened = Database(database_path, project_root / "contracts" / "database.sql")
    conversations = ConversationRepository(reopened)
    journal = SqliteOperationJournal(reopened)
    startup = SessionRecoveryService(reopened, conversations, journal).audit_startup()
    assert startup["execution_rounds_recovery_required"] == 1
    interrupted = conversations.get_execution_round(execution_round["id"])
    assert interrupted["status"] == "RECOVERY_REQUIRED"
    operations = journal.operation_results(plan.plan_id)
    assert sum(row["state"] == "COMMITTED" for row in operations) == 8
    assert sum(row["state"] == "PLANNED" for row in operations) == 12
    assert len(list((root / "再次整理").glob("*.txt"))) == 8
    assert len(list(output.glob("*.txt"))) == 12

    recovered = RecoveryService(journal).recover(journal.load_plan(plan.plan_id))
    assert recovered["retried"] == 12
    states = [row["state"] for row in journal.operation_results(plan.plan_id)]
    assert states.count("COMMITTED") == 20
    assert len(list((root / "再次整理").glob("*.txt"))) == 20
    assert not any(output.iterdir())
    completed = conversations.complete_execution_round(execution_round["id"], summary={"recovered": True})
    assert completed["status"] == "COMPLETED"
    assert conversations.get_execution_round(first_round["id"])["status"] == "COMPLETED"
    assert conversations.get_context(conversation_id)["current_execution_round_id"] == execution_round["id"]
    for file_id in file_ids:
        assert Path(conversations.get_conversation_file(conversation_id, file_id)["current_known_path"]).parent == root / "再次整理"
    reopened.close()
