from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from sqlalchemy import text

from guixu.domain.classification import ClassificationError, review_band, validate_result
from guixu.domain.profiles import FileProfile
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import canonical_json


class ClassificationService:
    def __init__(self, database: Database, result_schema_path: Path) -> None:
        self.database = database
        self.validator = Draft202012Validator(json.loads(result_schema_path.read_text("utf-8")), format_checker=FormatChecker())

    def classify(self, *, task_id: str, file_id: str, taxonomy: dict[str, Any], profile: FileProfile,
                 model_callback: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
        context = self._file_context(task_id, file_id, profile)
        input_hash = self._input_hash(task_id, context, taxonomy)
        cached = self._cached(file_id, taxonomy["taxonomy_id"], input_hash)
        if cached is not None:
            return cached
        if model_callback is None:
            raise ClassificationError("MODEL_UNAVAILABLE")
        payload = {"file_id": file_id, "taxonomy_id": taxonomy["taxonomy_id"], "profile": profile.model_dump(mode="json"),
                   "allowed_selectable_categories": [node for node in taxonomy["nodes"] if node["selectable"]]}
        result = model_callback(payload); source = "ai"; band = review_band(result, profile)
        try:
            self.validator.validate(result)
        except ValidationError as exc:
            raise ClassificationError("CLASSIFICATION_SCHEMA_INVALID") from exc
        validate_result(result, file_id=file_id, taxonomy=taxonomy, profile=profile)
        self._persist(task_id, file_id, taxonomy["taxonomy_id"], result, source, band, input_hash)
        return {**result, "source": source, "review_band": band, "needs_review": band != "high"}

    def review_bulk(self, task_id: str, reviews: list[dict[str, Any]], expected_revision: int) -> dict[str, Any]:
        if not 1 <= len(reviews) <= 500:
            raise ClassificationError("REVIEW_COUNT_INVALID")
        saved = []
        with self.database.begin() as connection:
            invalidated = [row[0] for row in connection.execute(text("SELECT id FROM plans WHERE task_id=:task AND status IN ('draft','validated','approved')"), {"task": task_id})]
            changed = connection.execute(text("UPDATE tasks SET revision=revision+1,updated_at=:now WHERE id=:task AND revision=:revision"), {"task": task_id, "revision": expected_revision, "now": utc_now()})
            if changed.rowcount != 1:
                raise ClassificationError("REVISION_CONFLICT")
            for review in reviews:
                row = connection.execute(text("""
                    SELECT f.scope_id,t.status,c.selectable FROM files f
                    JOIN taxonomies t ON t.id=:taxonomy AND t.task_id=f.task_id AND t.scope_id=f.scope_id
                    LEFT JOIN categories c ON c.taxonomy_id=t.id AND c.category_id=:category
                    WHERE f.task_id=:task AND f.id=:file
                """), {"taxonomy": review["taxonomy_id"], "category": review.get("category_id"), "task": task_id, "file": review["file_id"]}).mappings().first()
                if row is None or row["status"] != "approved":
                    raise ClassificationError("SCOPE_CONFLICT")
                if review["decision"] != "skip" and row["selectable"] != 1:
                    raise ClassificationError("CATEGORY_NOT_ALLOWED")
                revision = int(connection.execute(text("SELECT COALESCE(MAX(revision),0)+1 FROM reviews WHERE file_id=:file"), {"file": review["file_id"]}).scalar_one())
                review_id = str(uuid.uuid4()); now = utc_now()
                connection.execute(text("""
                    INSERT INTO reviews(id,task_id,file_id,taxonomy_id,category_id,decision,revision,note,created_at)
                    VALUES(:id,:task,:file,:taxonomy,:category,:decision,:revision,:note,:now)
                """), {"id": review_id, "task": task_id, "file": review["file_id"], "taxonomy": review["taxonomy_id"],
                        "category": review.get("category_id"), "decision": review["decision"], "revision": revision,
                        "note": review.get("note", ""), "now": now})
                saved.append({**review, "id": review_id, "revision": revision})
            connection.execute(text("UPDATE plans SET status='superseded' WHERE task_id=:task AND status IN ('draft','validated','approved')"), {"task": task_id})
        return {"items": saved, "applied": len(saved), "new_revision": expected_revision + 1, "invalidated_plan_ids": invalidated}

    def _file_context(self, task_id: str, file_id: str, profile: FileProfile) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT scope_id,basename,extension,relative_path,modality,size_bytes,mtime_ns,mime FROM files WHERE task_id=:task AND id=:file"), {"task": task_id, "file": file_id}).mappings().first()
        if row is None:
            raise KeyError(file_id)
        return {**dict(row), "profile": profile.model_dump(mode="python")}

    def _input_hash(self, task_id: str, context: dict[str, Any], taxonomy: dict[str, Any]) -> str:
        with self.database.engine.connect() as connection:
            task = connection.execute(text("SELECT model_snapshot_json FROM tasks WHERE id=:task"), {"task": task_id}).scalar_one()
            consents = [dict(row) for row in connection.execute(text("""
                SELECT provider_profile_id,scope_hash,grant_json FROM privacy_consents
                WHERE task_id=:task AND revoked_at IS NULL ORDER BY id
            """), {"task": task_id}).mappings()]
        payload = {
            "file_context": context,
            "taxonomy_id": taxonomy.get("taxonomy_id"),
            "taxonomy_version": taxonomy.get("version"),
            "taxonomy_hash": taxonomy.get("tree_hash"),
            "policy": taxonomy.get("policy", {}),
            "model_snapshot": json.loads(task),
            "privacy": [{**row, "grant_json": json.loads(row["grant_json"])} for row in consents],
            "prompt_version": "classification-v1",
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def _cached(self, file_id: str, taxonomy_id: str, input_hash: str) -> dict[str, Any] | None:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("""
                SELECT category_id,abstain,model_score,evidence_refs_json,reason,warnings_json,review_band
                FROM classifications WHERE file_id=:file AND taxonomy_id=:taxonomy AND input_hash=:hash
                ORDER BY attempt DESC LIMIT 1
            """), {"file": file_id, "taxonomy": taxonomy_id, "hash": input_hash}).mappings().first()
        if row is None:
            return None
        return {
            "file_id": file_id, "taxonomy_id": taxonomy_id, "category_id": row["category_id"],
            "abstain": bool(row["abstain"]), "model_score": row["model_score"],
            "evidence_ids": json.loads(row["evidence_refs_json"]), "reason": row["reason"],
            "tags": [], "warnings": json.loads(row["warnings_json"]), "source": "cache",
            "review_band": row["review_band"], "needs_review": row["review_band"] != "high",
        }

    def _persist(self, task_id: str, file_id: str, taxonomy_id: str, result: dict[str, Any], source: str, band: str, input_hash: str) -> None:
        with self.database.begin() as connection:
            attempt = int(connection.execute(text("SELECT COALESCE(MAX(attempt),0)+1 FROM classifications WHERE file_id=:file AND taxonomy_id=:taxonomy"), {"file": file_id, "taxonomy": taxonomy_id}).scalar_one())
            connection.execute(text("""
                INSERT INTO classifications(id,task_id,file_id,taxonomy_id,category_id,attempt,source,model_score,review_band,abstain,reason,evidence_refs_json,warnings_json,input_hash,created_at)
                VALUES(:id,:task,:file,:taxonomy,:category,:attempt,:source,:score,:band,:abstain,:reason,:evidence,:warnings,:hash,:now)
            """), {"id": str(uuid.uuid4()), "task": task_id, "file": file_id, "taxonomy": taxonomy_id,
                    "category": result["category_id"], "attempt": attempt, "source": source, "score": result["model_score"],
                    "band": band, "abstain": int(result["abstain"]), "reason": result["reason"],
                    "evidence": canonical_json(result["evidence_ids"]), "warnings": canonical_json(result["warnings"]),
                    "hash": input_hash, "now": utc_now()})
