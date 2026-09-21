from __future__ import annotations

from pathlib import Path

from guixu.application.plan_compiler import PlanCompiler
from guixu.application.undo import UndoCompiler
from guixu.domain.plans import ExecutionPlan, PlanCandidate
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.executor import FileOperationExecutor


class OperationService:
    def __init__(self, repository: TaskRepository, journal: SqliteOperationJournal) -> None:
        self.repository = repository
        self.journal = journal

    def compile(self, task_id: str) -> ExecutionPlan:
        task = self.repository.get(task_id)
        if task["status"] != "AWAITING_EXECUTION_APPROVAL":
            raise ValueError("TASK_NOT_READY")
        inputs = self.repository.plan_inputs(task_id)
        protected = {row["display_name"].casefold() for row in inputs if row["kind"] == "protected_child"}
        group_modalities = {
            row["companion_group_id"]: row["modality"]
            for row in inputs if row["companion_group_id"] and row["modality"] != "other"
        }
        group_categories = {
            row["companion_group_id"]: (row.get("category_id"), row.get("category_segments"))
            for row in inputs if row["companion_group_id"] and row.get("category_id")
        }
        candidates = []
        for row in inputs:
            effective_modality = group_modalities.get(row["companion_group_id"], row["modality"])
            approved_category = group_categories.get(row["companion_group_id"], (row.get("category_id"), row.get("category_segments")))
            if row["scan_status"] == "eligible" and not row.get("taxonomy_id"):
                raise ValueError("TAXONOMY_NOT_APPROVED")
            category_id, segments = approved_category
            candidates.append(PlanCandidate(
                file_id=row["file_id"], source_path=Path(row["original_path"]),
                source_root=Path(row["source_root"]), destination_root=Path(row["destination_root"]),
                category_id=category_id,
                category_segments=tuple(segments or ()), modality=effective_modality,
                eligible=row["scan_status"] == "eligible",
                companion_group_id=row["companion_group_id"],
            ))
        taxonomy_hashes = tuple(sorted({row["taxonomy_hash"] for row in inputs if row.get("taxonomy_hash")}))
        if not taxonomy_hashes:
            raise ValueError("TAXONOMY_NOT_APPROVED")
        plan = PlanCompiler().compile(
            task_id=task_id, version=self.repository.next_plan_version(task_id),
            operation_mode=task["settings"]["operation_mode"], settings_hash=task["settings_hash"],
            taxonomy_hashes=taxonomy_hashes, candidates=candidates,
            max_depth=task["settings"]["max_depth"], collision_policy=task["settings"]["collision_policy"],
            protected_root_names=protected,
        )
        self.journal.persist_plan(plan, task["revision"])
        return plan

    def approve(self, task_id: str, plan_id: str, plan_hash: str, expected_revision: int) -> None:
        if self.journal.load_plan(plan_id).task_id != task_id:
            raise ValueError("SCOPE_CONFLICT")
        self.journal.approve(plan_id, plan_hash, expected_revision)

    def execute(self, task_id: str, plan_id: str, plan_hash: str, expected_revision: int) -> ExecutionPlan:
        self.repository.assert_revision(task_id, expected_revision)
        plan = self.journal.load_plan(plan_id)
        if plan.task_id != task_id:
            raise ValueError("SCOPE_CONFLICT")
        FileOperationExecutor(self.journal).execute(plan, plan_hash)
        return self.journal.load_plan(plan_id)

    def compile_undo(self, task_id: str, forward_plan_id: str, expected_revision: int) -> ExecutionPlan:
        self.repository.assert_revision(task_id, expected_revision)
        forward = self.journal.load_plan(forward_plan_id)
        if forward.task_id != task_id:
            raise ValueError("SCOPE_CONFLICT")
        undo = UndoCompiler().compile(
            forward, self.journal.completed_operation_ids(forward_plan_id), self.repository.next_plan_version(forward.task_id)
        )
        self.journal.persist_plan(undo, expected_revision)
        return undo
