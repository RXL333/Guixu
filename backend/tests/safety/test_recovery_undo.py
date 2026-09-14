from __future__ import annotations

import uuid
import os
from pathlib import Path

import pytest

from guixu.application.plan_compiler import PlanCompiler
from guixu.application.recovery import RecoveryService
from guixu.application.undo import UndoCompiler
from guixu.domain.plans import PlanCandidate, PlannedOperation
from guixu.infrastructure.filesystem.executor import FileOperationExecutor, move_no_clobber


class Journal:
    def __init__(self):
        self.states: dict[str, str] = {}
        self.events: list[tuple[str, str, dict[str, object]]] = []
        self.approved: dict[str, str] = {}

    def state(self, operation_id: str) -> str:
        return self.states.get(operation_id, "PLANNED")

    def transition(self, operation: PlannedOperation, state: str, payload=None) -> None:
        self.states[operation.operation_id] = state
        self.events.append((operation.operation_id, state, payload or {}))

    def record_directory(self, plan_id: str, path: Path) -> None:
        return None

    def approved_hash(self, plan_id: str) -> str | None:
        return self.approved.get(plan_id)

    def begin_execution(self, plan_id: str) -> None:
        return None

    def finish_plan(self, plan_id: str) -> None:
        return None


def plan_for(source: Path, destination: Path, mode="preview_move"):
    item = PlanCandidate(
        str(uuid.uuid4()), source, source.parent, destination, "docs", ("文档",), "text"
    )
    return PlanCompiler().compile(
        task_id=str(uuid.uuid4()), version=1, operation_mode=mode, settings_hash="a" * 64,
        taxonomy_hashes=("b" * 64,), candidates=[item], max_depth=2,
    )


def approve(journal: Journal, plan) -> None:
    journal.approved[plan.plan_id] = plan.plan_hash


def test_op05_recovery_after_publish_before_log_commit(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("recover")
    plan = plan_for(source, destination)
    operation = plan.operations[0]; target = Path(operation.target_path or "")
    target.parent.mkdir(parents=True); move_no_clobber(source, target)
    journal = Journal(); approve(journal, plan)
    result = RecoveryService(journal).recover(plan)
    assert result["committed"] == 1
    assert journal.state(operation.operation_id) == "COMMITTED"
    assert target.read_text() == "recover" and not source.exists()


def test_recovery_refuses_unknown_target_content(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("original")
    plan = plan_for(source, destination, "copy"); operation = plan.operations[0]
    target = Path(operation.target_path or ""); target.parent.mkdir(parents=True); target.write_text("outsider")
    journal = Journal(); approve(journal, plan)
    result = RecoveryService(journal).recover(plan)
    assert result["conflict"] == 1 and source.read_text() == "original" and target.read_text() == "outsider"


def test_op08_undo_move_restores_without_overwrite(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("restore")
    forward = plan_for(source, destination); journal = Journal(); approve(journal, forward)
    FileOperationExecutor(journal).execute(forward, forward.plan_hash)
    undo = UndoCompiler().compile(forward, {forward.operations[0].operation_id}, 2); approve(journal, undo)
    FileOperationExecutor(journal).execute(undo, undo.plan_hash)
    assert source.read_text() == "restore"
    assert not Path(forward.operations[0].target_path or "").exists()
    assert journal.state(undo.operations[0].operation_id) == "UNDONE"


def test_undo_move_conflicts_when_original_path_is_occupied(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("moved")
    forward = plan_for(source, destination); journal = Journal(); approve(journal, forward)
    FileOperationExecutor(journal).execute(forward, forward.plan_hash)
    undo = UndoCompiler().compile(forward, {forward.operations[0].operation_id}, 2)
    source.write_text("new occupant"); approve(journal, undo)
    FileOperationExecutor(journal).execute(undo, undo.plan_hash)
    assert source.read_text() == "new occupant"
    assert Path(forward.operations[0].target_path or "").read_text() == "moved"
    assert journal.state(undo.operations[0].operation_id) == "UNDO_CONFLICT"


def test_op09_undo_copy_recycles_only_unchanged_task_copy(tmp_path: Path, monkeypatch):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("copy")
    forward = plan_for(source, destination, "copy"); journal = Journal(); approve(journal, forward)
    FileOperationExecutor(journal).execute(forward, forward.plan_hash)
    copied = Path(forward.operations[0].target_path or "")
    undo = UndoCompiler().compile(forward, {forward.operations[0].operation_id}, 2); approve(journal, undo)
    monkeypatch.setattr("guixu.infrastructure.filesystem.executor.send2trash", lambda path: Path(path).unlink())
    FileOperationExecutor(journal).execute(undo, undo.plan_hash)
    assert source.read_text() == "copy" and not copied.exists()
    assert journal.state(undo.operations[0].operation_id) == "UNDONE"


def test_undo_copy_refuses_externally_modified_copy(tmp_path: Path, monkeypatch):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("copy")
    forward = plan_for(source, destination, "copy"); journal = Journal(); approve(journal, forward)
    FileOperationExecutor(journal).execute(forward, forward.plan_hash)
    copied = Path(forward.operations[0].target_path or "")
    undo = UndoCompiler().compile(forward, {forward.operations[0].operation_id}, 2)
    copied.write_text("external edit"); approve(journal, undo)
    called = False
    def fake_recycle(_: str):
        nonlocal called
        called = True
    monkeypatch.setattr("guixu.infrastructure.filesystem.executor.send2trash", fake_recycle)
    FileOperationExecutor(journal).execute(undo, undo.plan_hash)
    assert not called and copied.read_text() == "external edit"
    assert journal.state(undo.operations[0].operation_id) == "UNDO_CONFLICT"


def test_op10_repeated_undo_is_idempotent(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "a.txt"; source.write_text("once")
    forward = plan_for(source, destination); journal = Journal(); approve(journal, forward)
    FileOperationExecutor(journal).execute(forward, forward.plan_hash)
    undo = UndoCompiler().compile(forward, {forward.operations[0].operation_id}, 2); approve(journal, undo)
    executor = FileOperationExecutor(journal); executor.execute(undo, undo.plan_hash)
    count = len(journal.events); executor.execute(undo, undo.plan_hash)
    assert len(journal.events) == count and source.read_text() == "once"


@pytest.mark.skipif(os.name != "nt", reason="Windows recycle bin integration")
def test_op09_windows_recycle_bin_for_unchanged_copy(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "recycle-smoke.txt"; source.write_text("recyclable")
    forward = plan_for(source, destination, "copy"); journal = Journal(); approve(journal, forward)
    FileOperationExecutor(journal).execute(forward, forward.plan_hash)
    copied = Path(forward.operations[0].target_path or "")
    undo = UndoCompiler().compile(forward, {forward.operations[0].operation_id}, 2); approve(journal, undo)
    FileOperationExecutor(journal).execute(undo, undo.plan_hash)
    assert source.read_text() == "recyclable" and not copied.exists()
    assert journal.state(undo.operations[0].operation_id) == "UNDONE"
