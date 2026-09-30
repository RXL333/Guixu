"""S09 - stable file identity across undo, user moves, and restart.

A forward execution records where each file *was* and what it *contained*. An
undo run later has to put those files back. Between the two, the world moves:
the app restarts, the user renames a file, edits one, drops a new file where an
old one used to be.

The invariant: **undo acts only on the exact file it moved, and only when
nothing about it has changed.** Identity here is the pair (file_id, sha256) -
the row says which file, the hash says whether it is still the same bytes. Every
way the world can change under an undo must end in a BLOCKED_* status with the
file left alone, never in a move the user did not agree to.

The dangerous case worth naming: a user renames an organized file away and puts
something *else* at the organized path. A naive undo keyed on path alone would
happily move the impostor back to the original location, destroying it and
leaving the real file wherever the user put it. That is the test this file is
built around.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from guixu.application.conversational_undo import ConversationalUndoService, UndoError
from guixu.application.plan_compiler import PlanCompiler
from guixu.application.semantic_cache import EvidenceCacheService
from guixu.application.session_recovery import SessionRecoveryService
from guixu.domain.plans import PlanCandidate
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.executor import FileOperationExecutor
from guixu.infrastructure.filesystem.identity import read_identity, sha256_file


class World:
    """One running instance of the app's persistence layer.

    Restarting means closing this and building a new one on the same files. No
    Python object is shared across the boundary, so nothing can be "remembered"
    in memory - which is the point.
    """

    def __init__(self, database_path: Path, schema: Path) -> None:
        self.database = Database(database_path, schema)
        self.database.initialize()
        self.tasks = TaskRepository(self.database)
        self.conversations = ConversationRepository(self.database)
        self.journal = SqliteOperationJournal(self.database)
        self.undo = ConversationalUndoService(self.database, self.journal)

    def close(self) -> None:
        self.database.close()


def _forward_execution(project_root: Path, tmp_path: Path, count: int = 3):
    """Run one real forward execution, leaving `count` files in the output tree."""
    root = tmp_path / "workspace"
    source = root / "原始"
    output = root / "整理后"
    source.mkdir(parents=True)
    output.mkdir()
    database_path = tmp_path / "data" / "app.sqlite3"
    schema = project_root / "contracts" / "database.sql"

    world = World(database_path, schema)
    task = world.tasks.create("undo fixture", TaskSettings(operation_mode="preview_move", max_depth=2), {})
    scope_id = str(uuid.uuid4())
    with world.database.begin() as connection:
        connection.execute(text("""
            INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
            VALUES(:id,:task,'whole_tree',:root,:root,'workspace','{}')
        """), {"id": scope_id, "task": task["id"], "root": str(root)})

    candidates, file_ids = [], []
    for index in range(count):
        path = source / f"file-{index}.txt"
        path.write_text(f"content-{index}", encoding="utf-8")
        identity = read_identity(path)
        file_id = str(uuid.uuid4())
        file_ids.append(file_id)
        with world.database.begin() as connection:
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
    world.journal.persist_plan(forward, task["revision"])
    world.journal.approve(forward.plan_id, forward.plan_hash, task["revision"])
    conversation = world.conversations.create("可撤销整理", scope={"source_root": str(root),
                                                                 "display_name": "workspace",
                                                                 "authorization_ref": "test"})
    for file_id in file_ids:
        world.conversations.attach_file(conversation["id"], file_id)
    version = world.conversations.create_plan_version(
        conversation["id"], expected_context_revision=1, basis_context_revision=1,
        plan_id=forward.plan_id, plan_hash=forward.plan_hash, status="PROPOSED",
        summary="第一次整理", affected_file_count=count)
    execution = world.conversations.create_execution_round(
        conversation["id"], version["id"], forward.plan_id, expected_context_revision=2,
        status="RUNNING", affected_file_count=count)
    FileOperationExecutor(world.journal).execute(forward, forward.plan_hash)
    world.conversations.complete_execution_round(execution["id"], summary={"description": "整理完成"})

    assert not any(source.iterdir()) and len(list(output.iterdir())) == count
    return world, conversation["id"], file_ids, source, output, root, database_path, schema


def _statuses(result: dict) -> dict[str, str]:
    preview = result["undo_plan"]
    return {item["file_id"]: item["status"] for item in preview["items"]}


def test_s09_undo_after_a_restart_puts_every_file_back(project_root: Path, tmp_path: Path):
    """The plain combination: a restart must not strand an undo.

    This is the baseline the other cases are measured against. If identity were
    not durable, every file would come back BLOCKED_MISSING after a restart and
    the user would have no way to undo anything they did before closing the app.
    """
    world, conversation_id, file_ids, source, output, _, database_path, schema = _forward_execution(
        project_root, tmp_path)
    world.close()

    world = World(database_path, schema)
    try:
        result = world.undo.request(conversation_id, user_message="撤销刚才那次调整。")
        preview = result["undo_plan"]
        assert set(_statuses(result).values()) == {"READY"}

        world.undo.approve(conversation_id, preview["id"], preview["plan_hash"], {"surface": "test"})
        completed = world.undo.execute(conversation_id, preview["id"], preview["plan_hash"])
        assert completed["status"] == "COMPLETED"

        assert len(list(source.iterdir())) == len(file_ids)
        assert not any(output.iterdir())
        # The same file IDs, back at the paths they started from - identity
        # survived the restart, it was not re-derived from a fresh scan.
        for file_id in file_ids:
            tracked = world.conversations.get_conversation_file(conversation_id, file_id)
            assert Path(tracked["current_known_path"]).parent == source
    finally:
        world.close()


def test_s09_undo_after_a_restart_still_refuses_a_file_the_user_edited(project_root: Path, tmp_path: Path):
    """A restart must not reset the "has this changed?" question.

    The hash check is the only thing standing between an undo and the destruction
    of a user's edits. If restart bypassed it, the exact sequence "organize,
    close the app, edit a file, reopen, undo" would silently discard the edit.
    """
    world, conversation_id, file_ids, source, output, _, database_path, schema = _forward_execution(
        project_root, tmp_path)
    edited = output / "file-0.txt"
    edited.write_text("用户后来改过的内容", encoding="utf-8")
    world.close()

    world = World(database_path, schema)
    try:
        result = world.undo.request(conversation_id, user_message="撤销刚才那次调整。")
        statuses = _statuses(result)
        blocked = [status for status in statuses.values() if status != "READY"]
        assert blocked, f"a user edit was not detected across restart: {statuses}"
        assert set(blocked) <= {"BLOCKED_MODIFIED", "BLOCKED_EXTERNAL_MOVE"}
        # And the edit is still there - blocked means blocked, not "moved anyway".
        assert edited.read_text(encoding="utf-8") == "用户后来改过的内容"
    finally:
        world.close()


def test_s09_undo_never_moves_an_impostor_left_at_the_organized_path(project_root: Path, tmp_path: Path):
    """The case this whole file exists for.

    The user renames an organized file to something of their own, then creates a
    *different* file at the organized path. A path-keyed undo would move that
    new file back to the original location - destroying a file the user made and
    leaving their real file where they put it. Identity is the hash, so the undo
    must refuse instead.
    """
    world, conversation_id, file_ids, source, output, root, database_path, schema = _forward_execution(
        project_root, tmp_path, count=1)
    original_source = source / "file-0.txt"
    organized = output / "file-0.txt"

    # The user takes their file somewhere else entirely, and leaves a
    # different file behind at the organized path.
    moved_aside = root / "用户自己改的名字.dat"
    organized.rename(moved_aside)
    impostor = output / "file-0.txt"
    impostor.write_text("这是一个完全不同的新文件", encoding="utf-8")
    impostor_hash = sha256_file(impostor)

    result = world.undo.request(conversation_id, user_message="撤销刚才那次调整。")
    statuses = _statuses(result)
    assert all(status != "READY" for status in statuses.values()), (
        f"undo accepted an impostor as the original file: {statuses}")
    assert result["undo_plan"] is None or not any(
        item["status"] == "READY" for item in result["undo_plan"]["items"])

    # Nothing moved: the impostor is untouched at the organized path, and the
    # user's own file is still where they put it.
    assert impostor.exists() and sha256_file(impostor) == impostor_hash
    assert moved_aside.exists()
    assert not original_source.exists()
    world.close()


def test_s09_undo_refuses_to_overwrite_a_file_the_user_created_at_the_original_path(project_root: Path, tmp_path: Path):
    """The original location is occupied by something new - do not clobber it.

    `AGENTS.md` is explicit that existing files are never overwritten. The user
    re-creates `原始/file-0.txt` with their own content after the organizer
    emptied the folder; undoing must not destroy it.
    """
    world, conversation_id, _, source, output, _, _, _ = _forward_execution(project_root, tmp_path, count=1)
    occupied = source / "file-0.txt"
    occupied.write_text("用户后来新建的同名文件", encoding="utf-8")
    occupant_hash = sha256_file(occupied)

    result = world.undo.request(conversation_id, user_message="撤销刚才那次调整。")
    statuses = _statuses(result)
    assert "BLOCKED_TARGET_CONFLICT" in statuses.values(), statuses
    assert sha256_file(occupied) == occupant_hash
    assert (output / "file-0.txt").exists(), "the organized file must not be consumed by a blocked undo"
    world.close()


def test_s09_a_change_between_preview_and_execute_is_caught_after_a_restart(project_root: Path, tmp_path: Path):
    """A restart between preview and approval must not launder an old preview.

    The preview says READY. The app restarts. The user edits the file. Approving
    and executing the *same* preview must still refuse, because execution
    re-verifies the hash rather than trusting the preview it was handed.
    """
    world, conversation_id, file_ids, _, output, _, database_path, schema = _forward_execution(
        project_root, tmp_path, count=1)
    result = world.undo.request(conversation_id, user_message="撤销刚才那次调整。")
    preview = result["undo_plan"]
    assert preview["status"] == "WAITING_FOR_APPROVAL"
    assert set(_statuses(result).values()) == {"READY"}
    world.close()

    world = World(database_path, schema)
    try:
        target = output / "file-0.txt"
        target.write_text("重启之后才被改掉的内容", encoding="utf-8")

        # The refusal may land at approval or at execution - both re-verify the
        # hash rather than trusting the preview, and which one fires first is an
        # implementation detail. What matters is that the pair refuses.
        with pytest.raises(UndoError) as failure:
            world.undo.approve(conversation_id, preview["id"], preview["plan_hash"], {"surface": "test"})
            world.undo.execute(conversation_id, preview["id"], preview["plan_hash"])
        assert failure.value.code == "UNDO_SOURCE_MODIFIED", failure.value.code
        # The edit survives; the refusal is the whole behaviour.
        assert target.read_text(encoding="utf-8") == "重启之后才被改掉的内容"
    finally:
        world.close()


def test_s09_identity_survives_a_restart_that_also_interrupted_a_turn(project_root: Path, tmp_path: Path):
    """Restart recovery must not disturb the file records an undo depends on.

    A restart mid-turn is normal - the app is killed and relaunched. The undo
    that follows must still be able to identify its files, so this interrupts a
    turn, audits the restart, and only then undoes.
    """
    world, conversation_id, file_ids, source, output, _, database_path, schema = _forward_execution(
        project_root, tmp_path, count=2)
    service = SessionRecoveryService(world.database, world.conversations, world.journal,
                                     EvidenceCacheService(world.database))
    service.create_agent_turn(conversation_id, turn_kind="ANALYSIS", status="RUNNING")
    world.close()

    world = World(database_path, schema)
    try:
        recovered = SessionRecoveryService(world.database, world.conversations, world.journal,
                                           EvidenceCacheService(world.database))
        assert recovered.audit_startup()["agent_turns_interrupted"] == 1

        result = world.undo.request(conversation_id, user_message="撤销刚才那次调整。")
        preview = result["undo_plan"]
        assert set(_statuses(result).values()) == {"READY"}
        world.undo.approve(conversation_id, preview["id"], preview["plan_hash"], {"surface": "test"})
        completed = world.undo.execute(conversation_id, preview["id"], preview["plan_hash"])
        assert completed["status"] == "COMPLETED"
        assert len(list(source.iterdir())) == len(file_ids) and not any(output.iterdir())
    finally:
        world.close()
