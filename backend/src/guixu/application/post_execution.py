from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text

from guixu.application.coordinator import TaskCoordinator
from guixu.application.parsing import ParsingService
from guixu.application.plan_compiler import PlanCompiler
from guixu.domain.plans import PlanCandidate
from guixu.domain.profiles import FileProfile
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository, canonical_json
from guixu.infrastructure.filesystem.identity import read_identity


SEMANTIC_EVIDENCE_KINDS = {
    "extracted_text", "ocr", "visual_caption", "visual_description", "transcript", "subtitle", "user_context",
}
GLOBAL_MARKERS = ("全部", "整个", "全局", "重新规划", "重新整理", "不要按照", "改成按", "所有文件")
TARGET_MARKERS = ("放到", "移到", "归到", "合并到", "放进", "移进")


class WorkspaceStateService:
    """Build and synchronize the current filesystem projection for one Conversation."""

    def __init__(self, database: Database, repository: ConversationRepository) -> None:
        self.database = database
        self.repository = repository

    def current_state(self, conversation_id: str, *, file_ids: list[str] | None = None) -> dict[str, Any]:
        conversation = self.repository.get(conversation_id)
        context = self.repository.get_context(conversation_id)
        with self.database.engine.connect() as connection:
            scopes = [dict(row) for row in connection.execute(text("""
                SELECT * FROM conversation_scopes
                WHERE conversation_id=:conversation AND revoked_at IS NULL ORDER BY created_at
            """), {"conversation": conversation_id}).mappings()]
            latest_execution = connection.execute(text("""
                SELECT * FROM conversation_execution_rounds
                WHERE conversation_id=:conversation AND status='COMPLETED'
                ORDER BY round_number DESC LIMIT 1
            """), {"conversation": conversation_id}).mappings().first()
            latest_executed_version = connection.execute(text("""
                SELECT pv.* FROM conversation_plan_versions pv
                JOIN conversation_execution_rounds er ON er.plan_version_id=pv.id
                WHERE pv.conversation_id=:conversation AND er.status='COMPLETED'
                ORDER BY er.round_number DESC LIMIT 1
            """), {"conversation": conversation_id}).mappings().first()
            current_version = None
            if context.get("current_plan_version_id"):
                current_version = connection.execute(text("""
                    SELECT * FROM conversation_plan_versions WHERE id=:id
                """), {"id": context["current_plan_version_id"]}).mappings().first()
            rows = self._file_rows(connection, conversation_id, file_ids)
        version_for_taxonomy = current_version or latest_executed_version
        taxonomy = self._taxonomy(version_for_taxonomy)
        files = [self._file_payload(row) for row in rows]
        return {
            "conversation_id": conversation_id,
            "conversation_status": conversation["status"],
            "authorized_scope": scopes,
            "file_state_revision": context["file_state_revision"],
            "context_revision": context["context_revision"],
            "max_directory_depth": context["max_directory_depth"],
            "latest_execution_round_id": latest_execution["id"] if latest_execution else None,
            "latest_execution_round": dict(latest_execution) if latest_execution else None,
            "latest_executed_plan_version_id": latest_executed_version["id"] if latest_executed_version else None,
            "current_plan_version_id": context.get("current_plan_version_id"),
            "current_taxonomy": taxonomy,
            "current_requirements": context.get("confirmed_requirements", []),
            "current_files": files,
            "total_scope_files": len(files),
        }

    def sync_workspace_state(self, conversation_id: str, *, file_ids: list[str] | None = None) -> dict[str, Any]:
        state = self.current_state(conversation_id, file_ids=file_ids)
        if file_ids and len(state["current_files"]) != len(set(file_ids)):
            raise ValueError("AFFECTED_SCOPE_INVALID")
        roots = [Path(str(scope["source_root"])) for scope in state["authorized_scope"]]
        events: list[dict[str, Any]] = []
        changed = False
        now = utc_now()
        with self.database.begin() as connection:
            for item in state["current_files"]:
                file_id = item["file_id"]
                core_path = Path(item["core_current_path"])
                observed_path = core_path
                external_state: str | None = None
                if not core_path.is_file():
                    matches = self._find_by_fingerprint(roots, item.get("current_fingerprint"), item.get("current_size_bytes"))
                    if len(matches) == 1:
                        observed_path = matches[0]
                        external_state = "FILE_MOVED_EXTERNALLY"
                        connection.execute(text("""
                            UPDATE files SET current_path=:path,path_key=:key,updated_at=:now WHERE id=:file
                        """), {"path": str(observed_path), "key": str(observed_path).casefold(), "now": now, "file": file_id})
                    elif len(matches) > 1:
                        external_state = "PATH_CONFLICT"
                    else:
                        external_state = "FILE_MISSING"
                if external_state == "PATH_CONFLICT":
                    persisted_state = "MISSING"
                    identity = None
                elif observed_path.is_file():
                    identity = read_identity(observed_path)
                    if item.get("current_fingerprint") and identity.sha256 != item["current_fingerprint"]:
                        external_state = "FILE_CHANGED"
                        persisted_state = "FILE_CHANGED"
                    else:
                        persisted_state = "ACTIVE"
                        if str(observed_path) != item["current_known_path"] and external_state is None:
                            internal = connection.execute(text("""
                                SELECT 1 FROM operations
                                WHERE file_id=:file AND state IN ('COMMITTED','UNDONE') AND target_path=:path LIMIT 1
                            """), {"file": file_id, "path": str(observed_path)}).first()
                            if internal is None:
                                external_state = "FILE_MOVED_EXTERNALLY"
                else:
                    identity = None
                    persisted_state = "MISSING"
                    external_state = external_state or "FILE_MISSING"
                new_path = str(observed_path)
                new_fingerprint = identity.sha256 if identity and persisted_state == "ACTIVE" else item.get("current_fingerprint")
                size = identity.size_bytes if identity else item.get("current_size_bytes")
                mtime = identity.mtime_ns if identity else item.get("current_mtime_ns")
                if (new_path != item["current_known_path"] or persisted_state != item["state"] or
                        (new_fingerprint and new_fingerprint != item.get("current_fingerprint"))):
                    changed = True
                connection.execute(text("""
                    UPDATE conversation_files SET current_known_path=:path,current_fingerprint=:fingerprint,
                      current_size_bytes=:size,current_mtime_ns=:mtime,last_verified_at=:now,state=:state
                    WHERE conversation_id=:conversation AND file_id=:file
                """), {"path": new_path, "fingerprint": new_fingerprint, "size": size, "mtime": mtime,
                        "now": now, "state": persisted_state, "conversation": conversation_id, "file": file_id})
                events.append({"file_id": file_id, "state": external_state or "UNCHANGED", "current_path": new_path})
            if changed:
                connection.execute(text("""
                    UPDATE conversation_contexts
                    SET file_state_revision=file_state_revision+1,context_revision=context_revision+1,updated_at=:now
                    WHERE conversation_id=:conversation
                """), {"conversation": conversation_id, "now": now})
                connection.execute(text("""
                    UPDATE conversation_plan_approvals SET status='STALE',superseded_at=:now
                    WHERE conversation_id=:conversation AND status='ACTIVE'
                """), {"conversation": conversation_id, "now": now})
        refreshed = self.current_state(conversation_id, file_ids=file_ids)
        refreshed["sync_events"] = events
        refreshed["workspace_changed"] = changed
        return refreshed

    @staticmethod
    def _find_by_fingerprint(roots: list[Path], fingerprint: str | None, size: int | None) -> list[Path]:
        if not fingerprint:
            return []
        matches: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            for candidate in root.rglob("*"):
                try:
                    if not candidate.is_file() or (size is not None and candidate.stat().st_size != size):
                        continue
                    if read_identity(candidate).sha256 == fingerprint:
                        matches.append(candidate)
                        if len(matches) > 1:
                            return matches
                except OSError:
                    continue
        return matches

    @staticmethod
    def _taxonomy(version: Any) -> dict[str, Any]:
        if version is None:
            return {"taxonomy_id": None, "nodes": []}
        raw = version.get("taxonomy_snapshot_json") or "{}"
        snapshot = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if isinstance(snapshot, list):
            snapshot = {"nodes": snapshot}
        snapshot.setdefault("nodes", snapshot.get("categories", []))
        snapshot.setdefault("taxonomy_id", version.get("taxonomy_id"))
        return snapshot

    @staticmethod
    def _file_rows(connection, conversation_id: str, file_ids: list[str] | None) -> list[Any]:
        clause = ""
        params: dict[str, Any] = {"conversation": conversation_id}
        if file_ids:
            names = []
            for index, file_id in enumerate(dict.fromkeys(file_ids)):
                key = f"file_{index}"
                params[key] = file_id
                names.append(f":{key}")
            clause = f" AND cf.file_id IN ({','.join(names)})"
        return list(connection.execute(text(f"""
            SELECT cf.*,f.task_id,f.current_path AS core_current_path,f.sha256 AS core_sha256,
                   f.size_bytes AS core_size_bytes,f.mtime_ns AS core_mtime_ns,f.modality,
                   fp.profile_json,
                   COALESCE(cf.current_category_id,
                     (SELECT r.category_id FROM reviews r WHERE r.file_id=cf.file_id ORDER BY r.revision DESC LIMIT 1),
                     (SELECT c.category_id FROM classifications c WHERE c.file_id=cf.file_id ORDER BY c.attempt DESC,c.created_at DESC LIMIT 1)
                   ) AS resolved_category_id
            FROM conversation_files cf
            JOIN files f ON f.id=cf.file_id
            LEFT JOIN file_profiles fp ON fp.id=(
              SELECT fp2.id FROM file_profiles fp2 WHERE fp2.file_id=cf.file_id ORDER BY fp2.created_at DESC LIMIT 1
            )
            WHERE cf.conversation_id=:conversation AND cf.removed_from_scope_at IS NULL{clause}
            ORDER BY cf.added_at,cf.id
        """), params).mappings())

    @staticmethod
    def _file_payload(row: Any) -> dict[str, Any]:
        result = dict(row)
        raw_profile = result.pop("profile_json", None)
        try:
            result["profile"] = json.loads(raw_profile) if raw_profile else None
        except json.JSONDecodeError:
            result["profile"] = None
        result["category_id"] = result.pop("resolved_category_id", None)
        result["exists"] = Path(str(result["core_current_path"])).is_file()
        return result


class AffectedScopeResolver:
    """Resolve taxonomy references, then expand them to DB-backed file IDs."""

    def resolve(self, user_message: str, workspace: dict[str, Any]) -> dict[str, Any]:
        if not workspace.get("latest_execution_round_id"):
            raise ValueError("NO_EXECUTED_BASELINE")
        message = user_message.strip()
        if not message:
            raise ValueError("REFINEMENT_AMBIGUOUS")
        nodes = workspace.get("current_taxonomy", {}).get("nodes", [])
        reference_text = message.replace("其他不要动", "")
        categories: list[tuple[str, str]] = []
        for node in nodes:
            category_id = node.get("category_id") or node.get("id")
            name = node.get("name") or node.get("label")
            if category_id and name and str(name).casefold() in reference_text.casefold():
                categories.append((str(category_id), str(name)))
        global_replan = any(marker in message for marker in GLOBAL_MARKERS)
        target_category_id = self._target_category(message, categories)
        affected = [category_id for category_id, _ in categories if category_id != target_category_id]
        if global_replan:
            affected = sorted({str(item.get("category_id")) for item in workspace["current_files"] if item.get("category_id")})
            candidates = [item["file_id"] for item in workspace["current_files"]]
            scope_type = "GLOBAL"
        else:
            if not affected:
                raise ValueError("REFINEMENT_AMBIGUOUS")
            affected_set = set(affected)
            candidates = [item["file_id"] for item in workspace["current_files"] if item.get("category_id") in affected_set]
            scope_type = "LOCAL" if len(affected_set) == 1 else "PARTIAL"
        if not candidates:
            raise ValueError("AFFECTED_SCOPE_EMPTY")
        return {
            "scope_type": scope_type,
            "affected_category_ids": list(dict.fromkeys(affected)),
            "candidate_file_ids": candidates,
            "target_category_id": target_category_id,
            "requires_global_replan": global_replan,
            "preserve_unaffected": not global_replan or "其他不要动" in message,
            "reason": "Resolved only from current taxonomy IDs and ConversationFile membership.",
        }

    @staticmethod
    def _target_category(message: str, categories: list[tuple[str, str]]) -> str | None:
        for marker in TARGET_MARKERS:
            if marker not in message:
                continue
            tail = message.split(marker, 1)[1].casefold()
            for category_id, name in categories:
                if name.casefold() in tail:
                    return category_id
        return None


class EvidenceReuseService:
    def decide(self, file: dict[str, Any]) -> str:
        if file.get("state") == "FILE_CHANGED":
            return "INVALID"
        if file.get("state") in {"MISSING", "REMOVED"} or not file.get("exists"):
            return "INVALID"
        profile = file.get("profile") or {}
        evidence = profile.get("evidence") if isinstance(profile, dict) else None
        usable = any(
            isinstance(item, dict) and item.get("kind") in SEMANTIC_EVIDENCE_KINDS and len(str(item.get("text") or "").strip()) >= 4
            for item in (evidence or [])
        )
        return "REUSE" if usable else "REFRESH_REQUIRED"


class PostExecutionConversationService:
    """Narrow orchestration for a second or later, approval-gated DELTA round."""

    def __init__(self, *, database: Database, conversations: ConversationRepository,
                 tasks: TaskRepository, journal: SqliteOperationJournal,
                 coordinator: TaskCoordinator, parsing: ParsingService,
                 evaluator: Callable[..., list[dict[str, Any]]]) -> None:
        self.database = database
        self.conversations = conversations
        self.tasks = tasks
        self.journal = journal
        self.coordinator = coordinator
        self.parsing = parsing
        self.evaluator = evaluator
        self.workspace = WorkspaceStateService(database, conversations)
        self.scope_resolver = AffectedScopeResolver()
        self.evidence = EvidenceReuseService()

    def prepare_refinement(self, conversation_id: str, *, user_message: str,
                           confirmed_global: bool = False) -> dict[str, Any]:
        initial = self.workspace.current_state(conversation_id)
        scope = self.scope_resolver.resolve(user_message, initial)
        if scope["requires_global_replan"] and not confirmed_global:
            decisions = [self.evidence.decide(item) for item in initial["current_files"]]
            return {
                "status": "GLOBAL_REPLAN_CONFIRMATION_REQUIRED",
                "intent": "POST_EXECUTION_REFINEMENT",
                "affected_scope": scope,
                "metrics": {**self._metrics(initial["total_scope_files"], len(scope["candidate_file_ids"]), decisions, 0),
                            "ai_calls": 0},
            }
        synced = self.workspace.sync_workspace_state(conversation_id, file_ids=scope["candidate_file_ids"])
        external = [event for event in synced.get("sync_events", []) if event["state"] != "UNCHANGED"]
        blocking = next((event for event in external if event["state"] in {"FILE_CHANGED", "FILE_MISSING", "PATH_CONFLICT", "FILE_MOVED_EXTERNALLY"}), None)
        if blocking:
            raise ValueError(blocking["state"])
        by_id = {item["file_id"]: item for item in synced["current_files"]}
        evidence_decisions = {file_id: self.evidence.decide(by_id[file_id]) for file_id in scope["candidate_file_ids"]}
        invalid = [file_id for file_id, decision in evidence_decisions.items() if decision == "INVALID"]
        if invalid:
            raise ValueError("WORKSPACE_STATE_STALE")
        prepared: list[tuple[FileProfile, list[str], bool]] = []
        for file_id in scope["candidate_file_ids"]:
            item = by_id[file_id]
            refresh = evidence_decisions[file_id] == "REFRESH_REQUIRED"
            if refresh:
                task = self.tasks.get(item["task_id"])
                outcome = self.parsing.parse(item["task_id"], file_id, task["settings"]["analysis_preset"])
                prepared.append((outcome.profile, list(outcome.cache_artifacts), True))
            else:
                if not item.get("profile"):
                    raise ValueError("EVIDENCE_UNAVAILABLE")
                prepared.append((FileProfile.model_validate(item["profile"]), [], False))
        baseline = initial["latest_execution_round"]
        with self.database.engine.connect() as connection:
            plan_row = connection.execute(text("SELECT task_id FROM plans WHERE id=:id"), {"id": baseline["execution_plan_id"]}).first()
        if plan_row is None:
            raise ValueError("NO_EXECUTED_BASELINE")
        task_id = str(plan_row[0])
        task = self.tasks.get(task_id)
        profile_id = task.get("model_profile_id")
        if not profile_id:
            raise ValueError("MODEL_UNAVAILABLE")
        evaluations = self.evaluator(task_id=task_id, profile_id=profile_id, items=prepared,
                                     instruction=user_message, taxonomy=initial["current_taxonomy"],
                                     target_category_id=scope["target_category_id"])
        decisions = self._validate_evaluations(evaluations, scope, initial["current_taxonomy"])
        profile_by_id = {item.file_id: item for item, _, _ in prepared}
        for decision in decisions:
            if (evidence_decisions.get(decision["file_id"]) == "REFRESH_REQUIRED" and
                    profile_by_id[decision["file_id"]].modality == "image" and decision.get("reason")):
                self.tasks.append_model_evidence(
                    decision["file_id"], text_value=decision["reason"], model_profile_id=profile_id,
                    prompt_version="post-execution-refinement-v1",
                )
        move_decisions = [item for item in decisions if item["matches"]]
        if not move_decisions:
            raise ValueError("DELTA_PLAN_EMPTY")
        core_plan = self._build_delta_plan(task, initial, move_decisions)
        self.journal.persist_plan(core_plan, task["revision"])
        context = self.conversations.get_context(conversation_id)
        requirements = list(context.get("confirmed_requirements") or [])
        requirements.append({"id": f"req_{context['context_revision'] + 1}", "text": user_message,
                             "status": "active", "scope": scope["scope_type"],
                             "category_ids": scope["affected_category_ids"]})
        context = self.conversations.update_context(conversation_id, context["context_revision"],
                                                    {"confirmed_requirements": requirements})
        current = self.conversations.get_current_plan_version(conversation_id)
        changes = {
            "scope": scope,
            "moves": [{"file_id": item["file_id"], "target_category_id": item["target_category_id"],
                       "reason": item.get("reason", "")} for item in move_decisions],
            "metrics": self._metrics(initial["total_scope_files"], len(scope["candidate_file_ids"]),
                                     list(evidence_decisions.values()), len(move_decisions)),
        }
        conversation_plan_kind = "FULL" if scope["scope_type"] == "GLOBAL" else "DELTA"
        version = self.conversations.create_plan_version(
            conversation_id,
            expected_context_revision=context["context_revision"],
            basis_context_revision=context["context_revision"],
            parent_plan_version_id=current["id"],
            baseline_execution_round_id=baseline["id"],
            source="USER_REQUEST", plan_kind=conversation_plan_kind, status="PROPOSED",
            taxonomy_id=initial["current_taxonomy"].get("taxonomy_id"),
            taxonomy_snapshot=initial["current_taxonomy"], plan_id=core_plan.plan_id,
            plan_hash=core_plan.plan_hash,
            summary=("全局重新规划" if conversation_plan_kind == "FULL" else "局部调整") + f" · {len(move_decisions)} 个文件",
            change_summary=changes, affected_file_count=len(move_decisions),
            kept_file_count=initial["total_scope_files"] - len(move_decisions), conflict_count=0,
        )
        assistant = self.conversations.append_message(
            conversation_id, "ASSISTANT",
            f"我检查了本轮影响范围中的 {len(scope['candidate_file_ids'])} 个文件，建议调整 {len(move_decisions)} 个；其他文件保持不变。目前还没有移动文件。",
            message_type="PLAN_PROPOSAL", referenced_plan_version_id=version["id"], metadata=changes["metrics"],
        )
        return {"status": "WAITING_FOR_APPROVAL", "intent": "POST_EXECUTION_REFINEMENT",
                "affected_scope": scope, "plan_version": version, "assistant_message": assistant,
                "metrics": changes["metrics"]}

    def approve(self, conversation_id: str, plan_version_id: str, *, expected_context_revision: int | None = None,
                plan_hash: str | None = None, authorization: dict[str, Any] | None = None) -> dict[str, Any]:
        approval = self.conversations.approve_plan_version(
            conversation_id, plan_version_id, expected_context_revision=expected_context_revision,
            plan_hash=plan_hash, authorization=authorization,
        )
        with self.database.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT p.task_id,t.revision,p.status,p.plan_hash FROM plans p JOIN tasks t ON t.id=p.task_id
                WHERE p.id=:plan
            """), {"plan": approval["plan_id"]}).mappings().one()
        if row["status"] == "validated":
            self.journal.approve(approval["plan_id"], row["plan_hash"], int(row["revision"]))
        return approval

    def execute(self, conversation_id: str, plan_version_id: str, *, expected_context_revision: int | None = None,
                plan_hash: str | None = None) -> dict[str, Any]:
        version = self.conversations.get_plan_version(plan_version_id)
        if (version["conversation_id"] != conversation_id or
                version.get("plan_kind") not in {"FULL", "DELTA"} or
                not version.get("baseline_execution_round_id")):
            raise ValueError("PLAN_VERSION_SCOPE_CONFLICT")
        current_workspace = self.workspace.current_state(conversation_id)
        if current_workspace.get("latest_execution_round_id") != version.get("baseline_execution_round_id"):
            raise ValueError("DELTA_PLAN_STALE")
        change_summary = version.get("change_summary") or {}
        affected_ids = [str(item.get("file_id")) for item in change_summary.get("moves", []) if isinstance(item, dict) and item.get("file_id")]
        if affected_ids:
            synced = self.workspace.sync_workspace_state(conversation_id, file_ids=affected_ids)
            stale_event = next((event for event in synced.get("sync_events", []) if event["state"] != "UNCHANGED"), None)
            if stale_event:
                raise ValueError(stale_event["state"] if stale_event["state"] in {"FILE_MOVED_EXTERNALLY", "FILE_CHANGED", "FILE_MISSING", "PATH_CONFLICT"} else "DELTA_PLAN_STALE")
        round_row = self.conversations.request_execution(
            conversation_id, plan_version_id, expected_context_revision=expected_context_revision,
            plan_hash=plan_hash, status="RUNNING", affected_file_count=version["affected_file_count"],
            summary={"description": "后续整理执行中", "plan_kind": version["plan_kind"]},
        )
        with self.database.engine.connect() as connection:
            core = connection.execute(text("""
                SELECT p.task_id,p.plan_hash,t.revision FROM plans p JOIN tasks t ON t.id=p.task_id WHERE p.id=:plan
            """), {"plan": version["plan_id"]}).mappings().one()
        try:
            self.coordinator.execute(core["task_id"], version["plan_id"], core["plan_hash"], int(core["revision"]))
            completed = self.conversations.complete_execution_round(
                round_row["id"], summary={"description": f"本轮调整完成，移动 {version['affected_file_count']} 个文件，其他文件没有变化。",
                                          "plan_kind": version["plan_kind"]},
            )
            self.conversations.append_message(
                conversation_id, "ASSISTANT",
                f"本轮调整完成。移动 {version['affected_file_count']} 个文件，其他文件没有变化。",
                message_type="EXECUTION_RESULT", referenced_plan_version_id=plan_version_id,
                referenced_execution_round_id=completed["id"],
            )
            return {"execution_round": completed, "workspace": self.workspace.current_state(conversation_id)}
        except Exception:
            self.conversations.update_execution_round(round_row["id"], "FAILED",
                                                      summary={"description": "本轮执行未完成。"})
            raise

    def _build_delta_plan(self, task: dict[str, Any], workspace: dict[str, Any],
                          decisions: list[dict[str, Any]]):
        files = {item["file_id"]: item for item in workspace["current_files"]}
        roots = [Path(str(scope["source_root"])) for scope in workspace["authorized_scope"]]
        if not roots:
            raise ValueError("SCOPE_VIOLATION")
        candidates: list[PlanCandidate] = []
        for decision in decisions:
            file = files.get(decision["file_id"])
            if file is None:
                raise ValueError("TOOL_VALIDATION_FAILED")
            source = Path(str(file["core_current_path"]))
            root = next((candidate for candidate in roots if source == candidate or candidate in source.parents), None)
            if root is None:
                raise ValueError("SCOPE_VIOLATION")
            segments = self._category_segments(workspace["current_taxonomy"], decision["target_category_id"])
            candidates.append(PlanCandidate(
                file_id=file["file_id"], source_path=source, source_root=root, destination_root=root,
                category_id=decision["target_category_id"], category_segments=segments,
                modality=file["modality"], companion_group_id=None,
            ))
        taxonomy_hash = ""
        taxonomy_id = workspace["current_taxonomy"].get("taxonomy_id")
        if taxonomy_id:
            with self.database.engine.connect() as connection:
                taxonomy_hash = connection.execute(text("SELECT tree_hash FROM taxonomies WHERE id=:id"), {"id": taxonomy_id}).scalar() or ""
        plan = PlanCompiler().compile(
            task_id=task["id"], version=self.tasks.next_plan_version(task["id"]),
            operation_mode=task["settings"]["operation_mode"], settings_hash=task["settings_hash"],
            taxonomy_hashes=(taxonomy_hash,) if taxonomy_hash else tuple(), candidates=candidates,
            max_depth=workspace.get("max_directory_depth", 3) or 3,
            collision_policy=task["settings"]["collision_policy"], protected_root_names=set(),
        )
        if not any(operation.action in {"move", "copy"} for operation in plan.operations):
            raise ValueError("DELTA_PLAN_EMPTY")
        return plan

    @staticmethod
    def _category_segments(taxonomy: dict[str, Any], category_id: str) -> tuple[str, ...]:
        nodes = {str(node.get("category_id") or node.get("id")): node for node in taxonomy.get("nodes", [])}
        if category_id not in nodes:
            raise ValueError("TOOL_VALIDATION_FAILED")
        result: list[str] = []
        cursor: str | None = category_id
        visited: set[str] = set()
        while cursor:
            if cursor in visited or cursor not in nodes:
                raise ValueError("AFFECTED_SCOPE_INVALID")
            visited.add(cursor)
            node = nodes[cursor]
            result.append(str(node.get("name") or node.get("label") or ""))
            parent = node.get("parent_id") or node.get("parentId")
            cursor = str(parent) if parent else None
        return tuple(reversed(result))

    @staticmethod
    def _validate_evaluations(evaluations: list[dict[str, Any]], scope: dict[str, Any],
                              taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = set(scope["candidate_file_ids"])
        allowed = {str(node.get("category_id") or node.get("id")) for node in taxonomy.get("nodes", [])}
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in evaluations:
            file_id = str(item.get("file_id"))
            target = item.get("target_category_id")
            if file_id not in candidates or file_id in seen or (item.get("matches") and str(target) not in allowed):
                raise ValueError("TOOL_VALIDATION_FAILED")
            seen.add(file_id)
            result.append({"file_id": file_id, "matches": bool(item.get("matches")),
                           "target_category_id": str(target) if target is not None else None,
                           "reason": str(item.get("reason") or "")[:1000]})
        if seen != candidates:
            raise ValueError("TOOL_VALIDATION_FAILED")
        return result

    @staticmethod
    def _metrics(total: int, affected: int, evidence: list[str], delta: int) -> dict[str, int]:
        return {"total_scope_files": total, "affected_files": affected,
                "evidence_reused": sum(item == "REUSE" for item in evidence),
                "evidence_refreshed": sum(item == "REFRESH_REQUIRED" for item in evidence),
                "invalid_evidence": sum(item == "INVALID" for item in evidence),
                "delta_plan_count": delta, "ai_calls": 1 if affected else 0}
