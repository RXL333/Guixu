from __future__ import annotations

import uuid
from pathlib import Path

from guixu.application.plan_compiler import canonical_hash
from guixu.domain.path_policy import target_key
from guixu.domain.plans import ExecutionPlan, PlannedOperation
from guixu.infrastructure.filesystem.identity import read_identity


class UndoCompiler:
    def compile(self, forward: ExecutionPlan, completed_operation_ids: set[str], version: int) -> ExecutionPlan:
        plan_id = str(uuid.uuid4())
        operations: list[PlannedOperation] = []
        eligible = [item for item in forward.operations if item.operation_id in completed_operation_ids and item.action in {"move", "copy"}]
        for ordinal, original in enumerate(reversed(eligible)):
            published = Path(original.target_path or "")
            identity = read_identity(published)
            action = "move" if original.action == "move" else "recycle_copy"
            destination = Path(original.source_path) if action == "move" else None
            operation_id = str(uuid.uuid5(uuid.UUID(plan_id), original.operation_id))
            operations.append(PlannedOperation(
                operation_id=operation_id,
                file_id=original.file_id,
                ordinal=ordinal,
                action=action,
                source_path=str(published),
                target_path=str(destination) if destination else None,
                target_key=target_key(destination) if destination else None,
                source_identity=identity,
                expected_sha256=identity.sha256,
                companion_group_id=original.companion_group_id,
                reverses_operation_id=original.operation_id,
            ))
        snapshot_hash = canonical_hash([
            {"operation_id": item.operation_id, "source": item.source_path, "sha256": item.expected_sha256}
            for item in operations
        ])
        partial = ExecutionPlan(
            plan_id=plan_id,
            task_id=forward.task_id,
            version=version,
            operation_mode=forward.operation_mode,
            settings_hash=forward.settings_hash,
            taxonomy_hashes=forward.taxonomy_hashes,
            source_snapshot_hash=snapshot_hash,
            plan_hash="",
            operations=tuple(operations),
            plan_kind="undo",
            parent_plan_id=forward.plan_id,
        )
        return ExecutionPlan(**{**partial.__dict__, "plan_hash": canonical_hash(partial.hash_payload())})

