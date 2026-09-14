from __future__ import annotations

from pathlib import Path

from guixu.domain.plans import ExecutionPlan, PlannedOperation
from guixu.infrastructure.filesystem.executor import FileOperationExecutor, OperationJournal, move_no_clobber
from guixu.infrastructure.filesystem.identity import identity_matches, sha256_file


def _has_hash(path: Path, expected: str) -> bool:
    try:
        return path.is_file() and sha256_file(path) == expected
    except OSError:
        return False


class RecoveryService:
    def __init__(self, journal: OperationJournal) -> None:
        self.journal = journal

    def recover(self, plan: ExecutionPlan) -> dict[str, int]:
        result = {"committed": 0, "retried": 0, "conflict": 0, "failed": 0}
        for operation in plan.operations:
            state = self.journal.state(operation.operation_id)
            if state in {"COMMITTED", "SKIPPED", "UNDONE"}:
                continue
            outcome = self._reconcile(plan, operation)
            result[outcome] += 1
        if result["retried"]:
            FileOperationExecutor(self.journal).execute(plan, plan.plan_hash)
        self.journal.finish_plan(plan.plan_id)
        return result

    def _reconcile(self, plan: ExecutionPlan, operation: PlannedOperation) -> str:
        source = Path(operation.source_path)
        target = Path(operation.target_path) if operation.target_path else None
        temporary = target.with_name(f".{target.name}.guixu-part-{operation.operation_id}") if target else None
        source_ok = identity_matches(source, operation.source_identity)
        target_ok = bool(target and _has_hash(target, operation.expected_sha256))
        if target and target.exists() and not target_ok:
            self.journal.transition(operation, "UNDO_CONFLICT" if plan.plan_kind == "undo" else "CONFLICT", {"code": "TARGET_CONTENT_UNKNOWN"})
            return "conflict"
        if target_ok:
            if operation.action == "move" and source_ok:
                source.unlink()
                self.journal.transition(operation, "SOURCE_REMOVED")
            final = "UNDONE" if plan.plan_kind == "undo" else "COMMITTED"
            self.journal.transition(operation, final)
            return "committed"
        if source_ok:
            if temporary and temporary.exists():
                if _has_hash(temporary, operation.expected_sha256):
                    move_no_clobber(temporary, target)
                    self.journal.transition(operation, "PUBLISHED")
                    if operation.action == "move":
                        source.unlink(); self.journal.transition(operation, "SOURCE_REMOVED")
                    self.journal.transition(operation, "UNDONE" if plan.plan_kind == "undo" else "COMMITTED")
                    return "committed"
                temporary.unlink()
            return "retried"
        self.journal.transition(operation, "UNDO_CONFLICT" if plan.plan_kind == "undo" else "FAILED", {"code": "FAILED_MISSING"})
        return "conflict" if plan.plan_kind == "undo" else "failed"

