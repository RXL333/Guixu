from __future__ import annotations

"""Durable compensation for an uncommitted first-plan refinement.

Core planning services commit several independent SQLite transactions while
calling a remote model.  Until the new Conversation PlanVersion is committed,
the old executable plan must survive every failure (including process exit).
The checkpoint lives in the existing AgentTurn ledger; it never touches disk
files or operation journal entries.
"""

import json
import uuid

from sqlalchemy import text

from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import canonical_json


_TASK_COLUMNS = (
    "status", "phase", "revision", "classification_request_json", "counters_json",
    "checkpoint_json", "last_error_code", "updated_at", "finished_at",
)
_CONTEXT_COLUMNS = (
    "context_revision", "current_taxonomy_id", "organization_intent_json",
    "confirmed_requirements_json", "updated_at",
)


def begin_pre_execution_replan(database: Database, conversation_id: str,
                               task_id: str, current_plan_version_id: str) -> str:
    turn_id = str(uuid.uuid4())
    with database.begin() as connection:
        context = connection.execute(text("SELECT * FROM conversation_contexts WHERE conversation_id=:id"),
                                     {"id": conversation_id}).mappings().one()
        if context["current_plan_version_id"] != current_plan_version_id or context["current_execution_round_id"]:
            raise ValueError("PLAN_VERSION_CONFLICT")
        active = connection.execute(text("""
            SELECT 1 FROM conversation_agent_turns
            WHERE conversation_id=:id AND turn_kind='REPLANNING' AND status='RUNNING'
            LIMIT 1
        """), {"id": conversation_id}).first()
        if active:
            raise ValueError("REPLAN_ALREADY_RUNNING")
        task = connection.execute(text("SELECT * FROM tasks WHERE id=:id"), {"id": task_id}).mappings().one()
        taxonomies = [dict(row) for row in connection.execute(text(
            "SELECT id,status,approved_at FROM taxonomies WHERE task_id=:id"
        ), {"id": task_id}).mappings()]
        plans = [dict(row) for row in connection.execute(text(
            "SELECT id,status FROM plans WHERE task_id=:id"
        ), {"id": task_id}).mappings()]
        approvals = [dict(row) for row in connection.execute(text(
            "SELECT id,status,superseded_at FROM conversation_plan_approvals WHERE conversation_id=:id"
        ), {"id": conversation_id}).mappings()]
        conversation_updated_at = connection.execute(text(
            "SELECT updated_at FROM conversations WHERE id=:id"
        ), {"id": conversation_id}).scalar_one()
        checkpoint = {
            "kind": "pre_execution_replan_v1",
            "task_id": task_id,
            "current_plan_version_id": current_plan_version_id,
            "task": {key: task[key] for key in _TASK_COLUMNS},
            "context": {key: context[key] for key in _CONTEXT_COLUMNS},
            "conversation_updated_at": conversation_updated_at,
            "taxonomies": taxonomies,
            "plans": plans,
            "approvals": approvals,
        }
        now = utc_now()
        connection.execute(text("""
            INSERT INTO conversation_agent_turns(
              id,conversation_id,task_id,plan_version_id,turn_kind,status,
              checkpoint_json,created_at,started_at,last_heartbeat_at
            ) VALUES(:id,:conversation,:task,:plan,'REPLANNING','RUNNING',:checkpoint,:now,:now,:now)
        """), {"id": turn_id, "conversation": conversation_id, "task": task_id,
               "plan": current_plan_version_id, "checkpoint": canonical_json(checkpoint), "now": now})
    return turn_id


def rollback_pre_execution_replan(database: Database, turn_id: str, *, interrupted: bool = False) -> bool:
    """Restore the old plan's backing Task state, preserving failed-attempt audit rows."""
    with database.begin() as connection:
        turn = connection.execute(text("SELECT * FROM conversation_agent_turns WHERE id=:id"),
                                  {"id": turn_id}).mappings().one()
        if turn["status"] != "RUNNING":
            return False
        snapshot = json.loads(turn["checkpoint_json"])
        if snapshot.get("kind") != "pre_execution_replan_v1":
            raise ValueError("REPLAN_CHECKPOINT_INVALID")
        conversation_id = str(turn["conversation_id"])
        context = connection.execute(text(
            "SELECT current_plan_version_id,current_execution_round_id FROM conversation_contexts WHERE conversation_id=:id"
        ), {"id": conversation_id}).mappings().one()
        if context["current_plan_version_id"] != snapshot["current_plan_version_id"] or context["current_execution_round_id"]:
            raise ValueError("REPLAN_ROLLBACK_CONFLICT")
        task_id = snapshot["task_id"]
        task = snapshot["task"]
        connection.execute(text("""
            UPDATE tasks SET status=:status,phase=:phase,revision=:revision,
              classification_request_json=:classification_request_json,counters_json=:counters_json,
              checkpoint_json=:checkpoint_json,last_error_code=:last_error_code,
              updated_at=:updated_at,finished_at=:finished_at WHERE id=:id
        """), {**task, "id": task_id})

        old_taxonomies = {row["id"]: row for row in snapshot["taxonomies"]}
        taxonomy_rows = connection.execute(text("SELECT id FROM taxonomies WHERE task_id=:id"),
                                           {"id": task_id}).mappings().all()
        for row in taxonomy_rows:
            old = old_taxonomies.get(row["id"])
            connection.execute(text("""
                UPDATE taxonomies SET status=:status,approved_at=:approved WHERE id=:id
            """), {"id": row["id"], "status": old["status"] if old else "superseded",
                   "approved": old["approved_at"] if old else None})

        old_plans = {row["id"]: row for row in snapshot["plans"]}
        plan_rows = connection.execute(text("SELECT id FROM plans WHERE task_id=:id"),
                                       {"id": task_id}).mappings().all()
        for row in plan_rows:
            old = old_plans.get(row["id"])
            connection.execute(text("UPDATE plans SET status=:status WHERE id=:id"),
                               {"id": row["id"], "status": old["status"] if old else "superseded"})

        prior = snapshot["context"]
        connection.execute(text("""
            UPDATE conversation_contexts SET context_revision=:context_revision,
              current_taxonomy_id=:current_taxonomy_id,
              organization_intent_json=:organization_intent_json,
              confirmed_requirements_json=:confirmed_requirements_json,updated_at=:updated_at
            WHERE conversation_id=:id
        """), {**prior, "id": conversation_id})
        connection.execute(text("UPDATE conversations SET updated_at=:updated WHERE id=:id"),
                           {"updated": snapshot["conversation_updated_at"], "id": conversation_id})
        for row in snapshot["approvals"]:
            connection.execute(text("""
                UPDATE conversation_plan_approvals SET status=:status,superseded_at=:superseded_at
                WHERE id=:id
            """), row)
        connection.execute(text("""
            UPDATE conversation_agent_turns SET status=:status,interruption_code=:code,
              checkpoint_json='{}',completed_at=:now WHERE id=:id
        """), {"id": turn_id, "status": "INTERRUPTED" if interrupted else "FAILED",
               "code": "REPLAN_INTERRUPTED_ROLLED_BACK" if interrupted else "REPLAN_FAILED_ROLLED_BACK",
               "now": utc_now()})
    return True


def recover_interrupted_pre_execution_replans(database: Database) -> int:
    with database.engine.connect() as connection:
        ids = [str(row[0]) for row in connection.execute(text("""
            SELECT id FROM conversation_agent_turns
            WHERE turn_kind='REPLANNING' AND status='RUNNING'
              AND json_extract(checkpoint_json,'$.kind')='pre_execution_replan_v1'
        """))]
    return sum(rollback_pre_execution_replan(database, turn_id, interrupted=True) for turn_id in ids)
