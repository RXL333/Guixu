from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import text

from guixu.domain.plans import ExecutionPlan, PlannedOperation, SourceIdentity
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import canonical_json


FINAL_STATES = {"COMMITTED", "SKIPPED", "FAILED", "CONFLICT", "UNDONE", "UNDO_CONFLICT"}


class SqliteOperationJournal:
    """The operation row and its event are committed atomically before/after disk actions."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def persist_plan(self, plan: ExecutionPlan) -> None:
        summary = {
            "total": len(plan.operations),
            "move": sum(item.action == "move" for item in plan.operations),
            "copy": sum(item.action == "copy" for item in plan.operations),
            "skip": sum(item.action in {"skip", "noop"} for item in plan.operations),
        }
        with self.database.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO plans(
                  id,task_id,version,plan_hash,plan_kind,parent_plan_id,status,operation_mode,
                  settings_hash,taxonomy_hashes_json,source_snapshot_hash,summary_json,created_at
                ) VALUES(:id,:task,:version,:hash,:kind,:parent,'validated',:mode,:settings,:taxonomies,:snapshot,:summary,:now)
                """),
                {
                    "id": plan.plan_id, "task": plan.task_id, "version": plan.version,
                    "hash": plan.plan_hash, "kind": plan.plan_kind, "parent": plan.parent_plan_id,
                    "mode": plan.operation_mode, "settings": plan.settings_hash,
                    "taxonomies": canonical_json(plan.taxonomy_hashes), "snapshot": plan.source_snapshot_hash,
                    "summary": canonical_json(summary), "now": utc_now(),
                },
            )
            for operation in plan.operations:
                connection.execute(
                    text("""
                    INSERT INTO operations(
                      id,plan_id,file_id,ordinal,action,source_path,target_path,target_key,
                      source_snapshot_json,expected_sha256,state,reverses_operation_id,
                      companion_group_id,updated_at
                    ) VALUES(:id,:plan,:file,:ordinal,:action,:source,:target,:target_key,
                      :snapshot,:sha,'PLANNED',:reverses,:group_id,:now)
                    """),
                    {
                        "id": operation.operation_id, "plan": plan.plan_id, "file": operation.file_id,
                        "ordinal": operation.ordinal, "action": operation.action,
                        "source": operation.source_path, "target": operation.target_path,
                        "target_key": operation.target_key,
                        "snapshot": canonical_json(asdict(operation.source_identity)),
                        "sha": operation.expected_sha256,
                        "reverses": operation.reverses_operation_id,
                        "group_id": operation.companion_group_id, "now": utc_now(),
                    },
                )

    def approve(self, plan_id: str, plan_hash: str, authorization_kind: str = "interactive") -> None:
        with self.database.begin() as connection:
            existing = connection.execute(
                text("SELECT plan_hash,status FROM plans WHERE id=:id"), {"id": plan_id}
            ).first()
            if (
                existing is not None
                and existing[0] == plan_hash
                and existing[1] in {"approved", "executing", "finished"}
            ):
                # Retrying the exact, already-authorized immutable plan is safe. This
                # lets the UI recover when approval succeeded but the following request
                # was interrupted, without weakening hash or plan-state validation.
                return
            result = connection.execute(
                text("""
                UPDATE plans SET status='approved',approved_at=:now,authorization_kind=:kind,
                  authorization_json=:auth WHERE id=:id AND plan_hash=:hash AND status='validated'
                """),
                {"id": plan_id, "hash": plan_hash, "now": utc_now(), "kind": authorization_kind,
                 "auth": canonical_json({"approved_hash": plan_hash})},
            )
            if result.rowcount != 1:
                raise ValueError("PLAN_STALE")

    def approved_hash(self, plan_id: str) -> str | None:
        with self.database.engine.connect() as connection:
            row = connection.execute(
                text("SELECT plan_hash FROM plans WHERE id=:id AND status IN ('approved','executing','finished')"),
                {"id": plan_id},
            ).first()
        return row[0] if row else None

    def begin_execution(self, plan_id: str) -> None:
        with self.database.begin() as connection:
            row = connection.execute(text("SELECT task_id,status FROM plans WHERE id=:id"), {"id": plan_id}).first()
            if row is None or row[1] not in {"approved", "executing", "finished"}:
                raise ValueError("PLAN_NOT_APPROVED")
            if row[1] == "finished":
                return
            connection.execute(text("UPDATE plans SET status='executing' WHERE id=:id"), {"id": plan_id})
            connection.execute(
                text("UPDATE tasks SET status='RUNNING',phase=:phase,revision=revision+1,updated_at=:now WHERE id=:id"),
                {"id": row[0], "phase": "UNDO" if self._plan_kind(connection, plan_id) == "undo" else "EXECUTE", "now": utc_now()},
            )

    @staticmethod
    def _plan_kind(connection, plan_id: str) -> str:
        return str(connection.execute(text("SELECT plan_kind FROM plans WHERE id=:id"), {"id": plan_id}).scalar_one())

    def state(self, operation_id: str) -> str:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT state FROM operations WHERE id=:id"), {"id": operation_id}).first()
        if row is None:
            raise KeyError(operation_id)
        return str(row[0])

    def transition(self, operation: PlannedOperation, state: str, payload: dict[str, object] | None = None) -> None:
        now = utc_now()
        payload = payload or {}
        with self.database.begin() as connection:
            current = connection.execute(
                text("SELECT state FROM operations WHERE id=:id"), {"id": operation.operation_id}
            ).scalar_one()
            if current in FINAL_STATES and current != state:
                return
            seq = connection.execute(
                text("SELECT COALESCE(MAX(seq),0)+1 FROM operation_events WHERE operation_id=:id"),
                {"id": operation.operation_id},
            ).scalar_one()
            connection.execute(
                text("""
                UPDATE operations SET state=:state,temp_path=COALESCE(:temp,temp_path),
                  error_code=COALESCE(:error,error_code),updated_at=:now WHERE id=:id
                """),
                {"id": operation.operation_id, "state": state, "temp": payload.get("temp_path"),
                 "error": payload.get("code"), "now": now},
            )
            if state in {"COMMITTED", "UNDONE"} and operation.action == "move" and operation.target_path:
                connection.execute(
                    text("UPDATE files SET current_path=:path,path_key=:key,updated_at=:now WHERE id=:id"),
                    {"id": operation.file_id, "path": operation.target_path,
                     "key": operation.target_path.casefold(), "now": now},
                )
            connection.execute(
                text("""
                INSERT INTO operation_events(operation_id,seq,event_type,payload_json,created_at)
                VALUES(:id,:seq,:event,:payload,:now)
                """),
                {"id": operation.operation_id, "seq": seq, "event": state,
                 "payload": canonical_json(payload), "now": now},
            )
            task_id = connection.execute(text("""
                SELECT p.task_id FROM plans p JOIN operations o ON o.plan_id=p.id WHERE o.id=:id
            """), {"id": operation.operation_id}).scalar_one()
            task_seq = connection.execute(
                text("SELECT COALESCE(MAX(seq),0)+1 FROM task_events WHERE task_id=:task"), {"task": task_id}
            ).scalar_one()
            connection.execute(text("""
                INSERT INTO task_events(task_id,seq,event_type,payload_json,created_at)
                VALUES(:task,:seq,'operation_checkpoint',:payload,:now)
            """), {"task": task_id, "seq": task_seq,
                    "payload": canonical_json({"operation_id": operation.operation_id, "ordinal": operation.ordinal, "state": state}),
                    "now": now})

    def record_directory(self, plan_id: str, path: Path) -> None:
        with self.database.begin() as connection:
            connection.execute(
                text("""
                INSERT OR IGNORE INTO created_directories(
                  id,plan_id,path,path_key,created_by_task,removed,created_at
                ) VALUES(:id,:plan,:path,:key,1,0,:now)
                """),
                {"id": str(uuid.uuid4()), "plan": plan_id, "path": str(path),
                 "key": str(path).casefold(), "now": utc_now()},
            )

    def finish_plan(self, plan_id: str) -> None:
        with self.database.begin() as connection:
            unfinished = connection.execute(
                text("SELECT count(*) FROM operations WHERE plan_id=:id AND state NOT IN ('COMMITTED','SKIPPED','UNDONE')"),
                {"id": plan_id},
            ).scalar_one()
            connection.execute(
                text("UPDATE plans SET status=:status WHERE id=:id"),
                {"id": plan_id, "status": "finished" if unfinished == 0 else "executing"},
            )
            plan = connection.execute(text("SELECT task_id,plan_kind FROM plans WHERE id=:id"), {"id": plan_id}).first()
            if plan:
                status = "COMPLETED" if unfinished == 0 else "COMPLETED_WITH_ISSUES"
                connection.execute(
                    text("UPDATE tasks SET status=:status,phase='REPORT',revision=revision+1,updated_at=:now,finished_at=:now WHERE id=:id"),
                    {"id": plan[0], "status": status, "now": utc_now()},
                )

    def completed_operation_ids(self, plan_id: str) -> set[str]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id FROM operations WHERE plan_id=:id AND state='COMMITTED'"), {"id": plan_id}
            )
            return {str(row[0]) for row in rows}

    def load_plan(self, plan_id: str) -> ExecutionPlan:
        with self.database.engine.connect() as connection:
            plan = connection.execute(text("SELECT * FROM plans WHERE id=:id"), {"id": plan_id}).mappings().first()
            if plan is None:
                raise KeyError(plan_id)
            rows = connection.execute(
                text("SELECT * FROM operations WHERE plan_id=:id ORDER BY ordinal"), {"id": plan_id}
            ).mappings().all()
        operations = []
        for row in rows:
            identity = SourceIdentity(**json.loads(row["source_snapshot_json"]))
            operations.append(PlannedOperation(
                operation_id=row["id"], file_id=row["file_id"], ordinal=row["ordinal"], action=row["action"],
                source_path=row["source_path"], target_path=row["target_path"], target_key=row["target_key"],
                source_identity=identity, expected_sha256=row["expected_sha256"] or identity.sha256,
                companion_group_id=row["companion_group_id"], reverses_operation_id=row["reverses_operation_id"],
            ))
        return ExecutionPlan(
            plan_id=plan["id"], task_id=plan["task_id"], version=plan["version"],
            operation_mode=plan["operation_mode"], settings_hash=plan["settings_hash"],
            taxonomy_hashes=tuple(json.loads(plan["taxonomy_hashes_json"])),
            source_snapshot_hash=plan["source_snapshot_hash"], plan_hash=plan["plan_hash"],
            operations=tuple(operations), plan_kind=plan["plan_kind"], parent_plan_id=plan["parent_plan_id"],
        )
