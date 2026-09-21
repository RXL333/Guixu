from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import canonical_json
from guixu.infrastructure.filesystem.identity import read_identity


JSON_COLUMNS = {
    "metadata_json": "metadata",
    "organization_intent_json": "organization_intent",
    "confirmed_requirements_json": "confirmed_requirements",
    "privacy_scope_json": "privacy_scope",
    "selection_state_json": "selection_state",
    "strategy_state_json": "strategy_state",
    "taxonomy_snapshot_json": "taxonomy_snapshot",
    "change_summary_json": "change_summary",
    "summary_json": "summary",
}


def _decode_json(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    result = dict(row)
    for column in columns:
        if column in result:
            target = JSON_COLUMNS.get(column, column.removesuffix("_json"))
            value = result.pop(column)
            result[target] = json.loads(value or ("[]" if target == "confirmed_requirements" else "{}"))
    return result


class ConversationRepository:
    """Persistence boundary for the PHASE D state layer.

    This repository deliberately does not invoke models, planners, executors, or
    undo. It only stores typed durable state and references existing core rows.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        title: str = "未命名整理",
        *,
        model_profile_id: str | None = None,
        scope: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_title = title.strip() or "未命名整理"
        if len(clean_title) > 160:
            raise ValueError("CONVERSATION_TITLE_INVALID")
        conversation_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        now = utc_now()
        state = context or {}
        if model_profile_id:
            with self.database.engine.connect() as connection:
                if connection.execute(text("SELECT 1 FROM model_profiles WHERE id=:id"), {"id": model_profile_id}).first() is None:
                    raise KeyError(model_profile_id)
        with self.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO conversations(id,title,status,model_profile_id,metadata_json,created_at,updated_at)
                VALUES(:id,:title,'ACTIVE',:model,:metadata,:now,:now)
            """), {"id": conversation_id, "title": clean_title, "model": model_profile_id,
                    "metadata": canonical_json(metadata or {}), "now": now})
            connection.execute(text("""
                INSERT INTO conversation_contexts(
                  id,conversation_id,context_revision,model_profile_id,max_directory_depth,
                  organization_intent_json,confirmed_requirements_json,privacy_scope_json,
                  selection_state_json,file_state_revision,strategy_state_json,created_at,updated_at
                ) VALUES(:id,:conversation,:revision,:model,:depth,:intent,:requirements,:privacy,
                         :selection,1,:strategy,:now,:now)
            """), {
                "id": context_id, "conversation": conversation_id, "revision": 1,
                "model": model_profile_id, "depth": int(state.get("max_directory_depth", 2)),
                "intent": canonical_json(state.get("organization_intent", {})),
                "requirements": canonical_json(state.get("confirmed_requirements", [])),
                "privacy": canonical_json(state.get("privacy_scope", {})),
                "selection": canonical_json(state.get("selection_state", {})),
                "strategy": canonical_json(state.get("strategy_state", {})), "now": now,
            })
            if scope is not None:
                self._insert_scope(connection, conversation_id, scope, now)
        return self.get(conversation_id)

    @staticmethod
    def _scope_hash(scope: dict[str, Any]) -> str:
        return hashlib.sha256(canonical_json({
            "source_root": str(scope["source_root"]),
            "display_name": str(scope.get("display_name") or Path(str(scope["source_root"])).name),
            "scope_kind": str(scope.get("scope_kind", "folder")),
        }).encode("utf-8")).hexdigest()

    def _insert_scope(self, connection, conversation_id: str, scope: dict[str, Any], now: str) -> str:
        scope_id = str(scope.get("id") or uuid.uuid4())
        source_root = str(scope["source_root"])
        display_name = str(scope.get("display_name") or Path(source_root).name or source_root)
        connection.execute(text("""
            INSERT INTO conversation_scopes(
              id,conversation_id,scope_kind,source_root,display_name,authorization_ref,
              authorization_json,scope_hash,created_at
            ) VALUES(:id,:conversation,:kind,:root,:display,:ref,:authorization,:hash,:now)
        """), {
            "id": scope_id, "conversation": conversation_id,
            "kind": scope.get("scope_kind", "folder"), "root": source_root,
            "display": display_name, "ref": scope.get("authorization_ref"),
            "authorization": canonical_json(scope.get("authorization", {})),
            "hash": scope.get("scope_hash") or self._scope_hash(scope), "now": now,
        })
        return scope_id

    def get(self, conversation_id: str, *, include_deleted: bool = True) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversations WHERE id=:id"), {"id": conversation_id}).mappings().first()
            if row is None or (not include_deleted and row["deleted_at"] is not None):
                raise KeyError(conversation_id)
            result = _decode_json(dict(row), ("metadata_json",))
            context = connection.execute(text("SELECT * FROM conversation_contexts WHERE conversation_id=:id"), {"id": conversation_id}).mappings().first()
            scopes = connection.execute(text("SELECT * FROM conversation_scopes WHERE conversation_id=:id ORDER BY created_at,id"), {"id": conversation_id}).mappings().all()
            linked_tasks = connection.execute(text("""
                SELECT id,name,status,phase,revision,conversation_plan_version_id
                FROM tasks WHERE conversation_id=:id ORDER BY updated_at DESC,id
            """), {"id": conversation_id}).mappings().all()
        result["scopes"] = [dict(item) for item in scopes]
        result["context"] = self._context_from_row(context) if context else None
        result["tasks"] = [dict(item) for item in linked_tasks]
        return result

    def list(self, view: str = "active") -> list[dict[str, Any]]:
        if view not in {"active", "deleted", "all"}:
            raise ValueError("CONVERSATION_VIEW_INVALID")
        clause = {"active": "WHERE deleted_at IS NULL", "deleted": "WHERE deleted_at IS NOT NULL", "all": ""}[view]
        with self.database.engine.connect() as connection:
            rows = connection.execute(text(f"""
                SELECT id,title,status,model_profile_id,metadata_json,created_at,updated_at,deleted_at,last_message_at
                FROM conversations {clause} ORDER BY COALESCE(last_message_at,updated_at) DESC,id
            """)).mappings().all()
        return [_decode_json(dict(row), ("metadata_json",)) for row in rows]

    def rename(self, conversation_id: str, title: str) -> dict[str, Any]:
        clean = title.strip()
        if not clean or len(clean) > 160:
            raise ValueError("CONVERSATION_TITLE_INVALID")
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE conversations SET title=:title,revision=revision+1,updated_at=:now
                WHERE id=:id AND deleted_at IS NULL
            """), {"id": conversation_id, "title": clean, "now": utc_now()})
            if result.rowcount != 1:
                if connection.execute(text("SELECT 1 FROM conversations WHERE id=:id"), {"id": conversation_id}).first() is None:
                    raise KeyError(conversation_id)
                raise ValueError("CONVERSATION_DELETED")
        return self.get(conversation_id)

    def soft_delete(self, conversation_id: str) -> dict[str, Any]:
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE conversations SET status='DELETED',deleted_at=:now,revision=revision+1,updated_at=:now WHERE id=:id
            """), {"id": conversation_id, "now": utc_now()})
            if result.rowcount != 1:
                raise KeyError(conversation_id)
        return self.get(conversation_id)

    def restore(self, conversation_id: str) -> dict[str, Any]:
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE conversations SET status='ACTIVE',deleted_at=NULL,revision=revision+1,updated_at=:now WHERE id=:id
            """), {"id": conversation_id, "now": utc_now()})
            if result.rowcount != 1:
                raise KeyError(conversation_id)
        return self.get(conversation_id)

    def archive(self, conversation_id: str) -> dict[str, Any]:
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE conversations SET status='ARCHIVED',revision=revision+1,updated_at=:now
                WHERE id=:id AND deleted_at IS NULL
            """), {"id": conversation_id, "now": utc_now()})
            if result.rowcount != 1:
                if connection.execute(text("SELECT 1 FROM conversations WHERE id=:id"), {"id": conversation_id}).first() is None:
                    raise KeyError(conversation_id)
                raise ValueError("CONVERSATION_DELETED")
        return self.get(conversation_id)

    def activate(self, conversation_id: str) -> dict[str, Any]:
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE conversations SET status='ACTIVE',revision=revision+1,updated_at=:now
                WHERE id=:id AND deleted_at IS NULL
            """), {"id": conversation_id, "now": utc_now()})
            if result.rowcount != 1:
                if connection.execute(text("SELECT 1 FROM conversations WHERE id=:id"), {"id": conversation_id}).first() is None:
                    raise KeyError(conversation_id)
                raise ValueError("CONVERSATION_DELETED")
        return self.get(conversation_id)

    def get_context(self, conversation_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_contexts WHERE conversation_id=:id"), {"id": conversation_id}).mappings().first()
        if row is None:
            raise KeyError(conversation_id)
        return self._context_from_row(row)

    @staticmethod
    def _context_from_row(row) -> dict[str, Any]:
        return _decode_json(dict(row), (
            "organization_intent_json", "confirmed_requirements_json", "privacy_scope_json",
            "selection_state_json", "strategy_state_json",
        ))

    def update_context(self, conversation_id: str, expected_revision: int, changes: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "current_taxonomy_id", "current_plan_version_id", "current_execution_round_id", "model_profile_id",
            "max_directory_depth", "organization_intent", "confirmed_requirements", "privacy_scope",
            "selection_state", "strategy_state",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError("CONTEXT_FIELD_INVALID")
        if "max_directory_depth" in changes and int(changes["max_directory_depth"]) not in {1, 2, 3}:
            raise ValueError("MAX_DIRECTORY_DEPTH_INVALID")
        if not changes:
            return self.get_context(conversation_id)
        assignments = ["context_revision=context_revision+1", "updated_at=:now"]
        params: dict[str, Any] = {"id": conversation_id, "revision": expected_revision, "now": utc_now()}
        json_names = {"organization_intent": "organization_intent_json", "confirmed_requirements": "confirmed_requirements_json",
                      "privacy_scope": "privacy_scope_json", "selection_state": "selection_state_json", "strategy_state": "strategy_state_json"}
        for key, value in changes.items():
            column = json_names.get(key, key)
            assignments.append(f"{column}=:{key}")
            params[key] = canonical_json(value) if key in json_names else value
        if "selection_state" in changes:
            assignments.append("file_state_revision=file_state_revision+1")
        with self.database.begin() as connection:
            result = connection.execute(text(f"""
                UPDATE conversation_contexts SET {','.join(assignments)}
                WHERE conversation_id=:id AND context_revision=:revision
            """), params)
            if result.rowcount != 1:
                if connection.execute(text("SELECT 1 FROM conversation_contexts WHERE conversation_id=:id"), {"id": conversation_id}).first() is None:
                    raise KeyError(conversation_id)
                raise ValueError("CONTEXT_REVISION_CONFLICT")
            connection.execute(text("""
                UPDATE conversation_plan_approvals SET status='STALE',superseded_at=:now
                WHERE conversation_id=:id AND status='ACTIVE'
            """), {"id": conversation_id, "now": params["now"]})
            connection.execute(text("UPDATE conversations SET updated_at=:now WHERE id=:id"), {"id": conversation_id, "now": params["now"]})
        return self.get_context(conversation_id)

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        message_type: str = "TEXT",
        metadata: dict[str, Any] | None = None,
        referenced_plan_version_id: str | None = None,
        referenced_execution_round_id: str | None = None,
    ) -> dict[str, Any]:
        if not content.strip():
            raise ValueError("MESSAGE_CONTENT_REQUIRED")
        message_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.begin() as connection:
            conversation = connection.execute(text("SELECT deleted_at FROM conversations WHERE id=:id"), {"id": conversation_id}).first()
            if conversation is None:
                raise KeyError(conversation_id)
            if conversation[0] is not None:
                raise ValueError("CONVERSATION_DELETED")
            sequence = int(connection.execute(text("SELECT COALESCE(MAX(sequence_number),0)+1 FROM conversation_messages WHERE conversation_id=:id"), {"id": conversation_id}).scalar_one())
            connection.execute(text("""
                INSERT INTO conversation_messages(
                  id,conversation_id,role,content,sequence_number,message_type,status,
                  referenced_plan_version_id,referenced_execution_round_id,metadata_json,created_at
                ) VALUES(:id,:conversation,:role,:content,:sequence,:type,'ACTIVE',:plan,:round,:metadata,:now)
            """), {"id": message_id, "conversation": conversation_id, "role": role, "content": content,
                    "sequence": sequence, "type": message_type, "plan": referenced_plan_version_id,
                    "round": referenced_execution_round_id, "metadata": canonical_json(metadata or {}), "now": now})
            connection.execute(text("UPDATE conversations SET last_message_at=:now,updated_at=:now WHERE id=:id"), {"id": conversation_id, "now": now})
        return self.get_message(message_id)

    def get_message(self, message_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_messages WHERE id=:id"), {"id": message_id}).mappings().first()
        if row is None:
            raise KeyError(message_id)
        return _decode_json(dict(row), ("metadata_json",))

    def list_messages(self, conversation_id: str, *, include_redacted: bool = False) -> list[dict[str, Any]]:
        clause = "" if include_redacted else " AND status='ACTIVE'"
        with self.database.engine.connect() as connection:
            rows = connection.execute(text(f"SELECT * FROM conversation_messages WHERE conversation_id=:id{clause} ORDER BY sequence_number"), {"id": conversation_id}).mappings().all()
        return [_decode_json(dict(row), ("metadata_json",)) for row in rows]

    def create_plan_version(
        self,
        conversation_id: str,
        *,
        basis_context_revision: int | None = None,
        expected_context_revision: int | None = None,
        parent_plan_version_id: str | None = None,
        baseline_execution_round_id: str | None = None,
        source: str = "USER_REQUEST",
        plan_kind: str = "FULL",
        status: str = "DRAFT",
        taxonomy_id: str | None = None,
        taxonomy_snapshot: dict[str, Any] | None = None,
        plan_id: str | None = None,
        plan_hash: str | None = None,
        summary: str = "",
        change_summary: dict[str, Any] | None = None,
        affected_file_count: int = 0,
        kept_file_count: int = 0,
        conflict_count: int = 0,
        created_by_message_id: str | None = None,
        restored_from_version_id: str | None = None,
    ) -> dict[str, Any]:
        if affected_file_count < 0 or kept_file_count < 0 or conflict_count < 0:
            raise ValueError("PLAN_VERSION_COUNTS_INVALID")
        if plan_kind not in {"FULL", "DELTA"}:
            raise ValueError("PLAN_KIND_INVALID")
        if plan_kind == "DELTA" and not baseline_execution_round_id:
            raise ValueError("NO_EXECUTED_BASELINE")
        if status in {"APPROVED", "EXECUTED"}:
            raise ValueError("PLAN_VERSION_LIFECYCLE_INVALID")
        for attempt in range(3):
            plan_version_id = str(uuid.uuid4())
            now = utc_now()
            try:
                with self.database.begin() as connection:
                    context = connection.execute(text("SELECT context_revision,current_plan_version_id FROM conversation_contexts WHERE conversation_id=:id"), {"id": conversation_id}).first()
                    if context is None:
                        raise KeyError(conversation_id)
                    current_revision = int(context[0])
                    if expected_context_revision is not None and current_revision != expected_context_revision:
                        raise ValueError("CONTEXT_REVISION_CONFLICT")
                    basis = int(basis_context_revision or current_revision)
                    if basis > current_revision:
                        raise ValueError("PLAN_CONTEXT_STALE")
                    if parent_plan_version_id:
                        parent = connection.execute(text("SELECT conversation_id,version_number FROM conversation_plan_versions WHERE id=:id"), {"id": parent_plan_version_id}).first()
                        if parent is None or parent[0] != conversation_id:
                            raise ValueError("PLAN_VERSION_PARENT_INVALID")
                        if context[1] is not None and context[1] != parent_plan_version_id:
                            raise ValueError("PLAN_VERSION_PARENT_NOT_CURRENT")
                    else:
                        parent_plan_version_id = connection.execute(text("SELECT id FROM conversation_plan_versions WHERE conversation_id=:id ORDER BY version_number DESC LIMIT 1"), {"id": conversation_id}).scalar()
                    if restored_from_version_id:
                        restored = connection.execute(text("SELECT conversation_id FROM conversation_plan_versions WHERE id=:id"), {"id": restored_from_version_id}).first()
                        if restored is None or restored[0] != conversation_id:
                            raise ValueError("PLAN_VERSION_RESTORE_SOURCE_INVALID")
                    if baseline_execution_round_id:
                        baseline = connection.execute(text("""
                            SELECT conversation_id,status FROM conversation_execution_rounds WHERE id=:id
                        """), {"id": baseline_execution_round_id}).first()
                        if baseline is None or baseline[0] != conversation_id:
                            raise ValueError("EXECUTION_BASELINE_INVALID")
                        if baseline[1] != "COMPLETED":
                            raise ValueError("NO_EXECUTED_BASELINE")
                    if created_by_message_id:
                        message = connection.execute(text("SELECT conversation_id FROM conversation_messages WHERE id=:id"), {"id": created_by_message_id}).first()
                        if message is None or message[0] != conversation_id:
                            raise ValueError("PLAN_VERSION_MESSAGE_INVALID")
                    if plan_id:
                        plan_row = connection.execute(text("SELECT plan_hash FROM plans WHERE id=:id"), {"id": plan_id}).first()
                        if plan_row is None:
                            raise KeyError(plan_id)
                        if plan_hash is None:
                            plan_hash = plan_row[0]
                        if plan_row[0] != plan_hash:
                            raise ValueError("PLAN_HASH_MISMATCH")
                    number = int(connection.execute(text("SELECT COALESCE(MAX(version_number),0)+1 FROM conversation_plan_versions WHERE conversation_id=:id"), {"id": conversation_id}).scalar_one())
                    connection.execute(text("""
                        INSERT INTO conversation_plan_versions(
                          id,conversation_id,version_number,parent_plan_version_id,baseline_execution_round_id,
                          basis_context_revision,source,plan_kind,status,taxonomy_id,taxonomy_snapshot_json,plan_id,plan_hash,summary,
                          change_summary_json,affected_file_count,kept_file_count,conflict_count,
                          created_by_message_id,restored_from_version_id,created_at
                        ) VALUES(:id,:conversation,:number,:parent,:baseline,:basis,:source,:plan_kind,:status,:taxonomy,:snapshot,
                                 :plan,:hash,:summary,:changes,:affected,:kept,:conflicts,:message,:restored,:now)
                    """), {"id": plan_version_id, "conversation": conversation_id, "number": number,
                            "parent": parent_plan_version_id, "basis": basis, "source": source, "status": status,
                            "baseline": baseline_execution_round_id, "plan_kind": plan_kind,
                            "taxonomy": taxonomy_id, "snapshot": canonical_json(taxonomy_snapshot or {}),
                            "plan": plan_id, "hash": plan_hash, "summary": summary,
                            "changes": canonical_json(change_summary or {}), "affected": affected_file_count,
                            "kept": kept_file_count, "conflicts": conflict_count, "message": created_by_message_id,
                            "restored": restored_from_version_id, "now": now})
                    if parent_plan_version_id:
                        connection.execute(text("""
                            UPDATE conversation_plan_versions
                            SET status='SUPERSEDED',superseded_at=:now
                            WHERE id=:parent AND status IN ('DRAFT','PROPOSED','APPROVED')
                        """), {"parent": parent_plan_version_id, "now": now})
                    pointer = connection.execute(text("""
                        UPDATE conversation_contexts SET current_plan_version_id=:plan,context_revision=context_revision+1,updated_at=:now
                        WHERE conversation_id=:conversation AND context_revision=:revision
                    """), {"plan": plan_version_id, "conversation": conversation_id, "revision": current_revision, "now": now})
                    if pointer.rowcount != 1:
                        raise ValueError("CONTEXT_REVISION_CONFLICT")
                    connection.execute(text("""
                        UPDATE conversation_plan_approvals SET status='STALE',superseded_at=:now
                        WHERE conversation_id=:conversation AND status='ACTIVE'
                    """), {"conversation": conversation_id, "now": now})
                return self.get_plan_version(plan_version_id)
            except IntegrityError as exc:
                if "conversation_plan_versions" not in str(exc).lower() or attempt == 2:
                    raise ValueError("PLAN_VERSION_CONFLICT") from exc
        raise ValueError("PLAN_VERSION_CONFLICT")

    def get_plan_version(self, plan_version_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_plan_versions WHERE id=:id"), {"id": plan_version_id}).mappings().first()
        if row is None:
            raise KeyError(plan_version_id)
        return _decode_json(dict(row), ("taxonomy_snapshot_json", "change_summary_json"))

    def list_plan_versions(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM conversation_plan_versions WHERE conversation_id=:id ORDER BY version_number"), {"id": conversation_id}).mappings().all()
        return [_decode_json(dict(row), ("taxonomy_snapshot_json", "change_summary_json")) for row in rows]

    def get_current_plan_version(self, conversation_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT p.* FROM conversation_contexts c
                JOIN conversation_plan_versions p ON p.id=c.current_plan_version_id
                WHERE c.conversation_id=:conversation
            """), {"conversation": conversation_id}).mappings().first()
        if row is None:
            raise KeyError("CURRENT_PLAN_VERSION_NOT_FOUND")
        return _decode_json(dict(row), ("taxonomy_snapshot_json", "change_summary_json"))

    def approve_plan_version(self, conversation_id: str, plan_version_id: str, *,
                             expected_context_revision: int | None = None,
                             plan_hash: str | None = None,
                             authorization: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        approval_id = str(uuid.uuid4())
        idempotent = False
        with self.database.begin() as connection:
            version = connection.execute(text("""
                SELECT p.*,c.current_plan_version_id,c.context_revision
                FROM conversation_plan_versions p
                JOIN conversation_contexts c ON c.conversation_id=p.conversation_id
                WHERE p.id=:version AND p.conversation_id=:conversation
            """), {"version": plan_version_id, "conversation": conversation_id}).mappings().first()
            if version is None:
                raise KeyError(plan_version_id)
            if version["current_plan_version_id"] != plan_version_id:
                raise ValueError("PLAN_VERSION_NOT_CURRENT")
            if not version["plan_id"] or not version["plan_hash"]:
                raise ValueError("PLAN_VERSION_NOT_APPROVABLE")
            if expected_context_revision is not None and int(version["context_revision"]) != expected_context_revision:
                raise ValueError("PLAN_CONTEXT_STALE")
            if plan_hash is not None and plan_hash != version["plan_hash"]:
                raise ValueError("PLAN_HASH_MISMATCH")
            plan = connection.execute(text("SELECT plan_hash,status FROM plans WHERE id=:id"), {"id": version["plan_id"]}).mappings().first()
            if plan is None:
                raise KeyError(version["plan_id"])
            if plan["plan_hash"] != version["plan_hash"]:
                raise ValueError("PLAN_HASH_MISMATCH")
            if plan["status"] not in {"validated", "approved", "executing", "finished"}:
                raise ValueError("PLAN_NOT_APPROVABLE")
            existing = connection.execute(text("""
                SELECT id,plan_hash,context_revision,status
                FROM conversation_plan_approvals WHERE plan_version_id=:version
            """), {"version": plan_version_id}).mappings().first()
            if existing is not None:
                if (existing["status"] == "ACTIVE" and existing["plan_hash"] == version["plan_hash"]
                        and int(existing["context_revision"]) == int(version["context_revision"])):
                    approval_id = existing["id"]
                    idempotent = True
                else:
                    raise ValueError("PLAN_APPROVAL_IMMUTABLE")
            if not idempotent:
                connection.execute(text("""
                UPDATE conversation_plan_approvals SET status='STALE',superseded_at=:now
                WHERE conversation_id=:conversation AND status='ACTIVE'
                """), {"conversation": conversation_id, "now": now})
                connection.execute(text("""
                INSERT INTO conversation_plan_approvals(
                  id,conversation_id,plan_version_id,plan_id,plan_hash,context_revision,
                  status,authorization_json,approved_at
                ) VALUES(:id,:conversation,:version,:plan,:hash,:revision,'ACTIVE',:authorization,:now)
                """), {"id": approval_id, "conversation": conversation_id, "version": plan_version_id,
                        "plan": version["plan_id"], "hash": version["plan_hash"],
                        "revision": version["context_revision"], "authorization": canonical_json(authorization or {}), "now": now})
                connection.execute(text("""
                UPDATE conversation_plan_versions SET status='APPROVED',approved_at=:now
                WHERE id=:version AND status IN ('DRAFT','PROPOSED','APPROVED')
                """), {"version": plan_version_id, "now": now})
        return self.get_plan_approval(plan_version_id)

    def get_plan_approval(self, plan_version_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_plan_approvals WHERE plan_version_id=:version"), {"version": plan_version_id}).mappings().first()
        if row is None:
            raise KeyError("PLAN_APPROVAL_NOT_FOUND")
        result = dict(row)
        result["authorization"] = json.loads(result.pop("authorization_json") or "{}")
        return result

    def request_execution(self, conversation_id: str, plan_version_id: str, *,
                          expected_context_revision: int | None = None,
                          plan_hash: str | None = None,
                          status: str = "PENDING",
                          summary: dict[str, Any] | None = None,
                          affected_file_count: int = 0) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            context = connection.execute(text("SELECT context_revision,current_plan_version_id FROM conversation_contexts WHERE conversation_id=:conversation"), {"conversation": conversation_id}).first()
            if context is None:
                raise KeyError(conversation_id)
            if expected_context_revision is not None and int(context[0]) != expected_context_revision:
                raise ValueError("PLAN_CONTEXT_STALE")
            if context[1] != plan_version_id:
                raise ValueError("PLAN_VERSION_NOT_CURRENT")
            approval = connection.execute(text("""
                SELECT plan_id,plan_hash,context_revision,status
                FROM conversation_plan_approvals WHERE conversation_id=:conversation AND plan_version_id=:version
            """), {"conversation": conversation_id, "version": plan_version_id}).mappings().first()
            if approval is None or approval["status"] != "ACTIVE":
                raise ValueError("PLAN_APPROVAL_STALE")
            if plan_hash is not None and approval["plan_hash"] != plan_hash:
                raise ValueError("PLAN_HASH_MISMATCH")
            if int(approval["context_revision"]) != int(context[0]):
                raise ValueError("PLAN_CONTEXT_STALE")
            execution_plan_id = approval["plan_id"]
        return self.create_execution_round(conversation_id, plan_version_id, execution_plan_id,
                                           expected_context_revision=expected_context_revision,
                                           status=status, affected_file_count=affected_file_count,
                                           summary=summary, require_approval=True)

    def create_execution_round(
        self,
        conversation_id: str,
        plan_version_id: str,
        execution_plan_id: str,
        *,
        expected_context_revision: int | None = None,
        status: str = "PENDING",
        affected_file_count: int = 0,
        summary: dict[str, Any] | None = None,
        require_approval: bool = False,
    ) -> dict[str, Any]:
        round_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.begin() as connection:
            context = connection.execute(text("SELECT context_revision FROM conversation_contexts WHERE conversation_id=:id"), {"id": conversation_id}).first()
            if context is None:
                raise KeyError(conversation_id)
            current_revision = int(context[0])
            if expected_context_revision is not None and current_revision != expected_context_revision:
                raise ValueError("CONTEXT_REVISION_CONFLICT")
            version = connection.execute(text("SELECT plan_id FROM conversation_plan_versions WHERE id=:id AND conversation_id=:conversation"), {"id": plan_version_id, "conversation": conversation_id}).first()
            if version is None:
                raise KeyError(plan_version_id)
            if require_approval:
                approval = connection.execute(text("""
                    SELECT plan_id,status FROM conversation_plan_approvals
                    WHERE conversation_id=:conversation AND plan_version_id=:version AND status='ACTIVE'
                """), {"conversation": conversation_id, "version": plan_version_id}).first()
                if approval is None or approval[0] != execution_plan_id:
                    raise ValueError("PLAN_APPROVAL_STALE")
            if version[0] is not None and version[0] != execution_plan_id:
                raise ValueError("EXECUTION_PLAN_MISMATCH")
            if connection.execute(text("SELECT 1 FROM plans WHERE id=:id"), {"id": execution_plan_id}).first() is None:
                raise KeyError(execution_plan_id)
            number = int(connection.execute(text("SELECT COALESCE(MAX(round_number),0)+1 FROM conversation_execution_rounds WHERE conversation_id=:id"), {"id": conversation_id}).scalar_one())
            connection.execute(text("""
                INSERT INTO conversation_execution_rounds(
                  id,conversation_id,round_number,plan_version_id,execution_plan_id,status,
                  summary_json,affected_file_count,created_at
                ) VALUES(:id,:conversation,:number,:version,:plan,:status,:summary,:affected,:now)
            """), {"id": round_id, "conversation": conversation_id, "number": number, "version": plan_version_id,
                    "plan": execution_plan_id, "status": status, "summary": canonical_json(summary or {}),
                    "affected": affected_file_count, "now": now})
            pointer = connection.execute(text("""
                UPDATE conversation_contexts SET current_execution_round_id=:round,context_revision=context_revision+1,updated_at=:now
                WHERE conversation_id=:conversation AND context_revision=:revision
            """), {"round": round_id, "conversation": conversation_id, "revision": current_revision, "now": now})
            if pointer.rowcount != 1:
                raise ValueError("CONTEXT_REVISION_CONFLICT")
            task_id = connection.execute(text("SELECT task_id FROM plans WHERE id=:id"), {"id": execution_plan_id}).scalar_one()
            connection.execute(text("UPDATE tasks SET conversation_id=:conversation,conversation_plan_version_id=:version WHERE id=:task"), {"conversation": conversation_id, "version": plan_version_id, "task": task_id})
        return self.get_execution_round(round_id)

    def get_execution_round(self, round_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_execution_rounds WHERE id=:id"), {"id": round_id}).mappings().first()
        if row is None:
            raise KeyError(round_id)
        return _decode_json(dict(row), ("summary_json",))

    def list_execution_rounds(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM conversation_execution_rounds WHERE conversation_id=:id ORDER BY round_number"), {"id": conversation_id}).mappings().all()
        return [_decode_json(dict(row), ("summary_json",)) for row in rows]

    def update_execution_round(self, round_id: str, status: str, *, undo_status: str | None = None, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        assignments = ["status=:status"]
        params: dict[str, Any] = {"id": round_id, "status": status, "now": now}
        if status == "RUNNING":
            assignments.append("started_at=COALESCE(started_at,:now)")
        if status in {"COMPLETED", "FAILED", "CANCELLED", "RECOVERY_REQUIRED"}:
            assignments.append("completed_at=COALESCE(completed_at,:now)")
        if undo_status is not None:
            assignments.append("undo_status=:undo_status"); params["undo_status"] = undo_status
        if summary is not None:
            assignments.append("summary_json=:summary"); params["summary"] = canonical_json(summary)
        with self.database.begin() as connection:
            result = connection.execute(text(f"UPDATE conversation_execution_rounds SET {','.join(assignments)} WHERE id=:id"), params)
            if result.rowcount != 1:
                raise KeyError(round_id)
        return self.get_execution_round(round_id)

    def complete_execution_round(self, round_id: str, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        """Project a completed core execution into Conversation state without rewriting history."""
        now = utc_now()
        with self.database.begin() as connection:
            row = connection.execute(text("""
                SELECT er.conversation_id,er.plan_version_id,er.execution_plan_id,pv.change_summary_json
                FROM conversation_execution_rounds er
                JOIN conversation_plan_versions pv ON pv.id=er.plan_version_id
                WHERE er.id=:id
            """), {"id": round_id}).mappings().first()
            if row is None:
                raise KeyError(round_id)
            plan_status = connection.execute(text("SELECT status FROM plans WHERE id=:id"), {"id": row["execution_plan_id"]}).scalar()
            if plan_status != "finished":
                raise ValueError("EXECUTION_NOT_COMPLETED")
            changes = json.loads(row["change_summary_json"] or "{}")
            category_by_file = {
                str(item["file_id"]): item.get("target_category_id")
                for item in changes.get("moves", [])
                if isinstance(item, dict) and item.get("file_id")
            }
            operation_rows = connection.execute(text("""
                SELECT o.file_id,o.state,f.current_path,f.sha256,f.size_bytes,f.mtime_ns
                FROM operations o JOIN files f ON f.id=o.file_id
                WHERE o.plan_id=:plan AND o.state IN ('COMMITTED','SKIPPED')
            """), {"plan": row["execution_plan_id"]}).mappings().all()
            for operation in operation_rows:
                connection.execute(text("""
                    UPDATE conversation_files
                    SET current_known_path=:path,current_fingerprint=COALESCE(:fingerprint,current_fingerprint),
                        current_size_bytes=:size,current_mtime_ns=:mtime,last_verified_at=:now,state='ACTIVE',
                        current_category_id=COALESCE(:category,current_category_id)
                    WHERE conversation_id=:conversation AND file_id=:file
                """), {"conversation": row["conversation_id"], "file": operation["file_id"],
                        "path": operation["current_path"], "fingerprint": operation["sha256"],
                        "size": operation["size_bytes"], "mtime": operation["mtime_ns"],
                        "category": category_by_file.get(str(operation["file_id"])), "now": now})
            connection.execute(text("""
                UPDATE conversation_execution_rounds
                SET status='COMPLETED',completed_at=COALESCE(completed_at,:now),
                    summary_json=COALESCE(:summary,summary_json)
                WHERE id=:id
            """), {"id": round_id, "now": now,
                    "summary": canonical_json(summary) if summary is not None else None})
            connection.execute(text("""
                UPDATE conversation_plan_versions SET status='EXECUTED',executed_at=COALESCE(executed_at,:now)
                WHERE id=:version
            """), {"version": row["plan_version_id"], "now": now})
            connection.execute(text("""
                UPDATE conversation_contexts
                SET current_execution_round_id=:round,file_state_revision=file_state_revision+1,
                    context_revision=context_revision+1,updated_at=:now
                WHERE conversation_id=:conversation
            """), {"round": round_id, "conversation": row["conversation_id"], "now": now})
            connection.execute(text("""
                UPDATE conversations SET status='ACTIVE',updated_at=:now WHERE id=:conversation AND deleted_at IS NULL
            """), {"conversation": row["conversation_id"], "now": now})
        return self.get_execution_round(round_id)

    def attach_file(self, conversation_id: str, file_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.begin() as connection:
            if connection.execute(text("SELECT 1 FROM conversations WHERE id=:id AND deleted_at IS NULL"), {"id": conversation_id}).first() is None:
                raise KeyError(conversation_id)
            row = connection.execute(text("SELECT id,current_path,size_bytes,mtime_ns,sha256 FROM files WHERE id=:id"), {"id": file_id}).mappings().first()
            if row is None:
                raise KeyError(file_id)
            fingerprint, size, mtime = self._observe(row)
            connection.execute(text("""
                INSERT INTO conversation_files(
                  id,conversation_id,file_id,first_seen_path,current_known_path,first_seen_fingerprint,current_fingerprint,
                  first_seen_size_bytes,current_size_bytes,first_seen_mtime_ns,current_mtime_ns,added_at,last_verified_at,state
                ) VALUES(:id,:conversation,:file,:path,:path,:fingerprint,:fingerprint,:size,:size,:mtime,:mtime,:now,:now,'ACTIVE')
                ON CONFLICT(conversation_id,file_id) DO UPDATE SET
                  current_known_path=excluded.current_known_path,current_fingerprint=excluded.current_fingerprint,
                  current_size_bytes=excluded.current_size_bytes,current_mtime_ns=excluded.current_mtime_ns,
                  last_verified_at=excluded.last_verified_at,state='ACTIVE',removed_from_scope_at=NULL
            """), {"id": str(uuid.uuid4()), "conversation": conversation_id, "file": file_id,
                    "path": row["current_path"], "fingerprint": fingerprint, "size": size or row["size_bytes"],
                    "mtime": mtime or row["mtime_ns"], "now": now})
        return self.get_conversation_file(conversation_id, file_id)

    @staticmethod
    def _observe(row) -> tuple[str | None, int | None, int | None]:
        path = Path(str(row["current_path"]))
        try:
            identity = read_identity(path)
            return identity.sha256, identity.size_bytes, identity.mtime_ns
        except OSError:
            if row.get("sha256"):
                return row["sha256"], row.get("size_bytes"), row.get("mtime_ns")
            return None, row.get("size_bytes"), row.get("mtime_ns")

    def get_conversation_file(self, conversation_id: str, file_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT cf.*,f.current_path AS core_current_path,f.size_bytes AS core_size_bytes,
                       f.mtime_ns AS core_mtime_ns,f.sha256 AS core_sha256
                FROM conversation_files cf JOIN files f ON f.id=cf.file_id
                WHERE cf.conversation_id=:conversation AND cf.file_id=:file
            """), {"conversation": conversation_id, "file": file_id}).mappings().first()
        if row is None:
            raise KeyError(file_id)
        return dict(row)

    def list_conversation_files(self, conversation_id: str, *, include_removed: bool = False) -> list[dict[str, Any]]:
        clause = "" if include_removed else " AND cf.removed_from_scope_at IS NULL"
        with self.database.engine.connect() as connection:
            rows = connection.execute(text(f"""
                SELECT cf.*,f.current_path AS core_current_path,f.size_bytes AS core_size_bytes,
                       f.mtime_ns AS core_mtime_ns,f.sha256 AS core_sha256
                FROM conversation_files cf JOIN files f ON f.id=cf.file_id
                WHERE cf.conversation_id=:conversation{clause} ORDER BY cf.added_at,cf.id
            """), {"conversation": conversation_id}).mappings().all()
        return [dict(row) for row in rows]

    def verify_file(self, conversation_id: str, file_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.begin() as connection:
            row = connection.execute(text("""
                SELECT cf.current_fingerprint,cf.file_id,f.current_path,f.size_bytes,f.mtime_ns,f.sha256
                FROM conversation_files cf JOIN files f ON f.id=cf.file_id
                WHERE cf.conversation_id=:conversation AND cf.file_id=:file
            """), {"conversation": conversation_id, "file": file_id}).mappings().first()
            if row is None:
                raise KeyError(file_id)
            fingerprint, size, mtime = self._observe(row)
            state = "MISSING" if not Path(str(row["current_path"])).is_file() else ("FILE_CHANGED" if row["current_fingerprint"] and fingerprint != row["current_fingerprint"] else "ACTIVE")
            accepted_fingerprint = row["current_fingerprint"] if state == "FILE_CHANGED" else fingerprint
            connection.execute(text("""
                UPDATE conversation_files SET current_known_path=:path,current_fingerprint=:fingerprint,
                  current_size_bytes=:size,current_mtime_ns=:mtime,last_verified_at=:now,state=:state
                WHERE conversation_id=:conversation AND file_id=:file
            """), {"conversation": conversation_id, "file": file_id, "path": row["current_path"],
                    "fingerprint": accepted_fingerprint, "size": size or row["size_bytes"], "mtime": mtime or row["mtime_ns"],
                    "now": now, "state": state})
        return self.get_conversation_file(conversation_id, file_id)

    def link_task(self, conversation_id: str, task_id: str, plan_version_id: str | None = None) -> dict[str, Any]:
        with self.database.begin() as connection:
            if connection.execute(text("SELECT 1 FROM conversations WHERE id=:id"), {"id": conversation_id}).first() is None:
                raise KeyError(conversation_id)
            task = connection.execute(text("SELECT id FROM tasks WHERE id=:id"), {"id": task_id}).first()
            if task is None:
                raise KeyError(task_id)
            if plan_version_id:
                row = connection.execute(text("SELECT conversation_id,plan_id FROM conversation_plan_versions WHERE id=:id"), {"id": plan_version_id}).first()
                if row is None or row[0] != conversation_id:
                    raise ValueError("PLAN_VERSION_CONVERSATION_MISMATCH")
                if row[1] and connection.execute(text("SELECT task_id FROM plans WHERE id=:id"), {"id": row[1]}).scalar() != task_id:
                    raise ValueError("PLAN_VERSION_TASK_MISMATCH")
            connection.execute(text("UPDATE tasks SET conversation_id=:conversation,conversation_plan_version_id=:version WHERE id=:task"), {"conversation": conversation_id, "version": plan_version_id, "task": task_id})
            linked = connection.execute(text("SELECT id,name,status,phase,revision,conversation_plan_version_id FROM tasks WHERE id=:id"), {"id": task_id}).mappings().first()
        return dict(linked)
