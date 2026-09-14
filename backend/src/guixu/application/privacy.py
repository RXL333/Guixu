from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from guixu.domain.privacy import ALLOWED_DATA_TYPES, PrivacyError, scope_hash
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import canonical_json


class PrivacyService:
    def __init__(self, database: Database) -> None: self.database = database

    def grant(self, task_id: str, profile_id: str, data_types: list[str], budget: dict[str, Any], supplied_scope_hash: str,
              expected_revision: int, acknowledge: bool) -> dict[str, Any]:
        if not acknowledge or not set(data_types) <= ALLOWED_DATA_TYPES or len(data_types) != len(set(data_types)):
            raise PrivacyError("PRIVACY_CONSENT_REQUIRED")
        actual = scope_hash(profile_id, data_types, budget)
        if actual != supplied_scope_hash: raise PrivacyError("CONSENT_SCOPE_CHANGED")
        consent_id = str(uuid.uuid4()); now = utc_now()
        grant = {"data_types": sorted(data_types), "budget": budget}
        with self.database.begin() as connection:
            model = connection.execute(text("SELECT enabled FROM model_profiles WHERE id=:id"), {"id": profile_id}).first()
            if model is None or not model[0]: raise PrivacyError("MODEL_UNAVAILABLE")
            changed = connection.execute(text("UPDATE tasks SET revision=revision+1,updated_at=:now WHERE id=:task AND revision=:revision"), {"now": now, "task": task_id, "revision": expected_revision})
            if changed.rowcount != 1: raise PrivacyError("REVISION_CONFLICT")
            connection.execute(text("INSERT INTO privacy_consents(id,task_id,provider_profile_id,scope_hash,grant_json,granted_at) VALUES(:id,:task,:profile,:hash,:grant,:now)"),
                               {"id": consent_id, "task": task_id, "profile": profile_id, "hash": actual, "grant": canonical_json(grant), "now": now})
        return {"id": consent_id, "provider_profile_id": profile_id, "scope_hash": actual, "data_types": sorted(data_types), "granted_at": now, "revoked_at": None}

    def revoke(self, task_id: str, consent_id: str, expected_revision: int) -> dict[str, bool]:
        with self.database.begin() as connection:
            task = connection.execute(text("UPDATE tasks SET revision=revision+1,updated_at=:now WHERE id=:task AND revision=:revision"), {"now": utc_now(), "task": task_id, "revision": expected_revision})
            if task.rowcount != 1: raise PrivacyError("REVISION_CONFLICT")
            changed = connection.execute(text("UPDATE privacy_consents SET revoked_at=COALESCE(revoked_at,:now) WHERE id=:id AND task_id=:task"), {"now": utc_now(), "id": consent_id, "task": task_id})
            if changed.rowcount != 1: raise KeyError(consent_id)
        return {"revoked": True}

    def require(self, task_id: str, profile_id: str, requested_types: set[str]) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("SELECT grant_json,scope_hash FROM privacy_consents WHERE task_id=:task AND provider_profile_id=:profile AND revoked_at IS NULL ORDER BY granted_at DESC"), {"task": task_id, "profile": profile_id}).mappings().all()
        for row in rows:
            grant = json.loads(row["grant_json"])
            if requested_types <= set(grant["data_types"]): return {**grant, "scope_hash": row["scope_hash"]}
        raise PrivacyError("PRIVACY_CONSENT_REQUIRED")

    def usage(self, task_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT COUNT(*),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),SUM(estimated_cost_micros) FROM model_calls WHERE task_id=:task"), {"task": task_id}).first()
        return {"calls": row[0], "input_tokens": row[1], "output_tokens": row[2], "estimated_cost_micros": row[3], "cost_known": row[3] is not None}
