from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


OperationAction = Literal["move", "copy", "skip", "noop", "recycle_copy"]


@dataclass(frozen=True)
class SourceIdentity:
    volume_id: str
    file_id: str
    size_bytes: int
    mtime_ns: int
    sha256: str
    link_count: int


@dataclass(frozen=True)
class PlanCandidate:
    file_id: str
    source_path: Path
    source_root: Path
    destination_root: Path
    category_id: str | None
    category_segments: tuple[str, ...]
    modality: str
    eligible: bool = True
    companion_group_id: str | None = None


@dataclass(frozen=True)
class PlannedOperation:
    operation_id: str
    file_id: str
    ordinal: int
    action: OperationAction
    source_path: str
    target_path: str | None
    target_key: str | None
    source_identity: SourceIdentity
    expected_sha256: str
    companion_group_id: str | None = None
    reason: str | None = None
    reverses_operation_id: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    task_id: str
    version: int
    operation_mode: Literal["preview_move", "direct_move", "copy", "report_only"]
    settings_hash: str
    taxonomy_hashes: tuple[str, ...]
    source_snapshot_hash: str
    plan_hash: str
    operations: tuple[PlannedOperation, ...]
    plan_kind: Literal["forward", "undo"] = "forward"
    parent_plan_id: str | None = None

    def hash_payload(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "version": self.version,
            "operation_mode": self.operation_mode,
            "settings_hash": self.settings_hash,
            "taxonomy_hashes": self.taxonomy_hashes,
            "source_snapshot_hash": self.source_snapshot_hash,
            "plan_kind": self.plan_kind,
            "parent_plan_id": self.parent_plan_id,
            "operations": [asdict(item) for item in self.operations],
        }
