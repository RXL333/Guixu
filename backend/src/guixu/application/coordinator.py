from __future__ import annotations

import threading
from typing import Any

from sqlalchemy import text

from guixu.application.operations import OperationService
from guixu.application.recovery import RecoveryService
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.executor import FileOperationExecutor


class TaskCoordinator:
    """Owns the single active filesystem worker and durable task controls.

    Cancellation is cooperative: it is observed only at executor checkpoints and
    never terminates an external model server or an unrelated process.
    """

    def __init__(self, repository: TaskRepository, journal: SqliteOperationJournal, operations: OperationService) -> None:
        self.repository = repository
        self.journal = journal
        self.operations = operations
        self.recovery = RecoveryService(journal)
        self._global_execution_lock = threading.Lock()
        self._guard = threading.RLock()
        self._signals: dict[str, threading.Event] = {}
        self._requested_action: dict[str, str] = {}
        self._active: set[str] = set()

    def audit_startup(self) -> list[str]:
        return self.repository.mark_interrupted_for_recovery()

    def is_active(self, task_id: str) -> bool:
        with self._guard:
            return task_id in self._active

    def execute(self, task_id: str, plan_id: str, plan_hash: str, expected_revision: int):
        if not self._global_execution_lock.acquire(blocking=False):
            raise ValueError("TASK_BUSY")
        signal = threading.Event()
        with self._guard:
            self._signals[task_id] = signal
            self._active.add(task_id)
            self._requested_action.pop(task_id, None)
        self.repository.append_event(task_id, "execution_started", {"plan_id": plan_id})
        try:
            self.journal.assert_execution_ready(task_id, plan_id, plan_hash, expected_revision)
            plan = self.journal.load_plan(plan_id)
            if plan.task_id != task_id:
                raise ValueError("SCOPE_CONFLICT")
            completed = FileOperationExecutor(self.journal, should_cancel=signal.is_set).execute(plan, plan_hash)
            if not completed:
                with self._guard:
                    action = self._requested_action.get(task_id, "pause")
                current = self.repository.get(task_id)
                target = "CANCELLED" if action == "cancel" else "PAUSED"
                self.repository.transition_control(
                    task_id,
                    current["revision"],
                    allowed_statuses={"RUNNING", "PAUSE_REQUESTED"},
                    status=target,
                    event_type="task_cancelled" if target == "CANCELLED" else "task_paused",
                    checkpoint_patch={"paused_plan_id": plan_id, "control_action": action},
                )
            else:
                self.repository.append_event(task_id, "execution_finished", {"plan_id": plan_id})
            self.repository.refresh_counters(task_id)
            return self.journal.load_plan(plan_id)
        finally:
            with self._guard:
                self._active.discard(task_id)
                self._signals.pop(task_id, None)
                self._requested_action.pop(task_id, None)
            self._global_execution_lock.release()

    def request_pause(self, task_id: str, expected_revision: int) -> dict[str, Any]:
        with self._guard:
            active = task_id in self._active
            if active:
                self._requested_action[task_id] = "pause"
                self._signals[task_id].set()
        return self.repository.transition_control(
            task_id,
            expected_revision,
            allowed_statuses={"RUNNING"},
            status="PAUSE_REQUESTED" if active else "PAUSED",
            event_type="pause_requested" if active else "task_paused",
            checkpoint_patch={"control_action": "pause"},
        )

    def request_cancel(self, task_id: str, expected_revision: int) -> dict[str, Any]:
        with self._guard:
            active = task_id in self._active
            if active:
                self._requested_action[task_id] = "cancel"
                self._signals[task_id].set()
        return self.repository.transition_control(
            task_id,
            expected_revision,
            allowed_statuses={"DRAFT", "RUNNING", "PAUSE_REQUESTED", "PAUSED", "AWAITING_TAXONOMY_APPROVAL", "AWAITING_EXECUTION_APPROVAL", "RECOVERY_REQUIRED"},
            status="PAUSE_REQUESTED" if active else "CANCELLED",
            event_type="cancel_requested" if active else "task_cancelled",
            checkpoint_patch={"control_action": "cancel"},
        )

    def resume(self, task_id: str, expected_revision: int) -> dict[str, Any]:
        return self.repository.transition_control(
            task_id,
            expected_revision,
            allowed_statuses={"PAUSED"},
            status="RUNNING",
            event_type="task_resumed",
            checkpoint_patch={"control_action": None},
        )

    def recover(self, task_id: str, expected_revision: int) -> dict[str, Any]:
        self.repository.assert_revision(task_id, expected_revision)
        task = self.repository.get(task_id)
        if task["status"] != "RECOVERY_REQUIRED":
            raise ValueError("TASK_STATE_CONFLICT")
        if not self._global_execution_lock.acquire(blocking=False):
            raise ValueError("TASK_BUSY")
        try:
            with self.repository.database.engine.connect() as connection:
                plan_id = connection.execute(text("""
                    SELECT id FROM plans WHERE task_id=:task AND status='executing'
                    ORDER BY version DESC LIMIT 1
                """), {"task": task_id}).scalar()
            if not plan_id:
                current = self.repository.get(task_id)
                task = self.repository.transition_control(
                    task_id,
                    current["revision"],
                    allowed_statuses={"RECOVERY_REQUIRED"},
                    status="PAUSED",
                    event_type="recovery_checked",
                    checkpoint_patch={"recovery_result": "no_unfinished_disk_operations"},
                )
                return {"task": task, "result": {"committed": 0, "retried": 0, "conflict": 0, "failed": 0}}
            result = self.recovery.recover(self.journal.load_plan(str(plan_id)))
            self.repository.append_event(task_id, "recovery_completed", result)
            self.repository.refresh_counters(task_id)
            return {"task": self.repository.get(task_id), "result": result}
        finally:
            self._global_execution_lock.release()
