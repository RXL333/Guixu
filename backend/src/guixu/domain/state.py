from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    PAUSED = "PAUSED"
    AWAITING_TAXONOMY_APPROVAL = "AWAITING_TAXONOMY_APPROVAL"
    AWAITING_EXECUTION_APPROVAL = "AWAITING_EXECUTION_APPROVAL"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ISSUES = "COMPLETED_WITH_ISSUES"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class TaskPhase(StrEnum):
    SETUP = "SETUP"
    SCAN = "SCAN"
    EXTRACT = "EXTRACT"
    PLAN = "PLAN"
    CLASSIFY = "CLASSIFY"
    PREVIEW = "PREVIEW"
    EXECUTE = "EXECUTE"
    REPORT = "REPORT"
    UNDO = "UNDO"


@dataclass(frozen=True)
class Transition:
    status: TaskStatus
    phase: TaskPhase


def start_task(status: TaskStatus) -> Transition:
    if status is not TaskStatus.DRAFT:
        raise ValueError("only DRAFT tasks can start")
    return Transition(TaskStatus.RUNNING, TaskPhase.SCAN)


def finish_report_only(status: TaskStatus, phase: TaskPhase) -> Transition:
    if status is not TaskStatus.RUNNING or phase is not TaskPhase.SCAN:
        raise ValueError("report-only completion requires RUNNING/SCAN")
    return Transition(TaskStatus.COMPLETED, TaskPhase.REPORT)

