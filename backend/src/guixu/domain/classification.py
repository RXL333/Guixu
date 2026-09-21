from __future__ import annotations

from typing import Any

from guixu.domain.profiles import FileProfile


class ClassificationError(ValueError):
    pass


def validate_result(result: dict[str, Any], *, file_id: str, taxonomy: dict[str, Any], profile: FileProfile) -> None:
    if result.get("file_id") != file_id or result.get("taxonomy_id") != taxonomy["taxonomy_id"]:
        raise ClassificationError("CLASSIFICATION_CONTEXT_MISMATCH")
    selectable = {node["category_id"] for node in taxonomy["nodes"] if node["selectable"]}
    if result.get("abstain") is True:
        if result.get("category_id") is not None:
            raise ClassificationError("ABSTAIN_CATEGORY_INVALID")
    elif result.get("category_id") not in selectable:
        raise ClassificationError("CATEGORY_NOT_ALLOWED")
    evidence = {item.id for item in profile.evidence}
    if not result.get("abstain") and (not result.get("evidence_ids") or not set(result["evidence_ids"]).issubset(evidence)):
        raise ClassificationError("EVIDENCE_NOT_ALLOWED")


def review_band(result: dict[str, Any], profile: FileProfile) -> str:
    if result.get("abstain") or not result.get("evidence_ids"):
        return "low"
    score = result.get("model_score")
    warnings = set(result.get("warnings", []))
    if score is not None and score >= 0.85 and not warnings and not profile.coverage.truncated:
        return "high"
    if score is not None and score >= 0.60 and "conflicting_signals" not in warnings:
        return "medium"
    return "low"
