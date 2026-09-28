from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path

from guixu.domain.path_policy import PathPolicyError, ensure_within, target_key, validate_category_segment
from guixu.domain.plans import ExecutionPlan, PlanCandidate, PlannedOperation
from guixu.infrastructure.filesystem.identity import read_identity, unsafe_file_feature


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _existing_names(parent: Path) -> set[str]:
    try:
        return {child.name.casefold() for child in parent.iterdir()}
    except FileNotFoundError:
        return set()


def _keep_both(target: Path, allocated: set[str]) -> Path:
    candidate = target
    counter = 2
    while target_key(candidate) in allocated or candidate.name.casefold() in _existing_names(candidate.parent):
        candidate = target.with_name(f"{target.stem} ({counter}){target.suffix}")
        counter += 1
    allocated.add(target_key(candidate))
    return candidate


class PlanCompiler:
    def compile(
        self,
        *,
        task_id: str,
        version: int,
        operation_mode: str,
        settings_hash: str,
        taxonomy_hashes: tuple[str, ...],
        candidates: list[PlanCandidate],
        max_depth: int,
        collision_policy: str = "keep_both",
        protected_root_names: set[str] | None = None,
        allow_file_rename: bool = False,
    ) -> ExecutionPlan:
        if operation_mode not in {"preview_move", "direct_move", "copy", "report_only"}:
            raise ValueError("INVALID_OPERATION_MODE")
        plan_id = str(uuid.uuid4())
        allocated: set[str] = set()
        operations: list[PlannedOperation] = []
        protected = {name.casefold() for name in (protected_root_names or set())}
        ordered = sorted(candidates, key=lambda item: item.file_id)
        forced_targets: dict[str, Path] = {}
        grouped: dict[str, list[PlanCandidate]] = {}
        for item in ordered:
            if item.companion_group_id:
                grouped.setdefault(item.companion_group_id, []).append(item)
        handled_groups: set[str] = set()
        if operation_mode != "report_only" and collision_policy == "keep_both":
            for candidate in ordered:
                group_id = candidate.companion_group_id
                if not group_id or group_id in handled_groups:
                    continue
                handled_groups.add(group_id)
                members = grouped[group_id]
                if len(members) < 2 or any(not item.eligible or item.category_id is None for item in members):
                    continue
                bases = []
                for member in members:
                    if not 1 <= len(member.category_segments) <= max_depth:
                        raise PathPolicyError("CATEGORY_DEPTH_INVALID")
                    segments = tuple(validate_category_segment(value) for value in member.category_segments)
                    bases.append(ensure_within(member.destination_root.joinpath(*segments, member.source_path.name), member.destination_root))
                suffix_number = 1
                while True:
                    choices = [
                        base if suffix_number == 1 else base.with_name(f"{base.stem} ({suffix_number}){base.suffix}")
                        for base in bases
                    ]
                    if all(target_key(choice) not in allocated and choice.name.casefold() not in _existing_names(choice.parent) for choice in choices):
                        break
                    suffix_number += 1
                for member, choice in zip(members, choices, strict=True):
                    forced_targets[member.file_id] = choice
                    allocated.add(target_key(choice))

        for ordinal, candidate in enumerate(ordered):
            source = ensure_within(candidate.source_path, candidate.source_root)
            identity = read_identity(source)
            unsafe_feature = unsafe_file_feature(source)
            reason = None
            action = "skip"
            target: Path | None = None
            if unsafe_feature:
                reason = unsafe_feature
            elif not candidate.eligible or candidate.modality == "other" or (candidate.category_id is None and candidate.proposed_stem is None):
                reason = "UNSUPPORTED_OR_UNDECIDED"
            elif candidate.proposed_stem is not None:
                if not allow_file_rename or operation_mode not in {"preview_move", "direct_move"}:
                    raise ValueError("FILE_RENAME_DISABLED")
                stem = validate_category_segment(candidate.proposed_stem)
                target = ensure_within(source.with_name(stem + source.suffix), candidate.source_root)
                if target_key(target) == target_key(source):
                    action = "noop"
                    reason = "SOURCE_EQUALS_TARGET"
                elif target.exists() and collision_policy == "skip":
                    action = "skip"
                    reason = "TARGET_EXISTS"
                    target = None
                elif collision_policy == "keep_both":
                    target = _keep_both(target, allocated)
                    action = "move"
                elif target_key(target) in allocated:
                    action = "skip"
                    reason = "BATCH_TARGET_COLLISION"
                    target = None
                else:
                    allocated.add(target_key(target))
                    action = "move"
            elif operation_mode == "report_only":
                action = "noop"
                reason = "REPORT_ONLY"
            else:
                if not 1 <= len(candidate.category_segments) <= max_depth:
                    raise PathPolicyError("CATEGORY_DEPTH_INVALID")
                segments = tuple(validate_category_segment(value) for value in candidate.category_segments)
                if candidate.source_root == candidate.destination_root and segments[0].casefold() in protected:
                    raise PathPolicyError("ROOT_LOOSE_PROTECTED_SCOPE")
                parent = candidate.destination_root.joinpath(*segments)
                target = forced_targets.get(candidate.file_id) or ensure_within(parent / source.name, candidate.destination_root)
                if target_key(target) == target_key(source):
                    action = "noop"
                    reason = "SOURCE_EQUALS_TARGET"
                elif target.exists() and collision_policy == "skip":
                    action = "skip"
                    reason = "TARGET_EXISTS"
                    target = None
                else:
                    if collision_policy == "keep_both" and candidate.file_id not in forced_targets:
                        target = _keep_both(target, allocated)
                    elif collision_policy != "keep_both" and target_key(target) in allocated:
                        action = "skip"
                        reason = "BATCH_TARGET_COLLISION"
                        target = None
                    if target is not None:
                        action = "copy" if operation_mode == "copy" else "move"
            operation_id = str(uuid.uuid5(uuid.UUID(plan_id), candidate.file_id))
            operations.append(
                PlannedOperation(
                    operation_id=operation_id,
                    file_id=candidate.file_id,
                    ordinal=ordinal,
                    action=action,
                    source_path=str(source),
                    target_path=str(target) if target else None,
                    target_key=target_key(target) if target else None,
                    source_identity=identity,
                    expected_sha256=identity.sha256,
                    companion_group_id=candidate.companion_group_id,
                    reason=reason,
                )
            )
        source_snapshot_hash = canonical_hash([
            {"file_id": item.file_id, "source": item.source_path, "identity": asdict(item.source_identity)} for item in operations
        ])
        partial = ExecutionPlan(
            plan_id=plan_id,
            task_id=task_id,
            version=version,
            operation_mode=operation_mode,  # type: ignore[arg-type]
            settings_hash=settings_hash,
            taxonomy_hashes=taxonomy_hashes,
            source_snapshot_hash=source_snapshot_hash,
            plan_hash="",
            operations=tuple(operations),
        )
        return ExecutionPlan(**{**partial.__dict__, "plan_hash": canonical_hash(partial.hash_payload())})


def verify_plan_hash(plan: ExecutionPlan) -> bool:
    payload = plan.hash_payload()
    return canonical_hash(payload) == plan.plan_hash
