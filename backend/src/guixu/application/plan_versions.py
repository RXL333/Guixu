from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.filesystem.identity import read_identity


KEEP_ACTIONS = {"skip", "noop"}
CONFLICT_STATES = {"CONFLICT", "UNDO_CONFLICT", "FAILED"}


def _json(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


class PlanDiffService:
    """Deterministic, database-backed diff for two immutable plan versions."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def diff(self, old_plan_version_id: str, new_plan_version_id: str) -> dict[str, Any]:
        if old_plan_version_id == new_plan_version_id:
            raise ValueError("PLAN_DIFF_REQUIRES_TWO_VERSIONS")
        with self.database.engine.connect() as connection:
            versions = connection.execute(text("""
                SELECT id,conversation_id,version_number,plan_id,plan_hash,taxonomy_snapshot_json
                FROM conversation_plan_versions WHERE id IN (:old,:new)
            """), {"old": old_plan_version_id, "new": new_plan_version_id}).mappings().all()
            by_id = {row["id"]: row for row in versions}
            old = by_id.get(old_plan_version_id)
            new = by_id.get(new_plan_version_id)
            if old is None or new is None:
                raise KeyError(old_plan_version_id if old is None else new_plan_version_id)
            if old["conversation_id"] != new["conversation_id"]:
                raise ValueError("PLAN_VERSION_SCOPE_CONFLICT")
            old_ops = self._operations(connection, old["plan_id"])
            new_ops = self._operations(connection, new["plan_id"])

        category_diff = self._categories(_json(old["taxonomy_snapshot_json"], {}), _json(new["taxonomy_snapshot_json"], {}))
        file_changes = self._files(old_ops, new_ops)
        counts = {
            "total": len(file_changes),
            "unchanged": sum(item["change_type"] == "UNCHANGED" for item in file_changes),
            "added": sum(item["change_type"] == "ADDED" for item in file_changes),
            "removed": sum(item["change_type"] == "REMOVED" for item in file_changes),
            "target_changed": sum(item["change_type"] == "TARGET_CHANGED" for item in file_changes),
            "keep_changed": sum(item["change_type"] == "KEEP_CHANGED" for item in file_changes),
            "conflict_changed": sum(item["change_type"] == "CONFLICT_CHANGED" for item in file_changes),
        }
        return {
            "old_plan_version_id": old_plan_version_id,
            "new_plan_version_id": new_plan_version_id,
            "old_version_number": old["version_number"],
            "new_version_number": new["version_number"],
            "categories_added": category_diff["categories_added"],
            "categories_removed": category_diff["categories_removed"],
            "category_changes": category_diff["category_changes"],
            "file_changes": file_changes,
            "affected_file_ids": [item["file_id"] for item in file_changes if item["change_type"] != "UNCHANGED"],
            "summary_counts": {**counts, "categories_added": len(category_diff["categories_added"]),
                                "categories_removed": len(category_diff["categories_removed"]),
                                "categories_changed": len(category_diff["category_changes"])},
        }

    @staticmethod
    def _operations(connection, plan_id: str | None) -> dict[str, dict[str, Any]]:
        if not plan_id:
            return {}
        rows = connection.execute(text("""
            SELECT file_id,action,target_path,state,expected_sha256,source_path
            FROM operations WHERE plan_id=:plan ORDER BY ordinal
        """), {"plan": plan_id}).mappings().all()
        return {str(row["file_id"]): dict(row) for row in rows}

    @staticmethod
    def _nodes(snapshot: Any) -> dict[str, dict[str, Any]]:
        if isinstance(snapshot, dict):
            candidates = snapshot.get("nodes") or snapshot.get("categories") or snapshot.get("tree") or []
        elif isinstance(snapshot, list):
            candidates = snapshot
        else:
            candidates = []
        result: dict[str, dict[str, Any]] = {}
        for node in candidates:
            if not isinstance(node, dict):
                continue
            key = node.get("category_id") or node.get("id") or node.get("categoryId")
            if key is not None:
                result[str(key)] = dict(node)
        return result

    @classmethod
    def _categories(cls, old_snapshot: Any, new_snapshot: Any) -> dict[str, Any]:
        old_nodes = cls._nodes(old_snapshot)
        new_nodes = cls._nodes(new_snapshot)
        added = [new_nodes[key] for key in sorted(set(new_nodes) - set(old_nodes))]
        removed = [old_nodes[key] for key in sorted(set(old_nodes) - set(new_nodes))]
        changes = []
        for key in sorted(set(old_nodes) & set(new_nodes)):
            old_node, new_node = old_nodes[key], new_nodes[key]
            old_name = old_node.get("name") or old_node.get("label")
            new_name = new_node.get("name") or new_node.get("label")
            old_parent = old_node.get("parent_id") or old_node.get("parentId")
            new_parent = new_node.get("parent_id") or new_node.get("parentId")
            if old_name != new_name or old_parent != new_parent:
                changes.append({"category_id": key, "old": old_node, "new": new_node,
                                "renamed": old_name != new_name, "reparented": old_parent != new_parent})
        return {"categories_added": added, "categories_removed": removed, "category_changes": changes}

    @staticmethod
    def _files(old_ops: dict[str, dict[str, Any]], new_ops: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for file_id in sorted(set(old_ops) | set(new_ops)):
            old, new = old_ops.get(file_id), new_ops.get(file_id)
            if old is None:
                change_type = "ADDED"
            elif new is None:
                change_type = "REMOVED"
            elif bool(old["state"] in CONFLICT_STATES) != bool(new["state"] in CONFLICT_STATES):
                change_type = "CONFLICT_CHANGED"
            elif (old["action"] in KEEP_ACTIONS) != (new["action"] in KEEP_ACTIONS):
                change_type = "KEEP_CHANGED"
            elif old["target_path"] != new["target_path"]:
                change_type = "TARGET_CHANGED"
            else:
                change_type = "UNCHANGED"
            changes.append({
                "file_id": file_id,
                "change_type": change_type,
                "old": old,
                "new": new,
            })
        return changes


class PlanVersionService:
    """Conversation-level version authority; core Plan remains the execution source."""

    def __init__(self, repository: ConversationRepository, database: Database) -> None:
        self.repository = repository
        self.database = database
        self.diff_service = PlanDiffService(database)

    def create_new_version(self, conversation_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.repository.create_plan_version(conversation_id, **kwargs)

    def get(self, plan_version_id: str) -> dict[str, Any]:
        return self.repository.get_plan_version(plan_version_id)

    def list(self, conversation_id: str) -> list[dict[str, Any]]:
        self.repository.get(conversation_id)
        return self.repository.list_plan_versions(conversation_id)

    def current(self, conversation_id: str) -> dict[str, Any]:
        self.repository.get(conversation_id)
        return self.repository.get_current_plan_version(conversation_id)

    def diff(self, old_plan_version_id: str, new_plan_version_id: str) -> dict[str, Any]:
        return self.diff_service.diff(old_plan_version_id, new_plan_version_id)

    def approve(self, conversation_id: str, plan_version_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.repository.approve_plan_version(conversation_id, plan_version_id, **kwargs)

    def request_execution(self, conversation_id: str, plan_version_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.repository.request_execution(conversation_id, plan_version_id, **kwargs)

    def restore(self, conversation_id: str, target_version_id: str, *,
                expected_context_revision: int | None = None,
                expected_current_plan_version_id: str | None = None) -> dict[str, Any]:
        target = self.repository.get_plan_version(target_version_id)
        conversation = self.repository.get(conversation_id)
        if target["conversation_id"] != conversation_id:
            raise ValueError("PLAN_VERSION_SCOPE_CONFLICT")
        current = self.repository.get_current_plan_version(conversation_id) if conversation.get("context", {}).get("current_plan_version_id") else None
        if current and expected_current_plan_version_id and current["id"] != expected_current_plan_version_id:
            raise ValueError("PLAN_VERSION_CONFLICT")
        context = self.repository.get_context(conversation_id)
        if expected_context_revision is not None and context["context_revision"] != expected_context_revision:
            raise ValueError("CONTEXT_REVISION_CONFLICT")
        if not target.get("plan_id") or not target.get("plan_hash"):
            raise ValueError("PLAN_VERSION_NOT_RESTORABLE")
        self._validate_file_state(conversation_id)
        parent_id = current["id"] if current else None
        return self.create_new_version(
            conversation_id,
            expected_context_revision=context["context_revision"],
            basis_context_revision=context["context_revision"],
            parent_plan_version_id=parent_id,
            source="USER_REQUEST",
            status="PROPOSED",
            taxonomy_id=target.get("taxonomy_id"),
            taxonomy_snapshot=target.get("taxonomy_snapshot") or {},
            plan_id=target.get("plan_id"),
            plan_hash=target.get("plan_hash"),
            summary=f"恢复方案 v{target['version_number']}",
            change_summary={"restored_from_version_id": target_version_id},
            affected_file_count=target.get("affected_file_count", 0),
            kept_file_count=target.get("kept_file_count", 0),
            conflict_count=target.get("conflict_count", 0),
            restored_from_version_id=target_version_id,
        )

    def _validate_file_state(self, conversation_id: str) -> None:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT cf.file_id,cf.current_known_path,cf.current_fingerprint,cf.state,
                       cs.source_root
                FROM conversation_files cf
                LEFT JOIN conversation_scopes cs ON cs.conversation_id=cf.conversation_id AND cs.revoked_at IS NULL
                WHERE cf.conversation_id=:conversation AND cf.removed_from_scope_at IS NULL
            """), {"conversation": conversation_id}).mappings().all()
        for row in rows:
            if row["state"] in {"FILE_CHANGED", "MISSING", "REMOVED"}:
                raise ValueError("PLAN_RESTORE_FILE_CHANGED")
            path = Path(str(row["current_known_path"]))
            try:
                identity = read_identity(path)
            except OSError as exc:
                raise ValueError("PLAN_RESTORE_FILE_CHANGED") from exc
            if row["current_fingerprint"] and identity.sha256 != row["current_fingerprint"]:
                raise ValueError("PLAN_RESTORE_FILE_CHANGED")
            roots = [Path(str(row["source_root"])) for row in rows if row["source_root"]]
            if roots and not any(path == root or root in path.parents for root in roots):
                raise ValueError("PLAN_RESTORE_SCOPE_CHANGED")
