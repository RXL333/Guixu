"""Unified local evidence cache used by parsers and semantic model flows.

The cache stores evidence, never classification decisions.  Rows are keyed by a
stable tracked file id and the SHA-256 content fingerprint; paths are metadata
only.  This module deliberately contains no provider calls or filesystem writes
other than the caller's explicit fingerprint calculation.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import text

from guixu.domain.profiles import FileProfile
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.filesystem.identity import sha256_file


LOGGER = logging.getLogger(__name__)

EVIDENCE_KINDS = {
    "METADATA", "TEXT_EXTRACT", "OCR_TEXT", "VISUAL_DESCRIPTION", "DOCUMENT_SUMMARY",
    "AUDIO_TRANSCRIPT", "AUDIO_SUMMARY", "VIDEO_FRAME_DESCRIPTION", "VIDEO_TRANSCRIPT",
    "VIDEO_SUMMARY", "COMBINED_CONTENT_SUMMARY", "USER_CONTEXT",
}

LEGACY_KIND_MAP = {
    "metadata": "METADATA",
    "extracted_text": "TEXT_EXTRACT",
    "ocr": "OCR_TEXT",
    "visual_caption": "VISUAL_DESCRIPTION",
    "visual_description": "VISUAL_DESCRIPTION",
    "transcript": "AUDIO_TRANSCRIPT",
    "subtitle": "VIDEO_TRANSCRIPT",
    "document_summary": "DOCUMENT_SUMMARY",
    "audio_summary": "AUDIO_SUMMARY",
    "video_frame_description": "VIDEO_FRAME_DESCRIPTION",
    "video_transcript": "VIDEO_TRANSCRIPT",
    "video_summary": "VIDEO_SUMMARY",
    "combined_content_summary": "COMBINED_CONTENT_SUMMARY",
    "user_context": "USER_CONTEXT",
}


def normalize_evidence_kind(kind: str) -> str:
    normalized = LEGACY_KIND_MAP.get(str(kind).strip().lower(), str(kind).strip().upper())
    if normalized not in EVIDENCE_KINDS:
        raise ValueError("EVIDENCE_KIND_INVALID")
    return normalized


def fingerprint_for_path(path: Path) -> str:
    return sha256_file(path)


class EvidenceCacheService:
    """Canonical evidence lookup and lifecycle service.

    Counters are intentionally process-local observability counters. Durable
    evidence and invalidation provenance live in SQLite, so a restart still
    preserves reuse while counters start a fresh application session.
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        self._counters = {"cache_hit": 0, "cache_miss": 0, "cache_refresh": 0,
                          "evidence_reused": 0, "vision_calls_saved": 0,
                          "ocr_calls_saved": 0, "asr_calls_saved": 0}
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    @contextmanager
    def single_flight(self, file_id: str, fingerprint: str, evidence_kind: str) -> Iterator[None]:
        key = f"{file_id}:{fingerprint}:{normalize_evidence_kind(evidence_kind)}"
        with self._locks_guard:
            lock = self._locks.setdefault(key, threading.Lock())
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def invalidate_file_evidence(self, file_id: str, current_fingerprint: str, *, reason: str = "CONTENT_CHANGED") -> int:
        now = utc_now()
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE file_evidence
                   SET state='INVALID', invalidated_at=:now, invalidation_reason=:reason
                 WHERE file_id=:file AND content_fingerprint<>:fingerprint
                   AND state IN ('VALID','STALE','REFRESHING')
            """), {"file": file_id, "fingerprint": current_fingerprint, "now": now, "reason": reason})
        if result.rowcount:
            LOGGER.info("CACHE_INVALID file_id=%s count=%s reason=%s", file_id, result.rowcount, reason)
        return int(result.rowcount or 0)

    def get_valid_evidence(self, file_id: str, fingerprint: str, evidence_kind: str, *,
                           schema_version: int = 1, producer_name: str | None = None,
                           producer_version: str | None = None, prompt_version: str | None = None,
                           touch: bool = True) -> dict[str, Any] | None:
        kind = normalize_evidence_kind(evidence_kind)
        clauses = ["file_id=:file", "content_fingerprint=:fingerprint", "evidence_kind=:kind",
                   "evidence_schema_version=:schema", "state='VALID'"]
        params: dict[str, Any] = {"file": file_id, "fingerprint": fingerprint, "kind": kind, "schema": schema_version}
        if producer_name is not None:
            clauses.append("producer_name=:producer_name"); params["producer_name"] = producer_name
        if producer_version is not None:
            clauses.append("producer_version=:producer_version"); params["producer_version"] = producer_version
        if prompt_version is not None:
            clauses.append("prompt_version=:prompt_version"); params["prompt_version"] = prompt_version
        with self.database.engine.connect() as connection:
            row = connection.execute(text(f"""
                SELECT * FROM file_evidence
                 WHERE {' AND '.join(clauses)}
                 ORDER BY created_at DESC LIMIT 1
            """), params).mappings().first()
        if row is None:
            self._counters["cache_miss"] += 1
            LOGGER.info("CACHE_MISS file_id=%s kind=%s", file_id, kind)
            return None
        result = self._public(row)
        if touch:
            with self.database.begin() as connection:
                connection.execute(text("UPDATE file_evidence SET last_used_at=:now WHERE id=:id"), {"now": utc_now(), "id": row["id"]})
        self._counters["cache_hit"] += 1
        self._counters["evidence_reused"] += 1
        if kind == "VISUAL_DESCRIPTION":
            self._counters["vision_calls_saved"] += 1
        elif kind == "OCR_TEXT":
            self._counters["ocr_calls_saved"] += 1
        elif kind in {"AUDIO_TRANSCRIPT", "VIDEO_TRANSCRIPT"}:
            self._counters["asr_calls_saved"] += 1
        LOGGER.info("CACHE_HIT file_id=%s kind=%s evidence_id=%s", file_id, kind, row["id"])
        return result

    def get_evidence_by_kind(self, file_id: str, fingerprint: str, evidence_kind: str, *,
                             schema_version: int = 1) -> list[dict[str, Any]]:
        kind = normalize_evidence_kind(evidence_kind)
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT * FROM file_evidence
                 WHERE file_id=:file AND content_fingerprint=:fingerprint
                   AND evidence_kind=:kind AND evidence_schema_version=:schema
                 ORDER BY created_at DESC
            """), {"file": file_id, "fingerprint": fingerprint, "kind": kind, "schema": schema_version}).mappings()
            return [self._public(row) for row in rows]

    def store_evidence(self, *, file_id: str, content_fingerprint: str, evidence_kind: str,
                       payload: dict[str, Any] | list[Any] | str, normalized_content: str | None = None,
                       schema_version: int = 1, producer_type: str, producer_name: str,
                       producer_version: str = "unknown", model_profile_id: str | None = None,
                       model_id: str | None = None, prompt_version: str | None = None,
                       quality: str | None = None, completeness: dict[str, Any] | None = None,
                       state: str = "VALID", error_code: str | None = None) -> dict[str, Any]:
        kind = normalize_evidence_kind(evidence_kind)
        if len(content_fingerprint) != 64:
            raise ValueError("FINGERPRINT_INVALID")
        if producer_type not in {"LOCAL_PARSER", "LOCAL_OCR", "LOCAL_MEDIA", "CLOUD_MODEL", "LOCAL_MODEL", "USER", "LEGACY"}:
            raise ValueError("EVIDENCE_PRODUCER_INVALID")
        if quality is not None and quality not in {"high", "medium", "low"}:
            raise ValueError("EVIDENCE_QUALITY_INVALID")
        payload_value = payload if isinstance(payload, (dict, list)) else {"text": str(payload)}
        encoded = json.dumps(payload_value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        params = {"file": file_id, "fingerprint": content_fingerprint, "kind": kind, "schema": schema_version,
                  "producer_name": producer_name, "producer_version": producer_version,
                  "model_id": model_id, "prompt_version": prompt_version}
        with self.database.engine.connect() as connection:
            existing = connection.execute(text("""
                SELECT * FROM file_evidence
                 WHERE file_id=:file AND content_fingerprint=:fingerprint AND evidence_kind=:kind
                   AND evidence_schema_version=:schema AND producer_name=:producer_name
                   AND producer_version=:producer_version
                   AND COALESCE(model_id,'')=COALESCE(:model_id,'')
                   AND COALESCE(prompt_version,'')=COALESCE(:prompt_version,'')
                   AND state='VALID'
                 ORDER BY created_at DESC LIMIT 1
            """), params).mappings().first()
        if existing is not None and state == "VALID":
            with self.database.begin() as connection:
                connection.execute(text("UPDATE file_evidence SET last_used_at=:now WHERE id=:id"), {"now": utc_now(), "id": existing["id"]})
            return self._public(existing)
        evidence_id = str(uuid.uuid4())
        now = utc_now()
        with self.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO file_evidence(
                  id,file_id,content_fingerprint,evidence_kind,evidence_schema_version,payload_json,
                  normalized_content,state,producer_type,producer_name,producer_version,model_profile_id,
                  model_id,prompt_version,quality,completeness_json,created_at,last_used_at,error_code
                ) VALUES(:id,:file,:fingerprint,:kind,:schema,:payload,:content,:state,:producer_type,:producer_name,
                  :producer_version,:model_profile_id,:model_id,:prompt_version,:quality,:completeness,:now,:now,:error)
            """), {"id": evidence_id, "file": file_id, "fingerprint": content_fingerprint, "kind": kind,
                    "schema": schema_version, "payload": encoded, "content": normalized_content, "state": state,
                    "producer_type": producer_type, "producer_name": producer_name, "producer_version": producer_version,
                    "model_profile_id": model_profile_id, "model_id": model_id, "prompt_version": prompt_version,
                    "quality": quality, "completeness": json.dumps(completeness or {}, ensure_ascii=False, separators=(",", ":")),
                    "now": now, "error": error_code})
            row = connection.execute(text("SELECT * FROM file_evidence WHERE id=:id"), {"id": evidence_id}).mappings().one()
        if state == "VALID":
            self._counters["cache_refresh"] += 1
        LOGGER.info("CACHE_REFRESH file_id=%s kind=%s evidence_id=%s state=%s", file_id, kind, evidence_id, state)
        return self._public(row)

    def sync_profile(self, *, file_id: str, content_fingerprint: str, profile: FileProfile,
                     producer_name: str = "GuixuParser", producer_version: str | None = None) -> list[dict[str, Any]]:
        """Project legacy embedded evidence into the canonical ledger idempotently."""
        self.invalidate_file_evidence(file_id, content_fingerprint)
        result: list[dict[str, Any]] = []
        parser_version = producer_version or profile.parser_version
        for evidence in profile.evidence:
            kind = normalize_evidence_kind(evidence.kind)
            origin = evidence.origin or producer_name
            # Model evidence is owned by the canonical ledger.  A later parser
            # snapshot may contain it because legacy profile snapshots are
            # immutable-ish aggregates; projecting it again would accidentally
            # revive a row explicitly marked STALE by force_refresh.
            if (origin.lower().startswith("ai:") or origin.lower().startswith("cache:")) and kind in {
                        "VISUAL_DESCRIPTION", "DOCUMENT_SUMMARY", "COMBINED_CONTENT_SUMMARY",
                        "AUDIO_SUMMARY", "VIDEO_SUMMARY",
                    }:
                continue
            if origin.lower().startswith("ai:") or "deepseek" in origin.lower() or "qwen" in origin.lower():
                producer_type = "CLOUD_MODEL" if "deepseek" in origin.lower() else "LOCAL_MODEL"
                source_name = origin.split(":", 1)[-1][:100]
            elif kind == "OCR_TEXT":
                producer_type, source_name = "LOCAL_OCR", origin[:100]
            elif kind in {"AUDIO_TRANSCRIPT", "VIDEO_TRANSCRIPT", "VIDEO_FRAME_DESCRIPTION"}:
                producer_type, source_name = "LOCAL_MEDIA", origin[:100]
            else:
                producer_type, source_name = "LOCAL_PARSER", origin[:100]
            result.append(self.store_evidence(
                file_id=file_id, content_fingerprint=content_fingerprint, evidence_kind=kind,
                payload={"text": evidence.text, "locator": evidence.locator.model_dump(mode="json"), "raw_version": 1},
                normalized_content=evidence.text, producer_type=producer_type, producer_name=source_name or producer_name,
                producer_version=parser_version, quality=evidence.quality,
            ))
        if profile.content_summary:
            result.append(self.store_evidence(
                file_id=file_id, content_fingerprint=content_fingerprint, evidence_kind="DOCUMENT_SUMMARY",
                payload={"summary": profile.content_summary, "raw_version": 1}, normalized_content=profile.content_summary,
                producer_type="LOCAL_PARSER" if profile.summary_origin == "deterministic" else "CLOUD_MODEL",
                producer_name=producer_name, producer_version=parser_version,
            ))
        return result

    def force_refresh(self, file_id: str, content_fingerprint: str, evidence_kind: str | None = None) -> int:
        clauses = ["file_id=:file", "content_fingerprint=:fingerprint", "state='VALID'"]
        params = {"file": file_id, "fingerprint": content_fingerprint}
        if evidence_kind is not None:
            clauses.append("evidence_kind=:kind"); params["kind"] = normalize_evidence_kind(evidence_kind)
        now = utc_now()
        with self.database.begin() as connection:
            result = connection.execute(text(f"UPDATE file_evidence SET state='STALE',invalidated_at=:now,invalidation_reason='FORCE_REFRESH' WHERE {' AND '.join(clauses)}"), {**params, "now": now})
        if result.rowcount:
            self._counters["cache_refresh"] += int(result.rowcount)
        return int(result.rowcount or 0)

    def invalidate_evidence_kind(self, file_id: str, fingerprint: str, evidence_kind: str, *, reason: str = "MANUAL_INVALIDATION") -> int:
        return self._invalidate_matching(file_id, fingerprint, normalize_evidence_kind(evidence_kind), reason)

    def _invalidate_matching(self, file_id: str, fingerprint: str, kind: str, reason: str) -> int:
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE file_evidence SET state='INVALID',invalidated_at=:now,invalidation_reason=:reason
                WHERE file_id=:file AND content_fingerprint=:fingerprint AND evidence_kind=:kind AND state='VALID'
            """), {"now": utc_now(), "reason": reason, "file": file_id, "fingerprint": fingerprint, "kind": kind})
        return int(result.rowcount or 0)

    def get_cache_status(self, *, file_id: str | None = None) -> dict[str, Any]:
        where = "WHERE file_id=:file" if file_id else ""
        params = {"file": file_id} if file_id else {}
        with self.database.engine.connect() as connection:
            counts = {str(state): int(count) for state, count in connection.execute(text(f"SELECT state,count(*) FROM file_evidence {where} GROUP BY state"), params).all()}
            total_bytes = int(connection.execute(text(f"SELECT COALESCE(sum(length(payload_json)),0) FROM file_evidence {where}"), params).scalar_one())
        return {"evidence_count": sum(counts.values()), "valid_count": counts.get("VALID", 0),
                "invalid_count": counts.get("INVALID", 0), "stale_count": counts.get("STALE", 0),
                "error_count": counts.get("ERROR", 0), "estimated_bytes": total_bytes,
                "counters": dict(self._counters)}

    def cleanup_invalid_cache(self, *, older_than_days: int = 30) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=max(0, older_than_days))).isoformat()
        with self.database.begin() as connection:
            result = connection.execute(text("""
                UPDATE file_evidence SET payload_json='{}',normalized_content=NULL
                 WHERE state IN ('INVALID','STALE','ERROR') AND COALESCE(invalidated_at,created_at)<:cutoff
            """), {"cutoff": cutoff})
        return int(result.rowcount or 0)

    def clear(self, *, file_id: str | None = None) -> int:
        where = "WHERE file_id=:file" if file_id else ""
        with self.database.begin() as connection:
            result = connection.execute(text(f"DELETE FROM file_evidence {where}"), {"file": file_id} if file_id else {})
        return int(result.rowcount or 0)

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        result = dict(row)
        for key in ("payload_json", "completeness_json"):
            raw = result.pop(key, "{}")
            result[key[:-5]] = json.loads(raw or "{}")
        return result
