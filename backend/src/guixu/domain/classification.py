from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any

from guixu.domain.profiles import FileProfile


class ClassificationError(ValueError):
    pass


@dataclass(frozen=True)
class RuleDecision:
    action: str
    category_id: str | None
    rule_ids: tuple[str, ...]


def _field(context: dict[str, Any], name: str) -> Any:
    profile = context.get("profile", {})
    if hasattr(profile, "model_dump"):
        profile = profile.model_dump(mode="python")
    if name == "text_keywords":
        return "\n".join(str(item.get("text", "")) for item in profile.get("evidence", []) if item.get("kind") in {"extracted_text", "ocr", "transcript", "subtitle"})
    aliases = {"image_width": "width", "image_height": "height", "duration_seconds": "duration_sec"}
    return context.get(name, profile.get("metadata", {}).get(aliases.get(name, name)))


def matches(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    if set(condition) == {"all"}:
        return all(matches(item, context) for item in condition["all"])
    if set(condition) == {"any"}:
        return any(matches(item, context) for item in condition["any"])
    if set(condition) == {"not"}:
        return not matches(condition["not"], context)
    if set(condition) != {"field", "op", "value"}:
        raise ClassificationError("RULE_AST_INVALID")
    current, op, expected = _field(context, condition["field"]), condition["op"], condition["value"]
    if op in {"gt", "gte", "lt", "lte"}:
        if not isinstance(current, (int, float)) or not isinstance(expected, (int, float)):
            return False
        return {"gt": current > expected, "gte": current >= expected, "lt": current < expected, "lte": current <= expected}[op]
    if op == "in":
        return str(current).casefold() in {str(item).casefold() for item in expected}
    left, right = str(current or "").casefold(), str(expected).casefold()
    return {"eq": left == right, "neq": left != right, "contains": right in left,
            "starts_with": left.startswith(right), "ends_with": left.endswith(right)}.get(op, False)


class RuleEngine:
    def evaluate(self, rules: list[dict[str, Any]], context: dict[str, Any], *, template_key: str, scope_id: str) -> RuleDecision | None:
        matched = []
        for rule in rules:
            scope = rule.get("scope", {})
            if not rule.get("enabled", True):
                continue
            if scope.get("modalities") and context.get("modality") not in scope["modalities"]:
                continue
            if scope.get("template_keys") and template_key not in scope["template_keys"]:
                continue
            if scope.get("task_scope_ids") and scope_id not in scope["task_scope_ids"]:
                continue
            if matches(rule["condition"], context):
                matched.append(rule)
        excluded = [item for item in matched if item["action"]["type"] == "exclude"]
        if excluded:
            return RuleDecision("exclude", None, tuple(sorted(item["id"] for item in excluded)))
        forced = [item for item in matched if item["action"]["type"] == "force_category"]
        if forced:
            priority = min(item["priority"] for item in forced)
            winners = [item for item in forced if item["priority"] == priority]
            categories = {item["action"]["category_id"] for item in winners}
            if len(categories) != 1:
                raise ClassificationError("RULE_CONFLICT")
            return RuleDecision("force_category", categories.pop(), tuple(sorted(item["id"] for item in winners)))
        hints = sorted((item for item in matched if item["action"]["type"] == "suggest_category"), key=lambda item: (item["priority"], item["id"]))
        return RuleDecision("suggest_category", hints[0]["action"]["category_id"], (hints[0]["id"],)) if hints else None


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


def classify_universal_types(file_id: str, taxonomy: dict[str, Any], profile: FileProfile) -> dict[str, Any]:
    suffix = {"image": "image", "text": "text", "audio": "audio", "video": "video"}.get(profile.modality)
    if profile.document_kind:
        suffix = {"pdf": "pdf", "docx": "word", "pptx": "slides", "xlsx": "sheet"}[profile.document_kind]
    category = f"universal.types.{suffix}" if suffix else None
    allowed = {node["category_id"] for node in taxonomy["nodes"] if node["selectable"]}
    evidence_ids = [profile.evidence[0].id] if profile.evidence else []
    if category not in allowed or not evidence_ids:
        return {"file_id": file_id, "taxonomy_id": taxonomy["taxonomy_id"], "category_id": None, "abstain": True, "model_score": None, "evidence_ids": [], "reason": "缺少可核对的真实格式证据。", "tags": [], "warnings": ["insufficient_evidence"]}
    return {"file_id": file_id, "taxonomy_id": taxonomy["taxonomy_id"], "category_id": category, "abstain": False, "model_score": None, "evidence_ids": evidence_ids, "reason": "本地解析器已确认文件真实格式。", "tags": [], "warnings": []}
