from __future__ import annotations

import shutil
import tempfile
import uuid
import os
import stat
from pathlib import Path

import pytest

from guixu.application.plan_compiler import PlanCompiler
from guixu.application.recovery import RecoveryService
from guixu.domain.plans import PlanCandidate, PlannedOperation
from guixu.infrastructure.filesystem.executor import FileOperationExecutor


class Journal:
    def __init__(self):
        self.states = {}; self.events = []; self.approved = {}
    def state(self, operation_id): return self.states.get(operation_id, "PLANNED")
    def transition(self, operation: PlannedOperation, state, payload=None):
        self.states[operation.operation_id] = state; self.events.append(state)
    def record_directory(self, plan_id, path): return None
    def approved_hash(self, plan_id): return self.approved.get(plan_id)
    def begin_execution(self, plan_id): return None
    def finish_plan(self, plan_id): return None


def compile_move(source: Path, destination: Path, mode="preview_move"):
    item = PlanCandidate(str(uuid.uuid4()), source, source.parent, destination, "docs", ("文档",), "document")
    return PlanCompiler().compile(
        task_id=str(uuid.uuid4()), version=1, operation_mode=mode, settings_hash="a" * 64,
        taxonomy_hashes=("b" * 64,), candidates=[item], max_depth=2,
    )


def test_op04_real_cross_volume_copy_verify_publish_delete(project_root: Path, tmp_path: Path):
    artifact_root = project_root / "artifacts" / "test-workspaces"
    artifact_root.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="phase-02-cross-volume-", dir=artifact_root))
    source = tmp_path / "cross-volume.bin"; source.write_bytes(b"cross-volume" * 131072)
    try:
        if source.stat().st_dev == destination.stat().st_dev:
            pytest.skip("the available temporary and project directories are on the same real volume")
        plan = compile_move(source, destination); journal = Journal(); journal.approved[plan.plan_id] = plan.plan_hash
        FileOperationExecutor(journal, chunk_size=65536).execute(plan, plan.plan_hash)
        target = Path(plan.operations[0].target_path or "")
        assert not source.exists() and target.exists()
        assert journal.events == ["PREPARED", "COPYING", "TEMP_WRITTEN", "VERIFIED", "PUBLISHED", "SOURCE_REMOVED", "COMMITTED"]
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def test_op07_cancel_stops_at_chunk_checkpoint_and_recovery_finishes(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "large.bin"; source.write_bytes(b"x" * 524288)
    plan = compile_move(source, destination, "copy"); journal = Journal(); journal.approved[plan.plan_id] = plan.plan_hash
    calls = 0
    def cancel_after_chunks():
        nonlocal calls
        calls += 1
        return calls >= 4
    FileOperationExecutor(journal, chunk_size=65536, should_cancel=cancel_after_chunks).execute(plan, plan.plan_hash)
    operation = plan.operations[0]; target = Path(operation.target_path or "")
    temporary = target.with_name(f".{target.name}.guixu-part-{operation.operation_id}")
    assert source.exists() and not target.exists() and temporary.exists()
    assert journal.state(operation.operation_id) == "COPYING"
    RecoveryService(journal).recover(plan)
    assert source.exists() and target.read_bytes() == source.read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="Windows handle semantics")
def test_fs15_locked_source_is_not_forced_or_lost(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "locked.txt"; source.write_text("locked")
    plan = compile_move(source, destination); journal = Journal(); journal.approved[plan.plan_id] = plan.plan_hash
    with source.open("rb"):
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    assert source.read_text() == "locked"
    assert not Path(plan.operations[0].target_path or "").exists()
    assert journal.state(plan.operations[0].operation_id) == "FAILED"


def test_fs15_read_only_source_can_be_safely_copied_without_change(tmp_path: Path):
    source_dir, destination = tmp_path / "source", tmp_path / "out"
    source_dir.mkdir(); destination.mkdir(); source = source_dir / "readonly.txt"; source.write_text("readonly")
    source.chmod(stat.S_IREAD)
    try:
        plan = compile_move(source, destination, "copy"); journal = Journal(); journal.approved[plan.plan_id] = plan.plan_hash
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)
        target = Path(plan.operations[0].target_path or "")
        assert source.read_text() == "readonly" and target.read_text() == "readonly"
        assert journal.state(plan.operations[0].operation_id) == "COMMITTED"
    finally:
        source.chmod(stat.S_IWRITE | stat.S_IREAD)
