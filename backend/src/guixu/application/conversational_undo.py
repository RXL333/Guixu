from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

from guixu.application.plan_compiler import canonical_hash
from guixu.application.undo import UndoCompiler
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import canonical_json
from guixu.infrastructure.filesystem.executor import FileOperationExecutor
from guixu.infrastructure.filesystem.identity import sha256_file


class UndoError(ValueError):
    def __init__(self, code: str, details: Any = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


class UndoTargetResolver:
    """Resolve only persisted Conversation rounds; never accept model supplied paths."""

    _number_words = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

    def __init__(self, database: Database) -> None:
        self.database = database

    def resolve(self, conversation_id: str, *, user_message: str = "", execution_round_id: str | None = None,
                referenced_file_ids: list[str] | None = None) -> dict[str, Any]:
        referenced = list(dict.fromkeys(referenced_file_ids or []))
        with self.database.engine.connect() as connection:
            if execution_round_id:
                row = connection.execute(text("""
                    SELECT * FROM conversation_execution_rounds
                    WHERE id=:round AND conversation_id=:conversation AND round_kind='FORWARD'
                """), {"round": execution_round_id, "conversation": conversation_id}).mappings().first()
                if row is None:
                    raise UndoError("UNDO_TARGET_NOT_FOUND")
                return self._result(row, referenced, "EXPLICIT_EXECUTION", 1.0)

            if referenced:
                names = ",".join(f":f{i}" for i in range(len(referenced)))
                params = {"conversation": conversation_id, **{f"f{i}": value for i, value in enumerate(referenced)}}
                rows = connection.execute(text(f"""
                    SELECT DISTINCT er.* FROM conversation_execution_rounds er
                    JOIN operations o ON o.plan_id=er.execution_plan_id
                    WHERE er.conversation_id=:conversation AND er.round_kind='FORWARD'
                      AND er.status='COMPLETED' AND o.state='COMMITTED'
                      AND o.file_id IN ({names}) ORDER BY er.round_number DESC
                """), params).mappings().all()
                covering = []
                for candidate in rows:
                    found = connection.execute(text(f"""
                        SELECT COUNT(DISTINCT file_id) FROM operations
                        WHERE plan_id=:plan AND state='COMMITTED' AND file_id IN ({names})
                    """), {"plan": candidate["execution_plan_id"], **{f"f{i}": value for i, value in enumerate(referenced)}}).scalar_one()
                    if int(found) == len(referenced):
                        covering.append(candidate)
                if len(covering) != 1:
                    raise UndoError("UNDO_REFERENCE_AMBIGUOUS", {"candidate_round_ids": [row["id"] for row in covering or rows]})
                return self._result(covering[0], referenced, "REFERENCED_FILES", 1.0)

            explicit_number = self._round_number(user_message)
            if explicit_number is not None:
                row = connection.execute(text("""
                    SELECT * FROM conversation_execution_rounds
                    WHERE conversation_id=:conversation AND round_number=:number AND round_kind='FORWARD'
                """), {"conversation": conversation_id, "number": explicit_number}).mappings().first()
                if row is None:
                    raise UndoError("UNDO_TARGET_NOT_FOUND")
                return self._result(row, [], "EXPLICIT_ORDINAL", 1.0)

            row = connection.execute(text("""
                SELECT er.* FROM conversation_execution_rounds er
                WHERE er.conversation_id=:conversation AND er.round_kind='FORWARD'
                  AND er.status='COMPLETED' AND er.undo_state!='FULLY_UNDONE'
                  AND EXISTS(SELECT 1 FROM operations o WHERE o.plan_id=er.execution_plan_id AND o.state='COMMITTED')
                ORDER BY er.round_number DESC LIMIT 1
            """), {"conversation": conversation_id}).mappings().first()
        if row is None:
            raise UndoError("UNDO_NOT_APPLICABLE")
        return self._result(row, [], "LATEST_REVERSIBLE", 1.0)

    @classmethod
    def _round_number(cls, message: str) -> int | None:
        match = re.search(r"第\s*(\d+)\s*次", message)
        if match:
            return int(match.group(1))
        match = re.search(r"第\s*([一二三四五六七八九十])\s*次", message)
        return cls._number_words.get(match.group(1)) if match else None

    @staticmethod
    def _result(row: Any, referenced: list[str], source: str, confidence: float) -> dict[str, Any]:
        return {"target_type": "EXECUTION_ROUND", "execution_round_id": row["id"],
                "round_number": row["round_number"], "referenced_file_ids": referenced,
                "resolution_source": source, "confidence": confidence, "requires_clarification": False}


class ExecutionDependencyAnalyzer:
    def __init__(self, database: Database) -> None:
        self.database = database

    def analyze(self, conversation_id: str, target_round_id: str, file_ids: list[str]) -> dict[str, Any]:
        if not file_ids:
            return {"status": "NONE", "dependent_file_ids": [], "round_ids": []}
        names = ",".join(f":f{i}" for i in range(len(file_ids)))
        params = {"conversation": conversation_id, "target": target_round_id,
                  **{f"f{i}": value for i, value in enumerate(file_ids)}}
        with self.database.engine.connect() as connection:
            rows = connection.execute(text(f"""
                SELECT DISTINCT o.file_id, later.id AS round_id
                FROM conversation_execution_rounds target
                JOIN conversation_execution_rounds later
                  ON later.conversation_id=target.conversation_id AND later.round_number>target.round_number
                JOIN operations o ON o.plan_id=later.execution_plan_id
                WHERE target.id=:target AND target.conversation_id=:conversation
                  AND later.round_kind='FORWARD' AND later.status='COMPLETED'
                  AND o.state='COMMITTED' AND o.file_id IN ({names})
            """), params).mappings().all()
        dependent = sorted({str(row["file_id"]) for row in rows})
        return {"status": "DEPENDENT" if dependent else "SAFE", "dependent_file_ids": dependent,
                "round_ids": sorted({str(row["round_id"]) for row in rows})}


class ConversationalUndoService:
    def __init__(self, database: Database, journal: SqliteOperationJournal) -> None:
        self.database = database
        self.journal = journal
        self.targets = UndoTargetResolver(database)
        self.dependencies = ExecutionDependencyAnalyzer(database)

    @staticmethod
    def is_undo_intent(message: str) -> bool:
        normalized = message.strip().lower()
        return any(term in normalized for term in ("撤销", "恢复回去", "放回去", "恢复原位"))

    def reversible_executions(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT er.*, COUNT(CASE WHEN o.state='COMMITTED' THEN 1 END) AS actual_count
                FROM conversation_execution_rounds er
                LEFT JOIN operations o ON o.plan_id=er.execution_plan_id
                WHERE er.conversation_id=:conversation AND er.round_kind='FORWARD'
                GROUP BY er.id ORDER BY er.round_number DESC
            """), {"conversation": conversation_id}).mappings().all()
        result = []
        for row in rows:
            actual = int(row["actual_count"] or 0)
            result.append({**dict(row), "actual_operation_count": actual,
                           "currently_reversible": row["status"] == "COMPLETED" and actual > 0 and row["undo_state"] != "FULLY_UNDONE"})
        return result

    def request(self, conversation_id: str, *, user_message: str = "", execution_round_id: str | None = None,
                referenced_file_ids: list[str] | None = None) -> dict[str, Any]:
        if user_message and not self.is_undo_intent(user_message):
            raise UndoError("UNDO_TARGET_NOT_FOUND")
        target = self.targets.resolve(conversation_id, user_message=user_message,
                                      execution_round_id=execution_round_id,
                                      referenced_file_ids=referenced_file_ids)
        if user_message and any(term in user_message for term in ("可以撤销吗", "能撤销吗", "可不可以撤销", "是否能撤销")):
            return {"target": target, "undo_plan": None,
                    "query": {"reversible": True, "message": f"第 {target['round_number']} 次整理可以生成撤销预览；目前不会修改文件。"}}
        return {"target": target, "undo_plan": self.build_preview(
            conversation_id, target["execution_round_id"], target["referenced_file_ids"])}

    def build_preview(self, conversation_id: str, target_round_id: str,
                      requested_file_ids: list[str] | None = None) -> dict[str, Any]:
        requested = list(dict.fromkeys(requested_file_ids or []))
        now = utc_now()
        with self.database.engine.connect() as connection:
            target = connection.execute(text("""
                SELECT er.*,p.task_id,p.operation_mode FROM conversation_execution_rounds er
                JOIN plans p ON p.id=er.execution_plan_id
                WHERE er.id=:round AND er.conversation_id=:conversation AND er.round_kind='FORWARD'
            """), {"round": target_round_id, "conversation": conversation_id}).mappings().first()
            if target is None:
                raise UndoError("UNDO_TARGET_NOT_FOUND")
            if target["status"] != "COMPLETED":
                raise UndoError("UNDO_NOT_REVERSIBLE")
            revision = int(connection.execute(text(
                "SELECT file_state_revision FROM conversation_contexts WHERE conversation_id=:id"
            ), {"id": conversation_id}).scalar_one())
            scopes = [Path(row[0]) for row in connection.execute(text("""
                SELECT source_root FROM conversation_scopes WHERE conversation_id=:id AND revoked_at IS NULL
            """), {"id": conversation_id})]
            operations = connection.execute(text("""
                SELECT o.*,cf.current_known_path,cf.current_fingerprint,cf.state AS conversation_file_state
                FROM operations o
                LEFT JOIN conversation_files cf ON cf.conversation_id=:conversation AND cf.file_id=o.file_id
                WHERE o.plan_id=:plan AND o.state='COMMITTED' AND o.action IN ('move','copy')
                ORDER BY o.ordinal
            """), {"conversation": conversation_id, "plan": target["execution_plan_id"]}).mappings().all()
        if requested:
            operation_by_file = {str(row["file_id"]): row for row in operations}
            unknown = [file_id for file_id in requested if file_id not in operation_by_file]
            if unknown:
                raise UndoError("UNDO_REFERENCE_AMBIGUOUS", {"file_ids": unknown})
            operations = [operation_by_file[file_id] for file_id in requested]
        if not operations:
            raise UndoError("UNDO_NOT_APPLICABLE")

        file_ids = [str(row["file_id"]) for row in operations]
        dependency = self.dependencies.analyze(conversation_id, target_round_id, file_ids)
        dependent = set(dependency["dependent_file_ids"])
        item_specs: list[dict[str, Any]] = []
        ready_ids: set[str] = set()
        for row in operations:
            current_source = Path(str(row["target_path"] or ""))
            restore_target = Path(str(row["source_path"]))
            operation_kind = "COPY" if row["action"] == "copy" else "MOVE"
            expected = str(row["expected_sha256"] or "")
            status, reason = "READY", None
            current_known = Path(str(row["current_known_path"])) if row["current_known_path"] else current_source
            if str(row["file_id"]) in dependent:
                status, reason = "BLOCKED_DEPENDENCY", "UNDO_DEPENDENCY_CONFLICT"
            elif not any(_inside(current_source, root) and _inside(restore_target, root) for root in scopes):
                status, reason = "BLOCKED_SCOPE", "UNDO_SCOPE_VIOLATION"
            elif operation_kind == "MOVE" and restore_target.exists() and not current_source.exists():
                try:
                    status = "ALREADY_REVERSED" if sha256_file(restore_target) == expected else "BLOCKED_TARGET_CONFLICT"
                    reason = None if status == "ALREADY_REVERSED" else "UNDO_TARGET_CONFLICT"
                except OSError:
                    status, reason = "BLOCKED_TARGET_CONFLICT", "UNDO_TARGET_CONFLICT"
            elif current_known != current_source and current_known.exists():
                status, reason = "BLOCKED_EXTERNAL_MOVE", "FILE_MOVED_EXTERNALLY"
            elif not current_source.exists():
                status, reason = "BLOCKED_MISSING", "UNDO_SOURCE_MISSING"
            elif operation_kind == "MOVE" and restore_target.exists():
                status, reason = "BLOCKED_TARGET_CONFLICT", "UNDO_TARGET_CONFLICT"
            else:
                try:
                    if sha256_file(current_source) != expected:
                        status, reason = "BLOCKED_MODIFIED", "UNDO_SOURCE_MODIFIED"
                except OSError:
                    status, reason = "BLOCKED_MISSING", "UNDO_SOURCE_MISSING"
            if status == "READY":
                ready_ids.add(str(row["id"]))
            item_specs.append({"file_id": str(row["file_id"]), "original_operation_id": str(row["id"]),
                               "operation_kind": operation_kind,
                               "current_source": str(current_source), "restore_target": str(restore_target),
                               "expected_fingerprint": expected, "status": status, "block_reason": reason})

        blocked = [item for item in item_specs if item["status"].startswith("BLOCKED_")]
        undo_plan = None
        if ready_ids and not blocked:
            forward = self.journal.load_plan(str(target["execution_plan_id"]))
            with self.database.engine.connect() as connection:
                version = int(connection.execute(text("SELECT COALESCE(MAX(version),0)+1 FROM plans WHERE task_id=:task"), {"task": forward.task_id}).scalar_one())
                task_revision = int(connection.execute(text("SELECT revision FROM tasks WHERE id=:task"), {"task": forward.task_id}).scalar_one())
            undo_plan = UndoCompiler().compile(forward, ready_ids, version)
            self.journal.persist_plan(undo_plan, task_revision)
            undo_by_original = {item.reverses_operation_id: item.operation_id for item in undo_plan.operations}
            for item in item_specs:
                item["undo_operation_id"] = undo_by_original.get(item["original_operation_id"])
        else:
            for item in item_specs:
                item["undo_operation_id"] = None

        plan_id = str(uuid.uuid4())
        preview_hash = undo_plan.plan_hash if undo_plan else canonical_hash({
            "conversation_id": conversation_id, "target_execution_round_id": target_round_id,
            "basis_file_state_revision": revision, "items": item_specs,
        })
        already = sum(item["status"] == "ALREADY_REVERSED" for item in item_specs)
        status = "WAITING_FOR_APPROVAL" if undo_plan and not blocked else "BLOCKED"
        summary = {"target_round_number": target["round_number"], "total": len(item_specs),
                   "ready": len(ready_ids), "blocked": len(blocked), "already_reversed": already,
                   "partial": bool(requested), "dependency": dependency,
                   "build_time_ms": 0, "validation_time_ms": 0}
        with self.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO conversation_undo_plans(
                  id,conversation_id,target_execution_round_id,core_plan_id,status,basis_file_state_revision,
                  plan_hash,requested_file_ids_json,summary_json,created_at
                ) VALUES(:id,:conversation,:target,:core,:status,:revision,:hash,:requested,:summary,:now)
            """), {"id": plan_id, "conversation": conversation_id, "target": target_round_id,
                    "core": undo_plan.plan_id if undo_plan else None, "status": status, "revision": revision,
                    "hash": preview_hash, "requested": canonical_json(requested),
                    "summary": canonical_json(summary), "now": now})
            for ordinal, item in enumerate(item_specs):
                connection.execute(text("""
                    INSERT INTO conversation_undo_plan_items(
                      id,undo_plan_id,file_id,original_operation_id,undo_operation_id,operation_kind,ordinal,current_source,
                      restore_target,expected_fingerprint,status,block_reason,created_at
                    ) VALUES(:id,:plan,:file,:original,:undo,:kind,:ordinal,:source,:target,:fingerprint,:status,:reason,:now)
                """), {"id": str(uuid.uuid4()), "plan": plan_id, "file": item["file_id"],
                        "original": item["original_operation_id"], "undo": item["undo_operation_id"],
                        "kind": item["operation_kind"],
                        "ordinal": ordinal, "source": item["current_source"], "target": item["restore_target"],
                        "fingerprint": item["expected_fingerprint"], "status": item["status"],
                        "reason": item["block_reason"], "now": now})
            connection.execute(text("""
                UPDATE conversation_execution_rounds
                SET undo_state=:state,reversible_file_count=:count,undo_status=:legacy
                WHERE id=:round
            """), {"round": target_round_id, "state": "UNDO_BLOCKED" if blocked else "NOT_UNDONE",
                    "count": len(item_specs), "legacy": "BLOCKED" if blocked else "PREPARED"})
        return self.get(plan_id)

    def get(self, undo_plan_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_undo_plans WHERE id=:id"), {"id": undo_plan_id}).mappings().first()
            if row is None:
                raise KeyError(undo_plan_id)
            items = connection.execute(text("SELECT * FROM conversation_undo_plan_items WHERE undo_plan_id=:id ORDER BY ordinal"), {"id": undo_plan_id}).mappings().all()
        result = dict(row)
        for field in ("requested_file_ids_json", "summary_json", "approval_json"):
            result[field.removesuffix("_json")] = json.loads(result.pop(field) or ("[]" if field.startswith("requested") else "{}"))
        result["items"] = [dict(item) for item in items]
        return result

    def list(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            ids = [str(row[0]) for row in connection.execute(text(
                "SELECT id FROM conversation_undo_plans WHERE conversation_id=:id ORDER BY created_at DESC"
            ), {"id": conversation_id})]
        return [self.get(value) for value in ids]

    def approve(self, conversation_id: str, undo_plan_id: str, plan_hash: str,
                authorization: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = self.get(undo_plan_id)
        if plan["conversation_id"] != conversation_id:
            raise UndoError("UNDO_TARGET_NOT_FOUND")
        if plan["plan_hash"] != plan_hash:
            raise UndoError("UNDO_PLAN_HASH_MISMATCH")
        if plan["status"] == "APPROVED":
            return plan
        if plan["status"] != "WAITING_FOR_APPROVAL" or not plan["core_plan_id"]:
            raise UndoError("UNDO_NOT_REVERSIBLE")
        self._assert_current(plan)
        with self.database.engine.connect() as connection:
            task_id = connection.execute(text("SELECT task_id FROM plans WHERE id=:id"), {"id": plan["core_plan_id"]}).scalar_one()
            revision = int(connection.execute(text("SELECT revision FROM tasks WHERE id=:id"), {"id": task_id}).scalar_one())
        self.journal.approve(plan["core_plan_id"], plan_hash, revision, authorization_kind="interactive")
        with self.database.begin() as connection:
            connection.execute(text("""
                UPDATE conversation_undo_plans SET status='APPROVED',approval_json=:approval,approved_at=:now
                WHERE id=:id AND status='WAITING_FOR_APPROVAL'
            """), {"id": undo_plan_id, "approval": canonical_json(authorization or {}), "now": utc_now()})
        return self.get(undo_plan_id)

    def execute(self, conversation_id: str, undo_plan_id: str, plan_hash: str) -> dict[str, Any]:
        plan = self.get(undo_plan_id)
        if plan["conversation_id"] != conversation_id:
            raise UndoError("UNDO_TARGET_NOT_FOUND")
        if plan["plan_hash"] != plan_hash:
            raise UndoError("UNDO_PLAN_HASH_MISMATCH")
        if plan["status"] in {"COMPLETED", "PARTIALLY_COMPLETED"} and plan["execution_round_id"]:
            return plan
        if plan["status"] not in {"APPROVED", "EXECUTING", "RECOVERY_REQUIRED"}:
            raise UndoError("UNDO_APPROVAL_REQUIRED")
        self._assert_no_competing_turn(conversation_id)
        self._assert_current(plan, allow_completed=True)
        round_id = plan["execution_round_id"] or self._create_undo_round(plan)
        with self.database.begin() as connection:
            connection.execute(text("UPDATE conversation_undo_plans SET status='EXECUTING',execution_round_id=:round WHERE id=:id"), {"round": round_id, "id": undo_plan_id})
        core = self.journal.load_plan(plan["core_plan_id"])
        FileOperationExecutor(self.journal).execute(core, plan_hash)
        results = self.journal.operation_results(core.plan_id)
        by_operation = {str(row["operation_id"]): str(row["state"]) for row in results}
        completed = 0
        failed = 0
        with self.database.begin() as connection:
            items = connection.execute(text("SELECT id,undo_operation_id,status FROM conversation_undo_plan_items WHERE undo_plan_id=:id"), {"id": undo_plan_id}).mappings().all()
            for item in items:
                if item["status"] == "ALREADY_REVERSED":
                    completed += 1
                    continue
                state = by_operation.get(str(item["undo_operation_id"]))
                next_status = "COMPLETED" if state == "UNDONE" else "FAILED"
                completed += next_status == "COMPLETED"
                failed += next_status == "FAILED"
                connection.execute(text("UPDATE conversation_undo_plan_items SET status=:status,block_reason=:reason WHERE id=:id"),
                                   {"id": item["id"], "status": next_status,
                                    "reason": None if next_status == "COMPLETED" else "UNDO_EXECUTION_INTERRUPTED"})
            final_status = "COMPLETED" if failed == 0 else "PARTIALLY_COMPLETED"
            now = utc_now()
            connection.execute(text("UPDATE conversation_undo_plans SET status=:status,completed_at=:now WHERE id=:id"),
                               {"id": undo_plan_id, "status": final_status, "now": now})
            connection.execute(text("""
                UPDATE conversation_execution_rounds SET status=:status,completed_at=:now,
                  affected_file_count=:affected,summary_json=:summary WHERE id=:round
            """), {"round": round_id, "status": "COMPLETED" if failed == 0 else "RECOVERY_REQUIRED",
                    "affected": completed, "summary": canonical_json({"description": f"已恢复 {completed} 个文件。", "failed": failed}), "now": now})
            file_rows = connection.execute(text("""
                SELECT DISTINCT i.file_id,f.current_path,f.sha256,f.size_bytes,f.mtime_ns
                FROM conversation_undo_plan_items i JOIN files f ON f.id=i.file_id
                WHERE i.undo_plan_id=:id AND i.status IN ('COMPLETED','ALREADY_REVERSED')
            """), {"id": undo_plan_id}).mappings().all()
            for file_row in file_rows:
                connection.execute(text("""
                    UPDATE conversation_files SET current_known_path=:path,current_fingerprint=:fingerprint,
                      current_size_bytes=:size,current_mtime_ns=:mtime,state='ACTIVE',last_verified_at=:now
                    WHERE conversation_id=:conversation AND file_id=:file
                """), {"conversation": conversation_id, "file": file_row["file_id"], "path": file_row["current_path"],
                        "fingerprint": file_row["sha256"], "size": file_row["size_bytes"], "mtime": file_row["mtime_ns"], "now": now})
            target = connection.execute(text("SELECT execution_plan_id FROM conversation_execution_rounds WHERE id=:id"), {"id": plan["target_execution_round_id"]}).first()
            total = int(connection.execute(text("SELECT COUNT(*) FROM operations WHERE plan_id=:plan AND state='COMMITTED'"), {"plan": target[0]}).scalar_one()) if target else 0
            undone = int(connection.execute(text("""
                SELECT COUNT(DISTINCT i.original_operation_id) FROM conversation_undo_plan_items i
                JOIN conversation_undo_plans p ON p.id=i.undo_plan_id
                WHERE p.target_execution_round_id=:target AND i.status IN ('COMPLETED','ALREADY_REVERSED')
            """), {"target": plan["target_execution_round_id"]}).scalar_one())
            undo_state = "FULLY_UNDONE" if total > 0 and undone >= total else "PARTIALLY_UNDONE"
            connection.execute(text("""
                UPDATE conversation_execution_rounds SET undo_state=:state,undone_file_count=:undone,
                  reversible_file_count=:total,undo_status=:legacy WHERE id=:id
            """), {"id": plan["target_execution_round_id"], "state": undo_state, "undone": undone,
                    "total": total, "legacy": "EXECUTED"})
            connection.execute(text("""
                UPDATE conversation_contexts SET current_execution_round_id=:round,
                  file_state_revision=file_state_revision+1,context_revision=context_revision+1,updated_at=:now
                WHERE conversation_id=:conversation
            """), {"round": round_id, "conversation": conversation_id, "now": now})
            current_file_revision = int(connection.execute(text("SELECT file_state_revision FROM conversation_contexts WHERE conversation_id=:id"), {"id": conversation_id}).scalar_one())
            connection.execute(text("""
                UPDATE conversation_plan_approvals SET status='STALE',superseded_at=:now
                WHERE conversation_id=:conversation AND status='ACTIVE' AND plan_version_id IN (
                  SELECT id FROM conversation_plan_versions WHERE basis_file_state_revision<:revision
                )
            """), {"conversation": conversation_id, "revision": current_file_revision, "now": now})
        return self.get(undo_plan_id)

    def cancel(self, conversation_id: str, undo_plan_id: str) -> dict[str, Any]:
        plan = self.get(undo_plan_id)
        if plan["conversation_id"] != conversation_id:
            raise UndoError("UNDO_TARGET_NOT_FOUND")
        if plan["status"] not in {"WAITING_FOR_APPROVAL", "BLOCKED"}:
            raise UndoError("UNDO_PLAN_STALE")
        with self.database.begin() as connection:
            connection.execute(text("UPDATE conversation_undo_plans SET status='CANCELLED',cancelled_at=:now WHERE id=:id"), {"id": undo_plan_id, "now": utc_now()})
        return self.get(undo_plan_id)

    def _assert_current(self, plan: dict[str, Any], *, allow_completed: bool = False) -> None:
        with self.database.engine.connect() as connection:
            revision = int(connection.execute(text("SELECT file_state_revision FROM conversation_contexts WHERE conversation_id=:id"), {"id": plan["conversation_id"]}).scalar_one())
        if revision != int(plan["basis_file_state_revision"]):
            with self.database.begin() as connection:
                connection.execute(text("UPDATE conversation_undo_plans SET status='STALE' WHERE id=:id AND status NOT IN ('COMPLETED','PARTIALLY_COMPLETED')"), {"id": plan["id"]})
            raise UndoError("UNDO_PLAN_STALE", {"expected": plan["basis_file_state_revision"], "actual": revision})
        for item in plan["items"]:
            if allow_completed and item.get("undo_operation_id"):
                try:
                    if self.journal.state(item["undo_operation_id"]) == "UNDONE":
                        continue
                except KeyError:
                    pass
            if item["status"] not in ({"READY", "ALREADY_REVERSED", "COMPLETED"} if allow_completed else {"READY", "ALREADY_REVERSED"}):
                raise UndoError(item["block_reason"] or "UNDO_NOT_REVERSIBLE")
            if item["status"] in {"ALREADY_REVERSED", "COMPLETED"}:
                continue
            source, target = Path(item["current_source"]), Path(item["restore_target"])
            if not source.exists():
                raise UndoError("UNDO_SOURCE_MISSING")
            if item["operation_kind"] == "MOVE" and target.exists():
                raise UndoError("UNDO_TARGET_CONFLICT")
            if sha256_file(source) != item["expected_fingerprint"]:
                raise UndoError("UNDO_SOURCE_MODIFIED")

    def _create_undo_round(self, plan: dict[str, Any]) -> str:
        round_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.begin() as connection:
            target = connection.execute(text("SELECT plan_version_id FROM conversation_execution_rounds WHERE id=:id"), {"id": plan["target_execution_round_id"]}).first()
            if target is None:
                raise UndoError("UNDO_TARGET_NOT_FOUND")
            number = int(connection.execute(text("SELECT COALESCE(MAX(round_number),0)+1 FROM conversation_execution_rounds WHERE conversation_id=:id"), {"id": plan["conversation_id"]}).scalar_one())
            connection.execute(text("""
                INSERT INTO conversation_execution_rounds(
                  id,conversation_id,round_number,plan_version_id,execution_plan_id,status,undo_status,
                  summary_json,affected_file_count,round_kind,target_execution_round_id,created_at,started_at
                ) VALUES(:id,:conversation,:number,:version,:core,'RUNNING','NOT_REQUESTED',:summary,0,'UNDO',:target,:now,:now)
            """), {"id": round_id, "conversation": plan["conversation_id"], "number": number,
                    "version": target[0], "core": plan["core_plan_id"], "target": plan["target_execution_round_id"],
                    "summary": canonical_json({"description": "正在撤销文件操作。"}), "now": now})
            connection.execute(text("UPDATE conversation_undo_plans SET execution_round_id=:round WHERE id=:id"), {"round": round_id, "id": plan["id"]})
        return round_id

    def _assert_no_competing_turn(self, conversation_id: str) -> None:
        with self.database.engine.connect() as connection:
            count = int(connection.execute(text("""
                SELECT COUNT(*) FROM conversation_agent_turns
                WHERE conversation_id=:id AND status IN ('QUEUED','RUNNING')
            """), {"id": conversation_id}).scalar_one())
        if count:
            raise UndoError("UNDO_RECOVERY_REQUIRED", {"active_agent_turns": count})
