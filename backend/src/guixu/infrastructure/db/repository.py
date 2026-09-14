from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

from guixu.domain.files import ScannedFile
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.filesystem.scanner import ScanScope
from guixu.domain.profiles import ParseOutcome


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, name: str, settings: TaskSettings, classification_request: dict[str, Any], model_profile_id: str | None = None, model_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        now = utc_now()
        settings_data = settings.model_dump(mode="json")
        rule_ids = classification_request.get("rule_ids", [])
        with self.database.engine.connect() as connection:
            rule_rows = connection.execute(text("SELECT * FROM rules ORDER BY priority,id")).mappings().all() if rule_ids else []
            rules_snapshot = [
                {"id": row["id"], "name": row["name"], "priority": row["priority"], "enabled": bool(row["enabled"]),
                 "scope": json.loads(row["scope_json"]), "condition": json.loads(row["condition_json"]),
                 "action": json.loads(row["action_json"]), "revision": row["revision"]}
                for row in rule_rows if row["id"] in rule_ids
            ]
            template_key = classification_request.get("template_key")
            template_version = classification_request.get("template_version")
            template_row = None
            if template_key:
                query = "SELECT definition_json FROM template_versions WHERE template_key=:key"
                params: dict[str, Any] = {"key": template_key}
                if template_version:
                    query += " AND version=:version"; params["version"] = template_version
                query += " ORDER BY version DESC LIMIT 1"
                template_row = connection.execute(text(query), params).first()
            template_snapshot = json.loads(template_row[0]) if template_row else {}
        with self.database.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO tasks(
                  id,name,status,phase,revision,settings_json,settings_hash,
                  classification_request_json,model_profile_id,model_snapshot_json,rules_snapshot_json,template_snapshot_json,created_at,updated_at
                ) VALUES(:id,:name,'DRAFT','SETUP',1,:settings,:settings_hash,:request,:model_profile_id,:model_snapshot,:rules_snapshot,:template_snapshot,:now,:now)
                """),
                {
                    "id": task_id,
                    "name": name,
                    "settings": canonical_json(settings_data),
                    "settings_hash": digest_json(settings_data),
                    "request": canonical_json(classification_request),
                    "model_profile_id": model_profile_id,
                    "model_snapshot": canonical_json(model_snapshot or {}),
                    "rules_snapshot": canonical_json(rules_snapshot),
                    "template_snapshot": canonical_json(template_snapshot),
                    "now": now,
                },
            )
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM tasks WHERE id=:id"), {"id": task_id}).mappings().first()
        if row is None:
            raise KeyError(task_id)
        result = dict(row)
        for key in ("settings_json", "classification_request_json", "model_snapshot_json", "rules_snapshot_json", "template_snapshot_json", "counters_json", "checkpoint_json"):
            result[key[:-5] if key.endswith("_json") else key] = json.loads(result.pop(key))
        return result

    def list(self) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("SELECT id,name,status,phase,revision,settings_json,counters_json,created_at,updated_at FROM tasks ORDER BY updated_at DESC")).mappings()
            results = []
            for row in rows:
                item = dict(row)
                item["settings"] = json.loads(item.pop("settings_json"))
                item["counters"] = json.loads(item.pop("counters_json"))
                results.append(item)
            return results

    def begin_scan(self, task_id: str, expected_revision: int) -> int:
        now = utc_now()
        with self.database.begin() as connection:
            result = connection.execute(
                text("""
                UPDATE tasks SET status='RUNNING',phase='SCAN',revision=revision+1,updated_at=:now
                WHERE id=:id AND status='DRAFT' AND revision=:revision
                """),
                {"id": task_id, "revision": expected_revision, "now": now},
            )
            if result.rowcount != 1:
                raise ValueError("REVISION_CONFLICT")
            connection.execute(
                text("INSERT INTO task_events(task_id,seq,event_type,payload_json,created_at) VALUES(:id,1,'scan_started','{}',:now)"),
                {"id": task_id, "now": now},
            )
        return expected_revision + 1

    def store_scan(self, task_id: str, scopes: list[ScanScope], files: list[ScannedFile], warnings: list[str], operation_mode: str) -> None:
        now = utc_now()
        scope_ids = {scope.scope_id: str(uuid.uuid4()) for scope in scopes}
        counters = {
            "discovered": len(files),
            "eligible": sum(item.scan_status == "eligible" for item in files),
            "excluded": sum(item.scan_status == "excluded" for item in files),
            "executed": 0,
        }
        with self.database.begin() as connection:
            for scope in scopes:
                connection.execute(
                    text("""
                    INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name,settings_json)
                    VALUES(:id,:task_id,:kind,:source,:destination,:display,'{}')
                    """),
                    {
                        "id": scope_ids[scope.scope_id], "task_id": task_id, "kind": scope.kind,
                        "source": str(scope.source_root), "destination": str(scope.destination_root),
                        "display": scope.display_name,
                    },
                )
            for item in files:
                path_key = str(item.path).casefold()
                file_id = str(uuid.uuid5(uuid.UUID(task_id), path_key))
                connection.execute(
                    text("""
                    INSERT INTO files(
                      id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,
                      extension,modality,size_bytes,mtime_ns,scan_status,exclusion_code,metadata_json,created_at,updated_at
                    ) VALUES(:id,:task,:scope,:path,:path,:path_key,:relative,:basename,:extension,:modality,
                      :size,:mtime,:status,:exclusion,:metadata,:now,:now)
                    """),
                    {
                        "id": file_id, "task": task_id, "scope": scope_ids[item.scope_id], "path": str(item.path),
                        "path_key": path_key, "relative": item.relative_path, "basename": item.path.name,
                        "extension": item.path.suffix.lower(), "modality": item.modality, "size": item.size_bytes,
                        "mtime": item.mtime_ns, "status": item.scan_status, "exclusion": item.exclusion_code,
                        "metadata": canonical_json({"type_evidence": f"extension:{item.path.suffix.lower() or '(none)'}"}),
                        "now": now,
                    },
                )
                if item.companion_group_id:
                    connection.execute(
                        text("UPDATE files SET companion_group_id=:group_id WHERE id=:id"),
                        {"id": file_id, "group_id": item.companion_group_id},
                    )
            final_status = "COMPLETED" if operation_mode == "report_only" else "AWAITING_EXECUTION_APPROVAL"
            final_phase = "REPORT" if operation_mode == "report_only" else "PREVIEW"
            connection.execute(
                text("""
                UPDATE tasks SET status=:status,phase=:phase,revision=revision+1,
                  counters_json=:counters,checkpoint_json=:checkpoint,updated_at=:now,finished_at=:finished
                WHERE id=:id AND status='RUNNING' AND phase='SCAN'
                """),
                {"id": task_id, "status": final_status, "phase": final_phase,
                 "counters": canonical_json(counters), "checkpoint": canonical_json({"warnings": warnings}),
                 "now": now, "finished": now if operation_mode == "report_only" else None},
            )
            connection.execute(
                text("INSERT INTO task_events(task_id,seq,event_type,payload_json,created_at) VALUES(:id,2,'scan_completed',:payload,:now)"),
                {"id": task_id, "payload": canonical_json(counters), "now": now},
            )

    def fail_scan(self, task_id: str, code: str) -> None:
        with self.database.begin() as connection:
            connection.execute(
                text("UPDATE tasks SET status='FAILED',last_error_code=:code,revision=revision+1,updated_at=:now WHERE id=:id"),
                {"id": task_id, "code": code, "now": utc_now()},
            )

    def list_files(self, task_id: str, limit: int = 100, offset: int = 0,
                   query: str = "", scan_status: str | None = None) -> tuple[list[dict[str, Any]], int]:
        clauses = ["f.task_id=:id"]
        params: dict[str, Any] = {"id": task_id, "limit": limit, "offset": offset}
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(f.basename LIKE :query ESCAPE '\\' OR f.relative_path LIKE :query ESCAPE '\\')")
            params["query"] = f"%{escaped}%"
        if scan_status:
            clauses.append("f.scan_status=:status"); params["status"] = scan_status
        where = " AND ".join(clauses)
        with self.database.engine.connect() as connection:
            total = connection.execute(text(f"SELECT count(*) FROM files f WHERE {where}"), params).scalar_one()
            rows = connection.execute(
                text(f"""
                SELECT f.id,f.basename,f.relative_path,f.extension,f.modality,f.size_bytes,f.mtime_ns,f.scan_status,
                       f.exclusion_code,f.metadata_json,s.id AS scope_id,s.display_name AS scope_name
                FROM files f JOIN task_scopes s ON s.id=f.scope_id
                WHERE {where} ORDER BY f.path_key,f.id LIMIT :limit OFFSET :offset
                """),
                params,
            ).mappings()
            items = [{**dict(row), "metadata": json.loads(row["metadata_json"])} for row in rows]
            for item in items:
                item.pop("metadata_json")
            return items, total

    def get_file(self, task_id: str, file_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT f.*,s.display_name AS scope_name FROM files f
                JOIN task_scopes s ON s.id=f.scope_id
                WHERE f.task_id=:task_id AND f.id=:file_id
            """), {"task_id": task_id, "file_id": file_id}).mappings().first()
        if row is None:
            raise KeyError(file_id)
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item

    def store_profile(self, outcome: ParseOutcome, cache_key: str, options_hash: str) -> None:
        profile = outcome.profile
        with self.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO file_profiles(id,file_id,cache_key,parser_version,options_hash,status,profile_json,created_at)
                VALUES(:id,:file_id,:cache_key,:parser_version,:options_hash,:status,:profile,:created_at)
                ON CONFLICT(file_id,cache_key) DO UPDATE SET
                  status=excluded.status,profile_json=excluded.profile_json,created_at=excluded.created_at
            """), {"id": str(uuid.uuid4()), "file_id": profile.file_id, "cache_key": cache_key,
                    "parser_version": profile.parser_version, "options_hash": options_hash,
                    "status": outcome.status, "profile": profile.model_dump_json(), "created_at": utc_now()})

    def file_detail(self, task_id: str, file_id: str) -> dict[str, Any]:
        file = self.get_file(task_id, file_id)
        with self.database.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT profile_json FROM file_profiles WHERE file_id=:file_id
                ORDER BY created_at DESC LIMIT 1
            """), {"file_id": file_id}).first()
            suggestion_row = connection.execute(text("""
                SELECT c.*,t.tree_hash FROM classifications c JOIN taxonomies t ON t.id=c.taxonomy_id
                WHERE c.task_id=:task AND c.file_id=:file AND t.status='approved' ORDER BY c.created_at DESC LIMIT 1
            """), {"task": task_id, "file": file_id}).mappings().first()
            review_row = connection.execute(text("""
                SELECT r.* FROM reviews r JOIN taxonomies t ON t.id=r.taxonomy_id
                WHERE r.task_id=:task AND r.file_id=:file AND t.status='approved' ORDER BY r.revision DESC LIMIT 1
            """), {"task": task_id, "file": file_id}).mappings().first()
        public_file = {key: file[key] for key in ("id", "task_id", "scope_id", "basename", "relative_path", "extension", "modality", "size_bytes", "mtime_ns", "scan_status", "exclusion_code", "metadata")}
        suggestion = None if not suggestion_row else {"file_id": file_id, "taxonomy_id": suggestion_row["taxonomy_id"], "category_id": suggestion_row["category_id"], "abstain": bool(suggestion_row["abstain"]), "model_score": suggestion_row["model_score"], "evidence_ids": json.loads(suggestion_row["evidence_refs_json"]), "reason": suggestion_row["reason"], "warnings": json.loads(suggestion_row["warnings_json"]), "source": suggestion_row["source"], "review_band": suggestion_row["review_band"]}
        review = None if not review_row else {"id": review_row["id"], "file_id": file_id, "taxonomy_id": review_row["taxonomy_id"], "category_id": review_row["category_id"], "decision": review_row["decision"], "note": review_row["note"], "revision": review_row["revision"]}
        return {"file": public_file, "profile": json.loads(row[0]) if row else None, "suggestion": suggestion, "latest_review": review}

    def list_scopes(self, task_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            return [dict(row) for row in connection.execute(text("SELECT * FROM task_scopes WHERE task_id=:task ORDER BY id"), {"task": task_id}).mappings()]

    def eligible_file_ids(self, task_id: str, scope_id: str) -> list[str]:
        with self.database.engine.connect() as connection:
            return [row[0] for row in connection.execute(text("SELECT id FROM files WHERE task_id=:task AND scope_id=:scope AND scan_status='eligible' ORDER BY id"), {"task": task_id, "scope": scope_id})]

    def events(self, task_id: str, after_seq: int, limit: int) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT seq,event_type,payload_json,created_at FROM task_events WHERE task_id=:id AND seq>:seq ORDER BY seq LIMIT :limit"),
                {"id": task_id, "seq": after_seq, "limit": limit},
            ).mappings()
            return [{"seq": row["seq"], "event_type": row["event_type"], "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]} for row in rows]

    def plan_inputs(self, task_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("""
              SELECT f.id AS file_id,f.scope_id,f.original_path,f.modality,f.scan_status,f.companion_group_id,
                     s.kind,s.source_root,s.destination_root,s.display_name
              FROM files f JOIN task_scopes s ON s.id=f.scope_id
              WHERE f.task_id=:id ORDER BY f.id
            """), {"id": task_id}).mappings()
            results = [dict(row) for row in rows]
            for item in results:
                taxonomy = connection.execute(text("""
                    SELECT id,tree_hash FROM taxonomies WHERE task_id=:task AND scope_id=:scope AND status='approved'
                    ORDER BY version DESC LIMIT 1
                """), {"task": task_id, "scope": item["scope_id"]}).mappings().first()
                item.update({"taxonomy_id": None, "taxonomy_hash": None, "category_id": None, "category_segments": None, "review_band": None, "manual_decision": None})
                if not taxonomy:
                    continue
                item["taxonomy_id"], item["taxonomy_hash"] = taxonomy["id"], taxonomy["tree_hash"]
                review = connection.execute(text("SELECT decision,category_id FROM reviews WHERE file_id=:file AND taxonomy_id=:taxonomy ORDER BY revision DESC LIMIT 1"), {"file": item["file_id"], "taxonomy": taxonomy["id"]}).mappings().first()
                classification = connection.execute(text("SELECT category_id,review_band,abstain FROM classifications WHERE file_id=:file AND taxonomy_id=:taxonomy ORDER BY attempt DESC LIMIT 1"), {"file": item["file_id"], "taxonomy": taxonomy["id"]}).mappings().first()
                if review:
                    item["manual_decision"] = review["decision"]
                    category_id = review["category_id"] if review["decision"] in {"accept", "change", "quarantine"} else None
                elif classification and classification["review_band"] == "high" and not classification["abstain"]:
                    category_id = classification["category_id"]; item["review_band"] = classification["review_band"]
                else:
                    category_id = None
                    if classification: item["review_band"] = classification["review_band"]
                if category_id:
                    category = connection.execute(text("SELECT category_id,path_segments_json FROM categories WHERE taxonomy_id=:taxonomy AND category_id=:category AND selectable=1"), {"taxonomy": taxonomy["id"], "category": category_id}).mappings().first()
                    if category:
                        item["category_id"] = category["category_id"]
                        item["category_segments"] = json.loads(category["path_segments_json"])
            return results

    def next_plan_version(self, task_id: str) -> int:
        with self.database.engine.connect() as connection:
            return int(connection.execute(
                text("SELECT COALESCE(MAX(version),0)+1 FROM plans WHERE task_id=:id"), {"id": task_id}
            ).scalar_one())

    def assert_revision(self, task_id: str, expected_revision: int) -> None:
        task = self.get(task_id)
        if task["revision"] != expected_revision:
            raise ValueError("REVISION_CONFLICT")

    def known_output_roots(self) -> tuple[Path, ...]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT DISTINCT destination_root FROM task_scopes
                WHERE destination_root <> source_root
            """))
            return tuple(Path(str(row[0])) for row in rows)

    def append_event(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> int:
        """Append one durable, monotonically sequenced task event."""
        with self.database.begin() as connection:
            if connection.execute(text("SELECT 1 FROM tasks WHERE id=:id"), {"id": task_id}).first() is None:
                raise KeyError(task_id)
            seq = int(connection.execute(
                text("SELECT COALESCE(MAX(seq),0)+1 FROM task_events WHERE task_id=:id"),
                {"id": task_id},
            ).scalar_one())
            connection.execute(
                text("INSERT INTO task_events(task_id,seq,event_type,payload_json,created_at) VALUES(:id,:seq,:event,:payload,:now)"),
                {"id": task_id, "seq": seq, "event": event_type,
                 "payload": canonical_json(payload or {}), "now": utc_now()},
            )
        return seq

    def transition_control(
        self,
        task_id: str,
        expected_revision: int,
        *,
        allowed_statuses: set[str],
        status: str,
        event_type: str,
        checkpoint_patch: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.begin() as connection:
            row = connection.execute(
                text("SELECT status,checkpoint_json FROM tasks WHERE id=:id AND revision=:revision"),
                {"id": task_id, "revision": expected_revision},
            ).mappings().first()
            if row is None:
                raise ValueError("REVISION_CONFLICT")
            if row["status"] not in allowed_statuses:
                raise ValueError("TASK_STATE_CONFLICT")
            checkpoint = json.loads(row["checkpoint_json"])
            checkpoint.update(checkpoint_patch or {})
            connection.execute(
                text("UPDATE tasks SET status=:status,revision=revision+1,checkpoint_json=:checkpoint,updated_at=:now WHERE id=:id"),
                {"id": task_id, "status": status, "checkpoint": canonical_json(checkpoint), "now": now},
            )
            seq = int(connection.execute(
                text("SELECT COALESCE(MAX(seq),0)+1 FROM task_events WHERE task_id=:id"), {"id": task_id}
            ).scalar_one())
            connection.execute(
                text("INSERT INTO task_events(task_id,seq,event_type,payload_json,created_at) VALUES(:id,:seq,:event,:payload,:now)"),
                {"id": task_id, "seq": seq, "event": event_type,
                 "payload": canonical_json(checkpoint_patch or {}), "now": now},
            )
        return self.get(task_id)

    def mark_interrupted_for_recovery(self) -> list[str]:
        """Convert only unfinished active work into an explicit recovery state at startup."""
        now = utc_now()
        with self.database.begin() as connection:
            ids = [str(row[0]) for row in connection.execute(
                text("SELECT id FROM tasks WHERE status IN ('RUNNING','PAUSE_REQUESTED') ORDER BY id")
            )]
            for task_id in ids:
                checkpoint = json.loads(connection.execute(
                    text("SELECT checkpoint_json FROM tasks WHERE id=:id"), {"id": task_id}
                ).scalar_one())
                checkpoint["recovery_reason"] = "previous_process_interrupted"
                connection.execute(
                    text("UPDATE tasks SET status='RECOVERY_REQUIRED',revision=revision+1,checkpoint_json=:checkpoint,updated_at=:now WHERE id=:id"),
                    {"id": task_id, "checkpoint": canonical_json(checkpoint), "now": now},
                )
                seq = int(connection.execute(
                    text("SELECT COALESCE(MAX(seq),0)+1 FROM task_events WHERE task_id=:id"), {"id": task_id}
                ).scalar_one())
                connection.execute(
                    text("INSERT INTO task_events(task_id,seq,event_type,payload_json,created_at) VALUES(:id,:seq,'recovery_required',:payload,:now)"),
                    {"id": task_id, "seq": seq,
                     "payload": canonical_json({"reason": "previous_process_interrupted"}), "now": now},
                )
        return ids

    def load_profile(self, file_id: str, cache_key: str) -> ParseOutcome | None:
        with self.database.engine.connect() as connection:
            row = connection.execute(
                text("SELECT status,profile_json FROM file_profiles WHERE file_id=:file AND cache_key=:key"),
                {"file": file_id, "key": cache_key},
            ).mappings().first()
            if row is None:
                row = connection.execute(
                    text("SELECT status,profile_json FROM file_profiles WHERE cache_key=:key ORDER BY created_at DESC LIMIT 1"),
                    {"key": cache_key},
                ).mappings().first()
        if row is None:
            return None
        from guixu.domain.profiles import FileProfile
        profile = FileProfile.model_validate_json(row["profile_json"]).model_copy(update={"file_id": file_id})
        return ParseOutcome(status=row["status"], profile=profile)

    def refresh_counters(self, task_id: str) -> dict[str, int]:
        with self.database.begin() as connection:
            file_counts = dict(connection.execute(text(
                "SELECT scan_status,count(*) FROM files WHERE task_id=:id GROUP BY scan_status"
            ), {"id": task_id}).all())
            class_counts = dict(connection.execute(text(
                "SELECT review_band,count(*) FROM classifications WHERE task_id=:id GROUP BY review_band"
            ), {"id": task_id}).all())
            op_counts = dict(connection.execute(text("""
                SELECT o.state,count(*) FROM operations o JOIN plans p ON p.id=o.plan_id
                WHERE p.task_id=:id AND p.plan_kind='forward' GROUP BY o.state
            """), {"id": task_id}).all())
            counters = {
                "discovered": sum(file_counts.values()),
                "eligible": file_counts.get("eligible", 0),
                "excluded": file_counts.get("excluded", 0),
                "profile_ready": int(connection.execute(text("""
                    SELECT count(DISTINCT fp.file_id) FROM file_profiles fp JOIN files f ON f.id=fp.file_id
                    WHERE f.task_id=:id AND fp.status='ready'
                """), {"id": task_id}).scalar_one()),
                "profile_partial": int(connection.execute(text("""
                    SELECT count(DISTINCT fp.file_id) FROM file_profiles fp JOIN files f ON f.id=fp.file_id
                    WHERE f.task_id=:id AND fp.status='partial'
                """), {"id": task_id}).scalar_one()),
                "suggested_high": class_counts.get("high", 0),
                "needs_review": class_counts.get("medium", 0) + class_counts.get("low", 0),
                "executed": op_counts.get("COMMITTED", 0),
                "conflict": op_counts.get("CONFLICT", 0),
            }
            connection.execute(text("UPDATE tasks SET counters_json=:counters,updated_at=:now WHERE id=:id"),
                               {"id": task_id, "counters": canonical_json(counters), "now": utc_now()})
        return counters
