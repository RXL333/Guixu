from __future__ import annotations

import uuid
from pathlib import Path
import errno
import os
import pytest

from guixu.application.plan_compiler import PlanCompiler
from guixu.domain.plans import PlanCandidate, PlannedOperation
from guixu.infrastructure.filesystem.executor import FileOperationExecutor
from guixu.infrastructure.filesystem.identity import sha256_file


class RecordingJournal:
    def __init__(self):
        self.states: dict[str, str] = {}
        self.events: list[tuple[str, str, dict[str, object]]] = []
        self.directories: list[Path] = []
        self.approved: dict[str, str] = {}

    def state(self, operation_id: str) -> str:
        return self.states.get(operation_id, "PLANNED")

    def transition(self, operation: PlannedOperation, state: str, payload=None) -> None:
        self.states[operation.operation_id] = state
        self.events.append((operation.operation_id, state, payload or {}))

    def record_directory(self, plan_id: str, path: Path) -> None:
        self.directories.append(path)

    def approved_hash(self, plan_id: str) -> str | None:
        return self.approved.get(plan_id)

    def begin_execution(self, plan_id: str) -> None:
        return None

    def finish_plan(self, plan_id: str) -> None:
        return None


def make_plan(source: Path, destination: Path, mode: str):
    item = PlanCandidate(
        file_id=str(uuid.uuid4()), source_path=source, source_root=source.parent,
        destination_root=destination, category_id="docs", category_segments=("文档",), modality="document",
    )
    return PlanCompiler().compile(
        task_id=str(uuid.uuid4()), version=1, operation_mode=mode, settings_hash="a" * 64,
        taxonomy_hashes=("b" * 64,), candidates=[item], max_depth=2,
    )


def test_op02_copy_preserves_source_and_hash(tmp_path: Path):
    source = tmp_path / "source" / "a.txt"; target = tmp_path / "target"
    source.parent.mkdir(); target.mkdir(); source.write_text("copy me")
    original_hash = sha256_file(source)
    plan = make_plan(source, target, "copy"); journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash
    FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    published = Path(plan.operations[0].target_path or "")
    assert source.exists() and sha256_file(source) == original_hash
    assert published.exists() and sha256_file(published) == original_hash
    assert journal.state(plan.operations[0].operation_id) == "COMMITTED"


def test_op03_move_is_no_clobber_and_repeat_is_idempotent(tmp_path: Path):
    source = tmp_path / "source" / "a.txt"; target = tmp_path / "target"
    source.parent.mkdir(); target.mkdir(); source.write_text("move me")
    plan = make_plan(source, target, "preview_move"); journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash; executor = FileOperationExecutor(journal)
    executor.execute(plan, plan.plan_hash)
    published = Path(plan.operations[0].target_path or "")
    assert not source.exists() and published.read_text() == "move me"
    event_count = len(journal.events)
    executor.execute(plan, plan.plan_hash)
    assert len(journal.events) == event_count


def test_op13_target_created_after_approval_conflicts(tmp_path: Path):
    source = tmp_path / "source" / "a.txt"; target = tmp_path / "target"
    source.parent.mkdir(); target.mkdir(); source.write_text("source")
    plan = make_plan(source, target, "copy")
    approved_target = Path(plan.operations[0].target_path or "")
    approved_target.parent.mkdir(parents=True); approved_target.write_text("outsider")
    journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash; FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert source.exists() and approved_target.read_text() == "outsider"
    assert journal.state(plan.operations[0].operation_id) == "CONFLICT"


def test_source_change_after_approval_conflicts(tmp_path: Path):
    source = tmp_path / "source" / "a.txt"; target = tmp_path / "target"
    source.parent.mkdir(); target.mkdir(); source.write_text("before")
    plan = make_plan(source, target, "copy"); source.write_text("after")
    journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash; FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert journal.state(plan.operations[0].operation_id) == "CONFLICT"
    assert not Path(plan.operations[0].target_path or "").exists()


def test_op11_disk_full_before_publish_preserves_source(tmp_path: Path, monkeypatch):
    source = tmp_path / "source" / "a.txt"; target = tmp_path / "target"
    source.parent.mkdir(); target.mkdir(); source.write_text("must survive")
    plan = make_plan(source, target, "copy"); journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash
    monkeypatch.setattr(os, "fsync", lambda _: (_ for _ in ()).throw(OSError(errno.ENOSPC, "disk full")))
    FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert source.read_text() == "must survive"
    assert not Path(plan.operations[0].target_path or "").exists()
    assert journal.state(plan.operations[0].operation_id) == "FAILED"


def test_op12_journal_failure_stops_before_disk_change(tmp_path: Path):
    source = tmp_path / "source" / "a.txt"; target = tmp_path / "target"
    source.parent.mkdir(); target.mkdir(); source.write_text("untouched")
    plan = make_plan(source, target, "preview_move")
    class FailingJournal(RecordingJournal):
        def transition(self, operation, state, payload=None):
            if state == "PREPARED":
                raise RuntimeError("database commit failed")
            super().transition(operation, state, payload)
    journal = FailingJournal(); journal.approved[plan.plan_id] = plan.plan_hash
    with pytest.raises(RuntimeError, match="database commit failed"):
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert source.read_text() == "untouched" and not Path(plan.operations[0].target_path or "").exists()


def test_op14_companion_preflight_blocks_entire_group_on_source_change(tmp_path: Path):
    source_dir, target = tmp_path / "source", tmp_path / "target"
    source_dir.mkdir(); target.mkdir(); first = source_dir / "clip.mp4"; second = source_dir / "clip.srt"
    first.write_text("video"); second.write_text("subtitle"); group = str(uuid.uuid4())
    candidates = [
        PlanCandidate(str(uuid.uuid4()), first, source_dir, target, "video", ("视频",), "video", companion_group_id=group),
        PlanCandidate(str(uuid.uuid4()), second, source_dir, target, "video", ("视频",), "video", companion_group_id=group),
    ]
    plan = PlanCompiler().compile(task_id=str(uuid.uuid4()), version=1, operation_mode="preview_move", settings_hash="a"*64, taxonomy_hashes=("b"*64,), candidates=candidates, max_depth=2)
    second.write_text("changed after approval")
    journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash
    FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert first.exists() and second.exists()
    assert {journal.state(item.operation_id) for item in plan.operations} == {"CONFLICT"}


def test_fs12_copy_rechecks_source_identity_before_publish(tmp_path: Path, monkeypatch):
    source = tmp_path / "source" / "a.bin"; target = tmp_path / "target"
    source.parent.mkdir(); target.mkdir(); source.write_bytes(b"stable")
    plan = make_plan(source, target, "copy"); journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash
    checks = 0
    from guixu.infrastructure.filesystem import executor as executor_module
    real_check = executor_module.identity_matches
    def changing_check(path, identity):
        nonlocal checks
        checks += 1
        if checks == 2:
            source.write_bytes(b"changed")
        return real_check(path, identity)
    monkeypatch.setattr(executor_module, "identity_matches", changing_check)
    FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert journal.state(plan.operations[0].operation_id) == "CONFLICT"
    assert not Path(plan.operations[0].target_path or "").exists()


def test_op14_mid_group_failure_is_reported_as_partial_not_atomic_success(tmp_path: Path, monkeypatch):
    source_dir, target = tmp_path / "source", tmp_path / "target"
    source_dir.mkdir(); target.mkdir(); first = source_dir / "clip.mp4"; second = source_dir / "clip.srt"
    first.write_text("video"); second.write_text("subtitle"); group = str(uuid.uuid4())
    candidates = [
        PlanCandidate("00000000-0000-0000-0000-000000000001", first, source_dir, target, "video", ("视频",), "video", companion_group_id=group),
        PlanCandidate("00000000-0000-0000-0000-000000000002", second, source_dir, target, "video", ("视频",), "video", companion_group_id=group),
    ]
    plan = PlanCompiler().compile(task_id=str(uuid.uuid4()), version=1, operation_mode="preview_move", settings_hash="a"*64, taxonomy_hashes=("b"*64,), candidates=candidates, max_depth=2)
    from guixu.infrastructure.filesystem import executor as executor_module
    real_rename = executor_module.rename_source_no_clobber
    calls = 0
    def fail_second(source, target, identity):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected sidecar failure")
        return real_rename(source, target, identity)
    monkeypatch.setattr(executor_module, "rename_source_no_clobber", fail_second)
    journal = RecordingJournal(); journal.approved[plan.plan_id] = plan.plan_hash
    FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert [journal.state(item.operation_id) for item in plan.operations] == ["COMMITTED", "FAILED"]
    assert not first.exists() and second.exists()
