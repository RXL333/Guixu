"""Restart-safe Conversation recovery and workspace reconciliation.

This module is deliberately conservative: it only reconciles durable state with
the currently authorized filesystem and creates retry records. It never calls a
model, approves a plan, or replays a filesystem operation automatically.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

from guixu.application.semantic_cache import EvidenceCacheService
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.operation_journal import FINAL_STATES, SqliteOperationJournal
from guixu.infrastructure.db.repository import canonical_json
from guixu.infrastructure.filesystem.identity import read_identity


class WorkspaceReconciliationService:
    """Compare last-known ConversationFile projections with an authorized scope."""

    def __init__(self, database: Database, repository: ConversationRepository,
                 evidence_cache: EvidenceCacheService | None = None) -> None:
        self.database = database
        self.repository = repository
        self.evidence_cache = evidence_cache

    def reconcile(self, conversation_id: str, *, trigger: str = "OPEN", detect_new: bool = True) -> dict[str, Any]:
        conversation = self.repository.get(conversation_id)
        context = self.repository.get_context(conversation_id)
        with self.database.engine.connect() as connection:
            scopes = list(connection.execute(text("""
                SELECT * FROM conversation_scopes
                WHERE conversation_id=:conversation AND revoked_at IS NULL ORDER BY created_at
            """), {"conversation": conversation_id}).mappings())
            known = list(connection.execute(text("""
                SELECT cf.*,f.task_id,f.current_path AS core_current_path,f.path_key AS core_path_key,
                       f.sha256 AS core_sha256,f.size_bytes AS core_size_bytes,f.mtime_ns AS core_mtime_ns
                FROM conversation_files cf JOIN files f ON f.id=cf.file_id
                WHERE cf.conversation_id=:conversation AND cf.removed_from_scope_at IS NULL
                ORDER BY cf.added_at,cf.id
            """), {"conversation": conversation_id}).mappings())

        # Only an entirely unindexed conversation lacks a baseline. A partially
        # indexed task must still detect files added outside the application.
        if not known and not context.get("current_plan_version_id") and not context.get("current_execution_round_id"):
            detect_new = False

        roots = [Path(str(item["source_root"])) for item in scopes]
        available_roots = [root for root in roots if root.is_dir()]
        scope_status = "AVAILABLE" if roots and len(available_roots) == len(roots) else "SCOPE_UNAVAILABLE"
        events: list[dict[str, Any]] = []
        changed_file_ids: set[str] = set()
        actual_paths: list[Path] = self._enumerate_files(available_roots) if available_roots else []
        known_paths = {self._key(Path(str(row["current_known_path"]))) for row in known}
        fingerprint_cache: dict[tuple[str, int | None], list[Path]] = {}
        cache_invalidations: list[tuple[str, str]] = []
        now = utc_now()

        if scope_status == "SCOPE_UNAVAILABLE":
            events = [{"file_id": str(row["file_id"]), "state": "SCOPE_UNAVAILABLE",
                       "current_path": row["current_known_path"]} for row in known]
        else:
            with self.database.begin() as connection:
                projection_updates: list[dict[str, Any]] = []
                for row in known:
                    file_id = str(row["file_id"])
                    last_path = Path(str(row["current_known_path"]))
                    observed_path = last_path if last_path.is_file() else None
                    event_state = "UNCHANGED"
                    new_fingerprint = row["current_fingerprint"]
                    new_size = row["current_size_bytes"]
                    new_mtime = row["current_mtime_ns"]

                    if observed_path is not None:
                        try:
                            stat = observed_path.stat()
                        except OSError:
                            observed_path = None
                        else:
                            quick_same = (row["current_size_bytes"] == stat.st_size and
                                           row["current_mtime_ns"] == stat.st_mtime_ns)
                            if quick_same:
                                new_size, new_mtime = stat.st_size, stat.st_mtime_ns
                            else:
                                identity = self._safe_identity(observed_path)
                                if identity is not None:
                                    new_size, new_mtime, new_fingerprint = identity.size_bytes, identity.mtime_ns, identity.sha256
                                    if row["current_fingerprint"] and identity.sha256 != row["current_fingerprint"]:
                                        event_state = "MODIFIED_EXTERNALLY"
                                        changed_file_ids.add(file_id)
                                        if self.evidence_cache:
                                            cache_invalidations.append((file_id, identity.sha256))

                    if observed_path is None:
                        fingerprint = row["current_fingerprint"] or row["core_sha256"]
                        candidates = self._find_by_fingerprint(
                            actual_paths, fingerprint, row["current_size_bytes"], fingerprint_cache
                        )
                        if len(candidates) == 1:
                            observed_path = candidates[0]
                            event_state = self._path_change_kind(last_path, observed_path)
                            identity = self._safe_identity(observed_path)
                            if identity is not None:
                                new_size, new_mtime, new_fingerprint = identity.size_bytes, identity.mtime_ns, identity.sha256
                            changed_file_ids.add(file_id)
                            self._update_core_path(connection, row, observed_path, now)
                        elif len(candidates) > 1:
                            event_state = "PATH_CONFLICT"
                            changed_file_ids.add(file_id)
                        else:
                            event_state = "FILE_MISSING"
                            changed_file_ids.add(file_id)

                    if observed_path is not None and event_state == "UNCHANGED" and self._key(observed_path) != self._key(last_path):
                        event_state = self._path_change_kind(last_path, observed_path)
                        changed_file_ids.add(file_id)
                        self._update_core_path(connection, row, observed_path, now)

                    state = {
                        "MODIFIED_EXTERNALLY": "FILE_CHANGED",
                        "FILE_MISSING": "MISSING",
                        "PATH_CONFLICT": "MISSING",
                    }.get(event_state, "ACTIVE")
                    persisted_path = str(observed_path) if observed_path is not None else str(last_path)
                    if (event_state != "UNCHANGED" or persisted_path != str(last_path) or
                            new_fingerprint != row["current_fingerprint"] or
                            new_size != row["current_size_bytes"] or new_mtime != row["current_mtime_ns"]):
                        projection_updates.append({"path": persisted_path, "fingerprint": new_fingerprint,
                                                   "size": new_size, "mtime": new_mtime, "now": now,
                                                   "state": state, "conversation": conversation_id, "file": file_id})
                    events.append({"file_id": file_id, "state": event_state, "current_path": persisted_path})
                # Every inspected active row gets the same verification time.
                # A single update avoids thousands of SQLite round trips for
                # directories whose files have not changed.
                connection.execute(text("""
                    UPDATE conversation_files SET last_verified_at=:now,state='ACTIVE'
                    WHERE conversation_id=:conversation AND removed_from_scope_at IS NULL
                """), {"now": now, "conversation": conversation_id})
                if projection_updates:
                    connection.execute(text("""
                        UPDATE conversation_files
                        SET current_known_path=:path,current_fingerprint=:fingerprint,
                            current_size_bytes=:size,current_mtime_ns=:mtime,
                            last_verified_at=:now,state=:state
                        WHERE conversation_id=:conversation AND file_id=:file
                    """), projection_updates)

        # Evidence writes use their own short transaction and therefore must not
        # run while the ConversationFile projection transaction is open.
        if self.evidence_cache:
            for file_id, fingerprint in cache_invalidations:
                self.evidence_cache.invalidate_file_evidence(file_id, fingerprint)

        known_path_keys = known_paths | {
            self._key(Path(str(item["current_path"])))
            for item in events if item.get("file_id") and item.get("current_path")
        }
        new_files = []
        if detect_new and scope_status == "AVAILABLE":
            for path in actual_paths:
                if self._key(path) not in known_path_keys:
                    new_files.append({"path": str(path), "name": path.name})
                    events.append({"file_id": None, "state": "NEW_FILE", "current_path": str(path)})

        changed = bool(changed_file_ids or new_files)
        if changed:
            with self.database.begin() as connection:
                connection.execute(text("""
                    UPDATE conversation_contexts
                    SET file_state_revision=file_state_revision+1,updated_at=:now
                    WHERE conversation_id=:conversation
                """), {"conversation": conversation_id, "now": now})
                if scope_status == "SCOPE_UNAVAILABLE":
                    connection.execute(text("""
                        UPDATE conversation_plan_approvals SET status='STALE',superseded_at=:now
                        WHERE conversation_id=:conversation AND status='ACTIVE'
                    """), {"conversation": conversation_id, "now": now})
                elif changed_file_ids:
                    placeholders = ",".join(f":f{i}" for i in range(len(changed_file_ids)))
                    params = {"conversation": conversation_id, "now": now,
                              **{f"f{i}": value for i, value in enumerate(changed_file_ids)}}
                    connection.execute(text(f"""
                        UPDATE conversation_plan_approvals SET status='STALE',superseded_at=:now
                        WHERE conversation_id=:conversation AND status='ACTIVE'
                          AND plan_id IN (SELECT DISTINCT plan_id FROM operations WHERE file_id IN ({placeholders}))
                    """), params)

        summary = {
            "conversation_id": conversation_id,
            "scope_status": scope_status,
            "known_files": len(known),
            "unchanged": sum(item["state"] == "UNCHANGED" for item in events),
            "moved": sum(item["state"] == "MOVED_EXTERNALLY" for item in events),
            "renamed": sum(item["state"] == "RENAMED_EXTERNALLY" for item in events),
            "modified": sum(item["state"] == "MODIFIED_EXTERNALLY" for item in events),
            "missing": sum(item["state"] in {"FILE_MISSING", "PATH_CONFLICT"} for item in events),
            "new_files": len(new_files),
            "conflicts": sum(item["state"] == "PATH_CONFLICT" for item in events),
            "requires_user_action": bool(scope_status != "AVAILABLE" or changed or new_files),
            "workspace_changed": changed,
            "changed_file_ids": sorted(changed_file_ids),
            "new_file_items": new_files,
            "events": events,
        }
        with self.database.begin() as connection:
            revision = int(connection.execute(text(
                "SELECT file_state_revision FROM conversation_contexts WHERE conversation_id=:conversation"
            ), {"conversation": conversation_id}).scalar_one())
            connection.execute(text("""
                INSERT INTO conversation_reconciliations(
                  id,conversation_id,trigger,scope_status,file_state_revision,summary_json,requires_user_action,created_at
                ) VALUES(:id,:conversation,:trigger,:scope,:revision,:summary,:requires,:now)
            """), {"id": str(uuid.uuid4()), "conversation": conversation_id, "trigger": trigger,
                    "scope": scope_status, "revision": revision, "summary": canonical_json(summary),
                    "requires": int(summary["requires_user_action"]), "now": now})
        summary["file_state_revision"] = revision
        summary["context_revision"] = self.repository.get_context(conversation_id)["context_revision"]
        summary["conversation_status"] = conversation["status"]
        return summary

    def latest(self, conversation_id: str) -> dict[str, Any] | None:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT * FROM conversation_reconciliations
                WHERE conversation_id=:conversation ORDER BY created_at DESC LIMIT 1
            """), {"conversation": conversation_id}).mappings().first()
        if row is None:
            return None
        result = dict(row)
        result["summary"] = json.loads(result.pop("summary_json") or "{}")
        result["requires_user_action"] = bool(result["requires_user_action"])
        return result

    @staticmethod
    def _key(path: Path) -> str:
        return str(path.resolve(strict=False)).casefold()

    @staticmethod
    def _enumerate_files(roots: list[Path]) -> list[Path]:
        result: list[Path] = []
        for root in roots:
            try:
                result.extend(path for path in root.rglob("*") if path.is_file())
            except OSError:
                continue
        return result

    @staticmethod
    def _safe_identity(path: Path):
        try:
            return read_identity(path)
        except OSError:
            return None

    @staticmethod
    def _path_change_kind(old: Path, new: Path) -> str:
        return "RENAMED_EXTERNALLY" if old.parent == new.parent else "MOVED_EXTERNALLY"

    @staticmethod
    def _find_by_fingerprint(paths: list[Path], fingerprint: str | None, size: int | None,
                             cache: dict[tuple[str, int | None], list[Path]]) -> list[Path]:
        if not fingerprint:
            return []
        key = (fingerprint, size)
        if key in cache:
            return cache[key]
        matches = []
        for path in paths:
            try:
                if size is not None and path.stat().st_size != size:
                    continue
                identity = read_identity(path)
                if identity.sha256 == fingerprint:
                    matches.append(path)
                    if len(matches) > 1:
                        break
            except OSError:
                continue
        cache[key] = matches
        return matches

    @staticmethod
    def _update_core_path(connection, row: Any, path: Path, now: str) -> None:
        try:
            connection.execute(text("""
                UPDATE files SET current_path=:path,path_key=:key,updated_at=:now WHERE id=:file
            """), {"path": str(path), "key": str(path).casefold(), "now": now, "file": row["file_id"]})
        except Exception:
            # A duplicate path in another task is a conflict; ConversationFile is
            # still updated with the observed projection and validation surfaces it.
            return


class RecoveryValidationService:
    """Validate one immutable PlanVersion against current state before execution."""

    def __init__(self, database: Database, repository: ConversationRepository,
                 reconciliation: WorkspaceReconciliationService) -> None:
        self.database = database
        self.repository = repository
        self.reconciliation = reconciliation

    def validate(self, conversation_id: str, plan_version_id: str, *, reconcile: bool = True) -> dict[str, Any]:
        if reconcile:
            current = self.reconciliation.reconcile(conversation_id, trigger="BEFORE_OPERATION")
        else:
            current = self.reconciliation.latest(conversation_id) or {}
        version = self.repository.get_plan_version(plan_version_id)
        context = self.repository.get_context(conversation_id)
        reasons: list[str] = []
        if version["conversation_id"] != conversation_id:
            reasons.append("PLAN_SCOPE_CONFLICT")
        if current.get("scope_status") == "SCOPE_UNAVAILABLE":
            reasons.append("SCOPE_UNAVAILABLE")
        if int(version.get("basis_file_state_revision") or 1) > int(context["file_state_revision"]):
            reasons.append("PLAN_FILE_STATE_STALE")
        affected_ids: set[str] = set()
        if version.get("plan_id"):
            with self.database.engine.connect() as connection:
                operations = list(connection.execute(text("""
                    SELECT o.file_id,o.source_path,o.target_path,o.expected_sha256,
                           o.state AS operation_state,
                           cf.current_known_path,cf.current_fingerprint,cf.state AS conversation_file_state
                    FROM operations o
                    LEFT JOIN conversation_files cf ON cf.conversation_id=:conversation AND cf.file_id=o.file_id
                    WHERE o.plan_id=:plan ORDER BY o.ordinal
                """), {"conversation": conversation_id, "plan": version["plan_id"]}).mappings())
                plan_row = connection.execute(text("SELECT plan_hash,status FROM plans WHERE id=:id"), {"id": version["plan_id"]}).mappings().first()
            if plan_row is None or (version.get("plan_hash") and plan_row["plan_hash"] != version["plan_hash"]):
                reasons.append("PLAN_HASH_MISMATCH")
            for item in operations:
                if item["operation_state"] not in FINAL_STATES and item["operation_state"] not in {"PLANNED", "SKIPPED"}:
                    # An unexecuted plan can contain PLANNED rows; other states
                    # are safe to view but require the existing journal recovery.
                    if version["status"] in {"APPROVED", "EXECUTED"}:
                        reasons.append("EXECUTION_RECOVERY_REQUIRED")
                # ConversationFile state is a current projection; operation_state
                # remains the immutable execution journal state.
                if (item.get("current_known_path") is None or item.get("current_fingerprint") is None) and item.get("conversation_file_state") is not None:
                    reasons.append("FILE_STATE_UNAVAILABLE")
                if item.get("expected_sha256") and item.get("current_fingerprint") and item["expected_sha256"] != item["current_fingerprint"]:
                    affected_ids.add(str(item["file_id"]))
                    reasons.append("PLAN_FILE_STATE_STALE")
                if item.get("conversation_file_state") in {"MISSING", "FILE_CHANGED", "REMOVED"}:
                    reasons.append("PLAN_FILE_STATE_STALE")
                affected_ids.add(str(item["file_id"]))
        # The current reconciliation summary lets unrelated NEW_FILE events stay
        # outside a plan's affected set.
        changed = set(current.get("changed_file_ids") or [])
        if changed & affected_ids:
            reasons.append("PLAN_FILE_STATE_STALE")
        unique_reasons = list(dict.fromkeys(reasons))
        return {
            "conversation_id": conversation_id,
            "plan_version_id": plan_version_id,
            "valid": not unique_reasons,
            "requires_revalidation": bool(unique_reasons),
            "reason_codes": unique_reasons,
            "affected_file_ids": sorted(affected_ids),
            "file_state_revision": context["file_state_revision"],
            "context_revision": context["context_revision"],
            "reconciliation": current,
        }


class SessionRecoveryService:
    """Application restart coordinator for durable Conversation state."""

    def __init__(self, database: Database, repository: ConversationRepository,
                 journal: SqliteOperationJournal, evidence_cache: EvidenceCacheService | None = None) -> None:
        self.database = database
        self.repository = repository
        self.journal = journal
        self.evidence_cache = evidence_cache
        self.workspace = WorkspaceReconciliationService(database, repository, evidence_cache)
        self.validation = RecoveryValidationService(database, repository, self.workspace)

    def audit_startup(self) -> dict[str, int]:
        from guixu.application.pre_execution_replan_guard import recover_interrupted_pre_execution_replans

        restored_replans = recover_interrupted_pre_execution_replans(self.database)
        now = utc_now()
        with self.database.begin() as connection:
            turns = connection.execute(text("""
                UPDATE conversation_agent_turns
                SET status='INTERRUPTED',interruption_code='APP_RESTARTED_DURING_TURN',completed_at=:now
                WHERE status IN ('QUEUED','RUNNING')
            """), {"now": now}).rowcount
            rounds = 0
            rows = connection.execute(text("""
                SELECT er.id,er.execution_plan_id
                FROM conversation_execution_rounds er WHERE er.status='RUNNING'
            """)).mappings().all()
            for row in rows:
                unfinished = connection.execute(text("""
                    SELECT count(*) FROM operations
                    WHERE plan_id=:plan AND state NOT IN ('COMMITTED','SKIPPED','UNDONE','FAILED','CONFLICT','UNDO_CONFLICT')
                """), {"plan": row["execution_plan_id"]}).scalar_one()
                if unfinished:
                    connection.execute(text("""
                        UPDATE conversation_execution_rounds
                        SET status='RECOVERY_REQUIRED',completed_at=COALESCE(completed_at,:now),
                            summary_json=json_set(summary_json,'$.recovery_code','EXECUTION_INTERRUPTED')
                        WHERE id=:id
                    """), {"id": row["id"], "now": now})
                    rounds += 1
            connection.execute(text("""
                UPDATE conversation_undo_plans SET status='RECOVERY_REQUIRED'
                WHERE status='EXECUTING' AND execution_round_id IN (
                  SELECT id FROM conversation_execution_rounds WHERE status='RECOVERY_REQUIRED'
                )
            """))
        return {"agent_turns_interrupted": int(turns or 0), "execution_rounds_recovery_required": rounds,
                "pre_execution_replans_rolled_back": restored_replans}

    def status(self, conversation_id: str, *, reconcile: bool = False) -> dict[str, Any]:
        conversation = self.repository.get(conversation_id)
        if reconcile:
            latest = self.workspace.reconcile(conversation_id, trigger="OPEN")
        else:
            latest = self.workspace.latest(conversation_id)
        with self.database.engine.connect() as connection:
            turns = [dict(row) for row in connection.execute(text("""
                SELECT id,turn_kind,status,interruption_code,retry_of_turn_id,created_at,started_at,completed_at
                FROM conversation_agent_turns WHERE conversation_id=:conversation ORDER BY created_at DESC LIMIT 20
            """), {"conversation": conversation_id}).mappings()]
            model = connection.execute(text("""
                SELECT mp.enabled FROM model_profiles mp WHERE mp.id=:id
            """), {"id": conversation.get("model_profile_id")}).scalar()
        return {
            "conversation_id": conversation_id,
            "conversation_status": conversation["status"],
            "reconciliation": latest,
            "agent_turns": turns,
            "model_available": model is None or bool(model),
            "requires_user_action": bool(latest and latest.get("requires_user_action")),
        }

    def reconcile(self, conversation_id: str, *, trigger: str = "MANUAL") -> dict[str, Any]:
        return self.workspace.reconcile(conversation_id, trigger=trigger)

    def revalidate_plan(self, conversation_id: str, plan_version_id: str) -> dict[str, Any]:
        return self.validation.validate(conversation_id, plan_version_id, reconcile=True)

    def create_agent_turn(self, conversation_id: str, *, turn_kind: str = "ANALYSIS",
                          status: str = "QUEUED", request_hash: str | None = None,
                          task_id: str | None = None, plan_version_id: str | None = None,
                          execution_round_id: str | None = None,
                          retry_of_turn_id: str | None = None) -> dict[str, Any]:
        if status not in {"QUEUED", "RUNNING", "WAITING_FOR_USER", "WAITING_FOR_APPROVAL", "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}:
            raise ValueError("AGENT_TURN_STATUS_INVALID")
        turn_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.begin() as connection:
            if connection.execute(text("SELECT 1 FROM conversations WHERE id=:id"), {"id": conversation_id}).first() is None:
                raise KeyError(conversation_id)
            connection.execute(text("""
                INSERT INTO conversation_agent_turns(
                  id,conversation_id,task_id,plan_version_id,execution_round_id,retry_of_turn_id,
                  turn_kind,status,request_hash,created_at,started_at,last_heartbeat_at
                ) VALUES(:id,:conversation,:task,:plan,:round,:retry,:kind,:status,:hash,:now,
                  CASE WHEN :status='RUNNING' THEN :now END,:now)
            """), {"id": turn_id, "conversation": conversation_id, "task": task_id,
                    "plan": plan_version_id, "round": execution_round_id, "retry": retry_of_turn_id,
                    "kind": turn_kind, "status": status, "hash": request_hash, "now": now})
        return self.get_agent_turn(turn_id)

    def retry_agent_turn(self, turn_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_agent_turns WHERE id=:id"), {"id": turn_id}).mappings().first()
        if row is None:
            raise KeyError(turn_id)
        return self.create_agent_turn(str(row["conversation_id"]), turn_kind=str(row["turn_kind"]),
                                      request_hash=row["request_hash"], task_id=row["task_id"],
                                      plan_version_id=row["plan_version_id"], execution_round_id=row["execution_round_id"],
                                      retry_of_turn_id=turn_id)

    def resume_analysis(self, conversation_id: str) -> dict[str, Any]:
        state = self.status(conversation_id, reconcile=True)
        if state["reconciliation"] and state["reconciliation"].get("scope_status") != "AVAILABLE":
            raise ValueError("SCOPE_UNAVAILABLE")
        return self.create_agent_turn(conversation_id, turn_kind="ANALYSIS", status="QUEUED")

    def get_agent_turn(self, turn_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM conversation_agent_turns WHERE id=:id"), {"id": turn_id}).mappings().first()
        if row is None:
            raise KeyError(turn_id)
        result = dict(row)
        for key in ("checkpoint_json", "result_json"):
            result[key[:-5]] = json.loads(result.pop(key) or "{}")
        return result
