import pytest

from guixu.domain.state import TaskPhase, TaskStatus, finish_report_only, start_task


def test_stage_one_state_transitions():
    running = start_task(TaskStatus.DRAFT)
    assert running.status is TaskStatus.RUNNING
    assert running.phase is TaskPhase.SCAN
    finished = finish_report_only(running.status, running.phase)
    assert finished.status is TaskStatus.COMPLETED
    assert finished.phase is TaskPhase.REPORT


def test_cannot_start_twice():
    with pytest.raises(ValueError):
        start_task(TaskStatus.RUNNING)

