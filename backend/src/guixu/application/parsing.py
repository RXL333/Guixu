from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from guixu.application.parser_runner import ParserRunner
from guixu.application.semantic_cache import EvidenceCacheService, fingerprint_for_path
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.db.database import utc_now
from guixu.domain.profiles import with_file_context
from guixu.infrastructure.filesystem.identity import sha256_file
from guixu.infrastructure.parsers.common import PARSER_VERSION, options_hash


class ParsingService:
    def __init__(self, repository: TaskRepository, cache_dir: Path,
                 evidence_cache: EvidenceCacheService | None = None) -> None:
        self.repository = repository
        self.runner = ParserRunner(cache_dir)
        self.evidence_cache = evidence_cache

    def parse(self, task_id: str, file_id: str, preset: str = "standard"):
        file = self.repository.get_file(task_id, file_id)
        if file["scan_status"] != "eligible":
            raise ValueError("FILE_NOT_ELIGIBLE")
        path = Path(file["current_path"])
        if not path.is_file():
            raise ValueError("SOURCE_MISSING")
        content_hash = sha256_file(path)
        with self.repository.database.begin() as connection:
            stat = path.stat()
            connection.execute(text("""
                UPDATE files SET sha256=:sha256,size_bytes=:size,mtime_ns=:mtime,updated_at=:now WHERE id=:file
            """), {"sha256": content_hash, "size": stat.st_size, "mtime": stat.st_mtime_ns,
                   "now": utc_now(), "file": file_id})
        if self.evidence_cache is not None:
            self.evidence_cache.invalidate_file_evidence(file_id, content_hash)
        option_digest = options_hash({"preset": preset})
        cache_key = f"{content_hash}-{PARSER_VERSION}-{option_digest}"
        cached = self.repository.load_profile(file_id, cache_key)
        if cached is not None:
            cached = with_file_context(cached, path)
            self.repository.store_profile(cached, cache_key, option_digest)
            if self.evidence_cache is not None:
                self.evidence_cache.sync_profile(file_id=file_id, content_fingerprint=content_hash,
                                                 profile=cached.profile, producer_version=PARSER_VERSION)
            return cached
        outcome = self.runner.parse(path, file_id, preset)
        self.repository.store_profile(outcome, cache_key, option_digest)
        if self.evidence_cache is not None and outcome.status in {"ready", "partial"}:
            self.evidence_cache.sync_profile(file_id=file_id, content_fingerprint=content_hash,
                                             profile=outcome.profile, producer_version=PARSER_VERSION)
        return outcome
