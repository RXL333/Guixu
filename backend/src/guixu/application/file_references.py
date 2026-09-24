from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text

from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database


DEICTIC_SINGLE = ("这个", "这张", "这个文件", "这一个")
DEICTIC_PLURAL = ("这些", "这几个", "刚才那几个", "前面那些")
LATEST_PLAN_MARKERS = ("刚才修改的", "刚才改动的", "当前方案", "这次方案")
LATEST_EXECUTION_MARKERS = ("上一次移动的", "上次移动的", "上一次执行的", "刚才实际移动的")
CATEGORY_ALL_MARKERS = ("这个类别里的所有文件", "当前类别里的所有文件", "该类别的所有文件")


class ReferenceResolutionError(ValueError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details or {}


class ReferenceResolver:
    """Resolve Conversation-local references deterministically; never asks a model for IDs."""

    def __init__(self, database: Database, conversations: ConversationRepository) -> None:
        self.database = database
        self.conversations = conversations

    def resolve(self, conversation_id: str, message: str, *, selected_file_ids: list[str] | None = None,
                focused_file_id: str | None = None, active_category_id: str | None = None) -> dict[str, Any]:
        selected = list(dict.fromkeys(selected_file_ids or []))
        if selected:
            return self._validated(conversation_id, selected, "UI_SELECTION", "User explicitly selected files")
        if focused_file_id:
            return self._validated(conversation_id, [focused_file_id], "FOCUSED_FILE", "User focused one file")

        exact = self._exact_filename(conversation_id, message)
        if exact:
            return self._validated(conversation_id, exact, "EXPLICIT_FILENAME", "Unique exact filename in current Conversation")

        if any(marker in message for marker in LATEST_EXECUTION_MARKERS):
            ids = self._latest_execution_files(conversation_id)
            if not ids:
                raise ReferenceResolutionError("REFERENCE_NOT_FOUND")
            return self._validated(conversation_id, ids, "LATEST_EXECUTION_AFFECTED", "Latest completed execution results")

        if any(marker in message for marker in LATEST_PLAN_MARKERS):
            ids = self._latest_plan_files(conversation_id)
            if not ids:
                raise ReferenceResolutionError("REFERENCE_NOT_FOUND")
            return self._validated(conversation_id, ids, "LATEST_PLAN_AFFECTED", "Current PlanVersion affected files")

        if any(marker in message for marker in CATEGORY_ALL_MARKERS):
            if not active_category_id:
                raise ReferenceResolutionError("REFERENCE_CATEGORY_NOT_FOUND")
            ids = self._category_files(conversation_id, active_category_id)
            if not ids:
                raise ReferenceResolutionError("REFERENCE_CATEGORY_NOT_FOUND")
            return self._validated(conversation_id, ids, "ACTIVE_CATEGORY_ALL", "Explicit all-files request for active category")

        if any(marker in message for marker in DEICTIC_SINGLE):
            raise ReferenceResolutionError("REFERENCE_AMBIGUOUS", details={"expected": "single_file"})

        if any(marker in message for marker in DEICTIC_PLURAL):
            recent = self._recent_message_files(conversation_id)
            if recent:
                return self._validated(conversation_id, recent, "RECENT_MESSAGE_REFERENCE", "Latest visible message file set")
            raise ReferenceResolutionError("REFERENCE_AMBIGUOUS", details={"expected": "file_set"})

        return {"source": "NONE", "file_ids": [], "count": 0, "missing": [], "changed": [],
                "scope_valid": True, "confidence": 1.0, "requires_confirmation": False,
                "reason": "No file reference was expressed"}

    def _validated(self, conversation_id: str, file_ids: list[str], source: str, reason: str) -> dict[str, Any]:
        if not file_ids:
            raise ReferenceResolutionError("REFERENCE_SET_EMPTY")
        placeholders = ",".join(f":f{i}" for i in range(len(file_ids)))
        params = {"conversation": conversation_id, **{f"f{i}": value for i, value in enumerate(file_ids)}}
        with self.database.engine.connect() as connection:
            rows = list(connection.execute(text(f"""
                SELECT cf.file_id,cf.state,cf.current_known_path,cf.current_fingerprint,
                       cf.current_size_bytes,cf.current_mtime_ns
                FROM conversation_files cf
                WHERE cf.conversation_id=:conversation AND cf.removed_from_scope_at IS NULL
                  AND cf.file_id IN ({placeholders})
            """), params).mappings())
            roots = [Path(str(row[0])) for row in connection.execute(text("""
                SELECT source_root FROM conversation_scopes
                WHERE conversation_id=:conversation AND revoked_at IS NULL
            """), {"conversation": conversation_id})]
        found = {str(row["file_id"]): row for row in rows}
        if set(found) != set(file_ids):
            raise ReferenceResolutionError("REFERENCE_SCOPE_VIOLATION", details={"invalid_count": len(set(file_ids) - set(found))})
        outside = [file_id for file_id, row in found.items()
                   if not any(Path(str(row["current_known_path"])) == root or root in Path(str(row["current_known_path"])).parents for root in roots)]
        if outside:
            raise ReferenceResolutionError("REFERENCE_SCOPE_VIOLATION", details={"invalid_count": len(outside)})
        missing = [file_id for file_id, row in found.items()
                   if row["state"] in {"MISSING", "REMOVED"} or not Path(str(row["current_known_path"])).is_file()]
        changed = [file_id for file_id, row in found.items() if row["state"] == "FILE_CHANGED"]
        return {"source": source, "file_ids": file_ids, "count": len(file_ids), "missing": missing,
                "changed": changed, "scope_valid": True, "confidence": 1.0,
                "requires_confirmation": bool(missing or changed), "reason": reason}

    def _exact_filename(self, conversation_id: str, message: str) -> list[str]:
        with self.database.engine.connect() as connection:
            rows = list(connection.execute(text("""
                SELECT cf.file_id,f.basename FROM conversation_files cf JOIN files f ON f.id=cf.file_id
                WHERE cf.conversation_id=:conversation AND cf.removed_from_scope_at IS NULL
            """), {"conversation": conversation_id}).mappings())
        matches: dict[str, list[str]] = {}
        folded = message.casefold()
        for row in rows:
            name = str(row["basename"])
            if name.casefold() in folded:
                matches.setdefault(name.casefold(), []).append(str(row["file_id"]))
        if not matches:
            return []
        # If `a.jpg` is a suffix of an explicitly mentioned `ba.jpg`, only the
        # longest visible filename is an exact reference.
        for name in list(matches):
            if any(name != other and name in other for other in matches):
                matches.pop(name)
        duplicated = [name for name, ids in matches.items() if len(ids) > 1]
        if duplicated:
            raise ReferenceResolutionError("REFERENCE_DUPLICATE_FILENAME", details={"filenames": duplicated})
        return [ids[0] for ids in matches.values()]

    def _recent_message_files(self, conversation_id: str) -> list[str]:
        with self.database.engine.connect() as connection:
            message_id = connection.execute(text("""
                SELECT m.id FROM conversation_messages m
                WHERE m.conversation_id=:conversation AND m.status='ACTIVE'
                  AND EXISTS (SELECT 1 FROM conversation_message_file_references r WHERE r.message_id=m.id)
                ORDER BY m.sequence_number DESC LIMIT 1
            """), {"conversation": conversation_id}).scalar()
            if not message_id:
                return []
            return [str(row[0]) for row in connection.execute(text("""
                SELECT file_id FROM conversation_message_file_references WHERE message_id=:message ORDER BY rowid
            """), {"message": message_id})]

    def _latest_plan_files(self, conversation_id: str) -> list[str]:
        current = self.conversations.get_current_plan_version(conversation_id)
        changes = current.get("change_summary") or {}
        return list(dict.fromkeys(str(item["file_id"]) for item in changes.get("moves", [])
                                  if isinstance(item, dict) and item.get("file_id")))

    def _latest_execution_files(self, conversation_id: str) -> list[str]:
        with self.database.engine.connect() as connection:
            plan_id = connection.execute(text("""
                SELECT execution_plan_id FROM conversation_execution_rounds
                WHERE conversation_id=:conversation AND status='COMPLETED'
                ORDER BY round_number DESC LIMIT 1
            """), {"conversation": conversation_id}).scalar()
            if not plan_id:
                return []
            return [str(row[0]) for row in connection.execute(text("""
                SELECT file_id FROM operations WHERE plan_id=:plan AND state IN ('COMMITTED','UNDONE') ORDER BY ordinal
            """), {"plan": plan_id})]

    def _category_files(self, conversation_id: str, category_id: str) -> list[str]:
        with self.database.engine.connect() as connection:
            return [str(row[0]) for row in connection.execute(text("""
                SELECT file_id FROM conversation_files
                WHERE conversation_id=:conversation AND current_category_id=:category AND removed_from_scope_at IS NULL
                ORDER BY added_at
            """), {"conversation": conversation_id, "category": category_id})]
