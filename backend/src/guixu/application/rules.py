from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from guixu.domain.classification import ClassificationError, RuleEngine, matches
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import canonical_json


FIELDS = {"basename", "extension", "relative_path", "modality", "size_bytes", "mtime_ns", "mime", "text_keywords", "image_width", "image_height", "duration_seconds"}
OPS = {"eq", "neq", "contains", "starts_with", "ends_with", "in", "gt", "gte", "lt", "lte"}
ACTIONS = {"force_category", "suggest_category", "exclude"}


def validate_condition(condition: dict[str, Any], depth: int = 0) -> int:
    if depth > 8 or not isinstance(condition, dict):
        raise ClassificationError("RULE_AST_INVALID")
    if set(condition) in ({"all"}, {"any"}):
        items = next(iter(condition.values()))
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise ClassificationError("RULE_AST_INVALID")
        leaves = sum(validate_condition(item, depth + 1) for item in items)
    elif set(condition) == {"not"}:
        leaves = validate_condition(condition["not"], depth + 1)
    elif set(condition) == {"field", "op", "value"}:
        if condition["field"] not in FIELDS or condition["op"] not in OPS:
            raise ClassificationError("RULE_AST_INVALID")
        if condition["op"] == "in" and (not isinstance(condition["value"], list) or len(condition["value"]) > 100):
            raise ClassificationError("RULE_AST_INVALID")
        leaves = 1
    else:
        raise ClassificationError("RULE_AST_INVALID")
    if leaves > 100:
        raise ClassificationError("RULE_AST_LIMIT")
    return leaves


class RuleService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, rule: dict[str, Any]) -> dict[str, Any]:
        self._validate(rule)
        rule_id = str(uuid.uuid4()); now = utc_now()
        with self.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO rules(id,name,priority,enabled,scope_json,condition_json,action_json,revision,created_at,updated_at)
                VALUES(:id,:name,:priority,:enabled,:scope,:condition,:action,1,:now,:now)
            """), {"id": rule_id, "name": rule["name"], "priority": rule["priority"], "enabled": int(rule["enabled"]),
                    "scope": canonical_json(rule["scope"]), "condition": canonical_json(rule["condition"]),
                    "action": canonical_json(rule["action"]), "now": now})
        return self.get(rule_id)

    def list(self) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            return [self._decode(row) for row in connection.execute(text("SELECT * FROM rules ORDER BY priority,id")).mappings()]

    def get(self, rule_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM rules WHERE id=:id"), {"id": rule_id}).mappings().first()
        if row is None: raise KeyError(rule_id)
        return self._decode(row)

    def test(self, task_id: str, file_ids: list[str], draft_rule: dict[str, Any]) -> dict[str, Any]:
        self._validate(draft_rule)
        matched = []
        with self.database.engine.connect() as connection:
            for file_id in file_ids[:500]:
                row = connection.execute(text("SELECT id,scope_id,basename,extension,relative_path,modality,size_bytes,mtime_ns,mime FROM files WHERE task_id=:task AND id=:file"), {"task": task_id, "file": file_id}).mappings().first()
                scope = draft_rule["scope"]
                in_scope = bool(row) and (
                    (not scope.get("modalities") or row["modality"] in scope["modalities"])
                    and (not scope.get("task_scope_ids") or row["scope_id"] in scope["task_scope_ids"])
                )
                if in_scope and matches(draft_rule["condition"], {**dict(row), "profile": {"metadata": {}, "evidence": []}}):
                    matched.append(file_id)
        return {"matched_file_ids": matched, "conflicts": []}

    @staticmethod
    def _validate(rule: dict[str, Any]) -> None:
        if set(rule) != {"name", "priority", "enabled", "scope", "condition", "action"}:
            raise ClassificationError("RULE_SCHEMA_INVALID")
        if not isinstance(rule["name"], str) or not 1 <= len(rule["name"]) <= 80 or not isinstance(rule["priority"], int) or rule["priority"] < 0:
            raise ClassificationError("RULE_SCHEMA_INVALID")
        if not isinstance(rule["enabled"], bool) or not isinstance(rule["scope"], dict) or not set(rule["scope"]).issubset({"modalities", "template_keys", "task_scope_ids"}):
            raise ClassificationError("RULE_SCHEMA_INVALID")
        validate_condition(rule["condition"])
        action = rule["action"]
        if set(action) != {"type", "category_id", "template_key"} or action["type"] not in ACTIONS:
            raise ClassificationError("RULE_SCHEMA_INVALID")
        if action["type"] in {"force_category", "suggest_category"} and not action["category_id"]:
            raise ClassificationError("RULE_SCHEMA_INVALID")
        if action["type"] == "exclude" and action["category_id"] is not None:
            raise ClassificationError("RULE_SCHEMA_INVALID")

    @staticmethod
    def _decode(row) -> dict[str, Any]:
        return {"id": row["id"], "name": row["name"], "priority": row["priority"], "enabled": bool(row["enabled"]),
                "scope": json.loads(row["scope_json"]), "condition": json.loads(row["condition_json"]),
                "action": json.loads(row["action_json"]), "revision": row["revision"]}
