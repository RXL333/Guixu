from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from guixu.application.plan_compiler import PlanCompiler, verify_plan_hash
from guixu.domain.plans import PlanCandidate
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.filesystem.executor import FileOperationExecutor
from guixu.application.recovery import RecoveryService


def make_database(project_root: Path, tmp_path: Path) -> Database:
    database = Database(tmp_path / "journal.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    return database


def seed_task_and_file(database: Database, source: Path) -> tuple[str, str]:
    task_id, scope_id, file_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    now = utc_now(); settings_hash = "a" * 64
    with database.begin() as connection:
        connection.execute(text("""
          INSERT INTO tasks(id,name,status,phase,settings_json,settings_hash,created_at,updated_at)
          VALUES(:id,'journal-test','AWAITING_EXECUTION_APPROVAL','PREVIEW','{}',:hash,:now,:now)
        """), {"id": task_id, "hash": settings_hash, "now": now})
        connection.execute(text("""
          INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name)
          VALUES(:id,:task,'whole_tree',:root,:root,'test')
        """), {"id": scope_id, "task": task_id, "root": str(source.parent)})
        info = source.stat()
        connection.execute(text("""
          INSERT INTO files(
            id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,extension,
            modality,size_bytes,mtime_ns,scan_status,created_at,updated_at
          ) VALUES(:id,:task,:scope,:path,:path,:key,:relative,:name,:ext,'text',:size,:mtime,'eligible',:now,:now)
        """), {"id": file_id, "task": task_id, "scope": scope_id, "path": str(source),
                 "key": str(source).casefold(), "relative": source.name, "name": source.name,
                 "ext": source.suffix, "size": info.st_size, "mtime": info.st_mtime_ns, "now": now})
    return task_id, file_id


def compile_for(database: Database, source: Path, destination: Path, task_id: str, file_id: str):
    candidate = PlanCandidate(file_id, source, source.parent, destination, "docs", ("文档",), "text")
    return PlanCompiler().compile(
        task_id=task_id, version=1, operation_mode="copy", settings_hash="a" * 64,
        taxonomy_hashes=("b" * 64,), candidates=[candidate], max_depth=2,
    )


def test_persistent_approval_events_and_repeat_execute(project_root: Path, tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "destination"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("persistent")
    database = make_database(project_root, tmp_path); task_id, file_id = seed_task_and_file(database, source)
    plan = compile_for(database, source, destination, task_id, file_id)
    journal = SqliteOperationJournal(database); journal.persist_plan(plan)
    with pytest.raises(ValueError, match="PLAN_HASH_MISMATCH"):
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    journal.approve(plan.plan_id, plan.plan_hash)
    executor = FileOperationExecutor(journal); executor.execute(plan, plan.plan_hash)
    executor.execute(plan, plan.plan_hash)
    with database.engine.connect() as connection:
        operation = connection.execute(
            text("SELECT state FROM operations WHERE id=:id"), {"id": plan.operations[0].operation_id}
        ).scalar_one()
        events = connection.execute(
            text("SELECT seq,event_type FROM operation_events WHERE operation_id=:id ORDER BY seq"),
            {"id": plan.operations[0].operation_id},
        ).all()
        status = connection.execute(text("SELECT status FROM plans WHERE id=:id"), {"id": plan.plan_id}).scalar_one()
    assert operation == "COMMITTED" and status == "finished"
    assert [event for _, event in events] == ["PREPARED", "COPYING", "TEMP_WRITTEN", "VERIFIED", "PUBLISHED", "COMMITTED"]
    assert [seq for seq, _ in events] == list(range(1, 7))
    database.close()


def test_reloaded_plan_retains_skip_reason_in_approved_hash(project_root: Path, tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "destination"
    source_dir.mkdir(); destination.mkdir()
    source = source_dir / "uncertain.jpg"; source.write_bytes(b"sample")
    database = make_database(project_root, tmp_path)
    task_id, file_id = seed_task_and_file(database, source)
    plan = PlanCompiler().compile(
        task_id=task_id, version=1, operation_mode="preview_move", settings_hash="a" * 64,
        taxonomy_hashes=("b" * 64,),
        candidates=[PlanCandidate(file_id, source, source_dir, destination, None, (), "image")],
        max_depth=2,
    )
    journal = SqliteOperationJournal(database)
    journal.persist_plan(plan)
    reloaded = journal.load_plan(plan.plan_id)
    assert reloaded.operations[0].reason == "UNSUPPORTED_OR_UNDECIDED"
    assert verify_plan_hash(reloaded)
    journal.approve(plan.plan_id, plan.plan_hash)
    assert FileOperationExecutor(journal).execute(reloaded, plan.plan_hash)
    assert source.exists()
    database.close()


def test_wrong_approval_hash_is_rejected(project_root: Path, tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "destination"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("data")
    database = make_database(project_root, tmp_path); task_id, file_id = seed_task_and_file(database, source)
    plan = compile_for(database, source, destination, task_id, file_id)
    journal = SqliteOperationJournal(database); journal.persist_plan(plan)
    with pytest.raises(ValueError, match="PLAN_HASH_MISMATCH"):
        journal.approve(plan.plan_id, "0" * 64)
    assert not (destination / "文档" / "a.txt").exists()
    database.close()


def test_plan_basis_revision_and_approval_state_are_independent(project_root: Path, tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "destination"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("data")
    database = make_database(project_root, tmp_path); task_id, file_id = seed_task_and_file(database, source)
    plan = compile_for(database, source, destination, task_id, file_id)
    journal = SqliteOperationJournal(database); journal.persist_plan(plan, 1)
    before = journal.plan_metadata(plan.plan_id)
    journal.approve(plan.plan_id, plan.plan_hash, 1)
    approved = journal.plan_metadata(plan.plan_id)
    assert before["plan_basis_revision"] == 1 and before["approved"] is False
    assert approved["plan_basis_revision"] == 1 and approved["approved_task_revision"] == 1 and approved["approved"] is True
    journal.assert_execution_ready(task_id, plan.plan_id, plan.plan_hash, 1)
    with database.begin() as connection:
        connection.execute(text("UPDATE tasks SET revision=revision+1 WHERE id=:id"), {"id": task_id})
    with pytest.raises(ValueError, match="REVISION_CONFLICT"):
        journal.assert_execution_ready(task_id, plan.plan_id, plan.plan_hash, 1)
    database.close()


class InjectedCrash(RuntimeError):
    pass


class FaultJournal:
    def __init__(self, delegate: SqliteOperationJournal, state: str):
        self.delegate = delegate
        self.crash_state = state
        self.triggered = False

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def transition(self, operation, state, payload=None):
        self.delegate.transition(operation, state, payload)
        if state == self.crash_state and not self.triggered:
            self.triggered = True
            raise InjectedCrash(state)


@pytest.mark.parametrize("crash_state", ["PREPARED", "COPYING", "TEMP_WRITTEN", "VERIFIED", "PUBLISHED", "COMMITTED"])
def test_op05_persistent_checkpoint_crash_recovery(project_root: Path, tmp_path: Path, crash_state: str):
    case = tmp_path / crash_state.lower(); source_dir, destination = case / "source", case / "destination"
    source_dir.mkdir(parents=True); destination.mkdir(); source = source_dir / "a.bin"; source.write_bytes(b"recovery" * 8192)
    database = Database(case / "journal.sqlite3", project_root / "contracts" / "database.sql"); database.initialize()
    task_id, file_id = seed_task_and_file(database, source)
    plan = compile_for(database, source, destination, task_id, file_id)
    journal = SqliteOperationJournal(database); journal.persist_plan(plan); journal.approve(plan.plan_id, plan.plan_hash)
    with pytest.raises(InjectedCrash, match=crash_state):
        FileOperationExecutor(FaultJournal(journal, crash_state), chunk_size=4096).execute(plan, plan.plan_hash)
    result = RecoveryService(SqliteOperationJournal(database)).recover(plan)
    target = Path(plan.operations[0].target_path or "")
    assert target.read_bytes() == source.read_bytes()
    assert SqliteOperationJournal(database).state(plan.operations[0].operation_id) == "COMMITTED"
    assert sum(result.values()) <= 1
    database.close()


@pytest.mark.parametrize("crash_state", ["PREPARED", "COPYING", "TEMP_WRITTEN", "VERIFIED", "PUBLISHED", "COMMITTED"])
def test_op05_real_process_exit_and_restart_recovery(project_root: Path, tmp_path: Path, crash_state: str):
    case = tmp_path / f"process-{crash_state.lower()}"
    source_dir, destination = case / "source", case / "destination"
    source_dir.mkdir(parents=True)
    destination.mkdir()
    source = source_dir / "a.bin"
    source.write_bytes(b"process-crash" * 8192)
    database_path = case / "journal.sqlite3"
    database = Database(database_path, project_root / "contracts" / "database.sql")
    database.initialize()
    task_id, file_id = seed_task_and_file(database, source)
    plan = compile_for(database, source, destination, task_id, file_id)
    journal = SqliteOperationJournal(database)
    journal.persist_plan(plan)
    journal.approve(plan.plan_id, plan.plan_hash)
    database.close()
    worker = project_root / "backend" / "tests" / "helpers" / "crash_operation.py"
    completed = subprocess.run(
        [sys.executable, str(worker), str(project_root), str(database_path), plan.plan_id, crash_state],
        cwd=project_root / "backend",
        check=False,
        timeout=20,
    )
    assert completed.returncode == 91
    reopened = Database(database_path, project_root / "contracts" / "database.sql")
    result = RecoveryService(SqliteOperationJournal(reopened)).recover(plan)
    target = Path(plan.operations[0].target_path or "")
    assert source.exists() and target.read_bytes() == source.read_bytes()
    assert SqliteOperationJournal(reopened).state(plan.operations[0].operation_id) == "COMMITTED"
    assert sum(result.values()) <= 1
    reopened.close()
