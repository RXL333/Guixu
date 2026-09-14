from __future__ import annotations

import ctypes
import os
import shutil
from pathlib import Path
from typing import Protocol
from send2trash import send2trash

from guixu.application.plan_compiler import verify_plan_hash
from guixu.domain.plans import ExecutionPlan, PlannedOperation
from guixu.infrastructure.filesystem.identity import identity_matches, sha256_file
from guixu.infrastructure.filesystem.windows_handles import locked_source_chunks, rename_source_no_clobber


class CancellationRequested(Exception):
    pass


class SourceChangedDuringCopy(Exception):
    pass


class OperationJournal(Protocol):
    def state(self, operation_id: str) -> str: ...
    def transition(self, operation: PlannedOperation, state: str, payload: dict[str, object] | None = None) -> None: ...
    def record_directory(self, plan_id: str, path: Path) -> None: ...
    def approved_hash(self, plan_id: str) -> str | None: ...
    def begin_execution(self, plan_id: str) -> None: ...
    def finish_plan(self, plan_id: str) -> None: ...


def move_no_clobber(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(target)
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file = kernel32.MoveFileW
        move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        move_file.restype = ctypes.c_int
        if not move_file(str(source), str(target)):
            error = ctypes.get_last_error()
            if target.exists():
                raise FileExistsError(target)
            raise OSError(error, os.strerror(error), str(source))
    else:
        # Hard-link publication is no-clobber; unlink happens only after the link exists.
        os.link(source, target)
        source.unlink()


class FileOperationExecutor:
    def __init__(self, journal: OperationJournal, chunk_size: int = 1024 * 1024, should_cancel=None) -> None:
        self.journal = journal
        self.chunk_size = chunk_size
        self.should_cancel = should_cancel or (lambda: False)

    def execute(self, plan: ExecutionPlan, approved_hash: str) -> bool:
        if approved_hash != plan.plan_hash or self.journal.approved_hash(plan.plan_id) != approved_hash or not verify_plan_hash(plan):
            raise ValueError("PLAN_HASH_MISMATCH")
        self.journal.begin_execution(plan.plan_id)
        handled_groups: set[str] = set()
        cancelled = False
        for operation in plan.operations:
            if self.should_cancel():
                cancelled = True
                break
            group_id = operation.companion_group_id
            if group_id:
                if group_id in handled_groups:
                    continue
                handled_groups.add(group_id)
                group = [item for item in plan.operations if item.companion_group_id == group_id]
                if not self._group_preflight(group, plan.plan_kind):
                    continue
                for member in group:
                    if self.should_cancel():
                        cancelled = True
                        break
                    try:
                        self._execute_one(plan.plan_id, plan.plan_kind, member)
                    except CancellationRequested:
                        cancelled = True
                        break
                    if self.journal.state(member.operation_id) not in {"COMMITTED", "SKIPPED", "UNDONE"}:
                        for pending in group:
                            if self.journal.state(pending.operation_id) == "PLANNED":
                                self.journal.transition(pending, "CONFLICT", {"code": "PARTIAL_GROUP"})
                        break
                continue
            if self.journal.state(operation.operation_id) in {"COMMITTED", "SKIPPED", "UNDONE"}:
                continue
            try:
                self._execute_one(plan.plan_id, plan.plan_kind, operation)
            except CancellationRequested:
                cancelled = True
                break
        if not cancelled:
            self.journal.finish_plan(plan.plan_id)
        return not cancelled

    def _group_preflight(self, operations: list[PlannedOperation], plan_kind: str) -> bool:
        conflict_state = "UNDO_CONFLICT" if plan_kind == "undo" else "CONFLICT"
        blocked = False
        for operation in operations:
            if operation.action in {"skip", "noop"}:
                continue
            source = Path(operation.source_path)
            target = Path(operation.target_path) if operation.target_path else None
            if not identity_matches(source, operation.source_identity) or (target is not None and target.exists()):
                blocked = True
                break
        if blocked:
            for operation in operations:
                self.journal.transition(operation, conflict_state, {"code": "COMPANION_GROUP_PREFLIGHT"})
            return False
        return True

    def _execute_one(self, plan_id: str, plan_kind: str, operation: PlannedOperation) -> None:
        if operation.action in {"skip", "noop"}:
            self.journal.transition(operation, "SKIPPED", {"reason": operation.reason})
            return
        source = Path(operation.source_path)
        target = Path(operation.target_path or "")
        prepared_state = "UNDO_PREPARED" if plan_kind == "undo" else "PREPARED"
        final_state = "UNDONE" if plan_kind == "undo" else "COMMITTED"
        self.journal.transition(operation, prepared_state)
        if not identity_matches(source, operation.source_identity):
            conflict_state = "UNDO_CONFLICT" if plan_kind == "undo" else "CONFLICT"
            self.journal.transition(operation, conflict_state, {"code": "SOURCE_CHANGED"})
            return
        if operation.action == "recycle_copy":
            try:
                send2trash(str(source))
            except OSError as exc:
                self.journal.transition(operation, "UNDO_CONFLICT", {"code": "RECYCLE_UNAVAILABLE", "type": type(exc).__name__})
                return
            self.journal.transition(operation, "UNDONE")
            return
        if target.exists():
            self.journal.transition(
                operation,
                "UNDO_CONFLICT" if plan_kind == "undo" else "CONFLICT",
                {"code": "TARGET_APPEARED"},
            )
            return
        self._make_parent(plan_id, target.parent)
        same_volume = source.stat().st_dev == target.parent.stat().st_dev
        try:
            if operation.action == "move" and same_volume:
                rename_source_no_clobber(source, target, operation.source_identity)
                if sha256_file(target) != operation.expected_sha256:
                    raise OSError("published hash mismatch")
                self.journal.transition(operation, "PUBLISHED")
                self.journal.transition(operation, final_state)
                return
            self._copy_publish(operation, source, target)
            if operation.action == "move":
                if not identity_matches(source, operation.source_identity):
                    self.journal.transition(operation, "CONFLICT", {"code": "SOURCE_CHANGED_AFTER_COPY"})
                    return
                source.unlink()
                self.journal.transition(operation, "SOURCE_REMOVED")
            self.journal.transition(operation, final_state)
        except FileExistsError:
            self.journal.transition(operation, "UNDO_CONFLICT" if plan_kind == "undo" else "CONFLICT", {"code": "TARGET_APPEARED"})
        except SourceChangedDuringCopy:
            self.journal.transition(
                operation,
                "UNDO_CONFLICT" if plan_kind == "undo" else "CONFLICT",
                {"code": "SOURCE_CHANGED_DURING_COPY"},
            )
        except OSError as exc:
            self.journal.transition(operation, "FAILED", {"code": "OPERATION_FAILED", "type": type(exc).__name__})

    def _make_parent(self, plan_id: str, parent: Path) -> None:
        missing: list[Path] = []
        cursor = parent
        while not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for directory in reversed(missing):
            directory.mkdir()
            self.journal.record_directory(plan_id, directory)

    def _copy_publish(self, operation: PlannedOperation, source: Path, target: Path) -> None:
        temporary = target.with_name(f".{target.name}.guixu-part-{operation.operation_id}")
        self.journal.transition(operation, "COPYING", {"temp_path": str(temporary)})
        with temporary.open("xb") as writer:
            for chunk in locked_source_chunks(source, operation.source_identity, self.chunk_size):
                writer.write(chunk)
                if self.should_cancel():
                    writer.flush()
                    os.fsync(writer.fileno())
                    raise CancellationRequested
            writer.flush()
            os.fsync(writer.fileno())
        self.journal.transition(operation, "TEMP_WRITTEN", {"temp_path": str(temporary)})
        if sha256_file(temporary) != operation.expected_sha256:
            raise OSError("temporary hash mismatch")
        self.journal.transition(operation, "VERIFIED", {"temp_path": str(temporary)})
        if not identity_matches(source, operation.source_identity):
            raise SourceChangedDuringCopy
        move_no_clobber(temporary, target)
        if sha256_file(target) != operation.expected_sha256:
            raise OSError("published hash mismatch")
        shutil.copystat(source, target, follow_symlinks=False)
        self.journal.transition(operation, "PUBLISHED")
