from __future__ import annotations

from pathlib import Path

from guixu.application.plan_compiler import PlanCompiler, canonical_hash
from guixu.application.undo import UndoCompiler
from guixu.domain.plans import ExecutionPlan, PlanCandidate
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.executor import FileOperationExecutor


TYPE_CATEGORIES = {"image": "图片", "text": "文本", "document": "文档", "audio": "音频", "video": "视频"}


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
            if row.get("taxonomy_id"):
                category_id, segments = approved_category
            else:
                category = TYPE_CATEGORIES.get(effective_modality)
                if row["kind"] == "root_loose" and category and category.casefold() in protected:
                    category = f"{category}文件"
                category_id, segments = (f"type:{effective_modality}", [category]) if category else (None, [])
            candidates.append(PlanCandidate(
                file_id=row["file_id"], source_path=Path(row["original_path"]),
                source_root=Path(row["source_root"]), destination_root=Path(row["destination_root"]),
                category_id=category_id,
                category_segments=tuple(segments or ()), modality=effective_modality,
                eligible=row["scan_status"] == "eligible",
                companion_group_id=row["companion_group_id"],
            ))
        taxonomy_hashes = tuple(sorted({row["taxonomy_hash"] for row in inputs if row.get("taxonomy_hash")})) or (canonical_hash(TYPE_CATEGORIES),)
        plan = PlanCompiler().compile(
            task_id=task_id, version=self.repository.next_plan_version(task_id),
            operation_mode=task["settings"]["operation_mode"], settings_hash=task["settings_hash"],
            taxonomy_hashes=taxonomy_hashes, candidates=candidates,
            max_depth=task["settings"]["max_depth"], collision_policy=task["settings"]["collision_policy"],
            protected_root_names=protected,
        )
        self.journal.persist_plan(plan)
        return plan

    def approve(self, task_id: str, plan_id: str, plan_hash: str, expected_revision: int) -> None:
        self.repository.assert_revision(task_id, expected_revision)
        if self.journal.load_plan(plan_id).task_id != task_id:
            raise ValueError("SCOPE_CONFLICT")
        self.journal.approve(plan_id, plan_hash)

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
        self.journal.persist_plan(undo)
        return undo
