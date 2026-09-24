from __future__ import annotations

import json
import threading
import time
from time import perf_counter
from pathlib import Path

from guixu.application.semantic_cache import EvidenceCacheService, fingerprint_for_path
from guixu.domain.files import ScannedFile
from guixu.domain.profiles import Coverage, Evidence, EvidenceLocator, FileProfile
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.scanner import ScanScope


def _fixture(project_root: Path, tmp_path: Path):
    root = tmp_path / "source"; root.mkdir()
    path = root / "photo.jpg"; path.write_bytes(b"same-content")
    database = Database(tmp_path / "app.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    repository = TaskRepository(database)
    task = repository.create("cache", TaskSettings(scan_mode="current_only"), {"user_instructions": ""})
    repository.store_scan(task["id"], [ScanScope("current", "current_only", root, root, "source")], [
        ScannedFile("current", path, path.name, "image", path.stat().st_size, path.stat().st_mtime_ns, "eligible")
    ], [], "preview_move")
    with database.engine.connect() as connection:
        file_id = connection.execute(__import__("sqlalchemy").text("SELECT id FROM files WHERE task_id=:task"), {"task": task["id"]}).scalar_one()
    return database, repository, task, file_id, path


def _profile(file_id: str, text_value: str = "海边三个人") -> FileProfile:
    return FileProfile(file_id=file_id, modality="image", coverage=Coverage(mode="full"), parser_version="parser-v1",
                       evidence=[Evidence(id="v1", kind="visual_description", text=text_value,
                                          locator=EvidenceLocator(), quality="high", origin="DeepSeek")])


def test_cache_hit_move_rename_and_content_change(project_root: Path, tmp_path: Path):
    database, _, _, file_id, path = _fixture(project_root, tmp_path)
    cache = EvidenceCacheService(database)
    first = fingerprint_for_path(path)
    cache.sync_profile(file_id=file_id, content_fingerprint=first, profile=_profile(file_id))
    assert cache.get_valid_evidence(file_id, first, "VISUAL_DESCRIPTION")["normalized_content"] == "海边三个人"
    moved = path.with_name("holiday.jpg"); path.rename(moved)
    assert cache.get_valid_evidence(file_id, first, "VISUAL_DESCRIPTION") is not None
    moved.write_bytes(b"changed-content")
    second = fingerprint_for_path(moved)
    cache.invalidate_file_evidence(file_id, second)
    assert cache.get_valid_evidence(file_id, second, "VISUAL_DESCRIPTION") is None
    old = cache.get_evidence_by_kind(file_id, first, "VISUAL_DESCRIPTION")[0]
    assert old["state"] == "INVALID" and old["invalidation_reason"] == "CONTENT_CHANGED"
    database.close()


def test_provenance_prompt_parser_provider_and_force_refresh(project_root: Path, tmp_path: Path):
    database, _, _, file_id, path = _fixture(project_root, tmp_path)
    cache = EvidenceCacheService(database); fingerprint = fingerprint_for_path(path)
    first = cache.store_evidence(file_id=file_id, content_fingerprint=fingerprint, evidence_kind="OCR_TEXT",
        payload={"text": "GUIXU"}, normalized_content="GUIXU", producer_type="LOCAL_OCR",
        producer_name="RapidOCR", producer_version="2", quality="high")
    assert first["producer_type"] == "LOCAL_OCR"
    second = cache.store_evidence(file_id=file_id, content_fingerprint=fingerprint, evidence_kind="VISUAL_DESCRIPTION",
        payload={"description": "建筑夜景"}, normalized_content="建筑夜景", producer_type="CLOUD_MODEL",
        producer_name="DeepSeek", producer_version="deepseek-flash", model_id="deepseek-flash",
        prompt_version="vision-description-v1", quality="high")
    assert cache.get_valid_evidence(file_id, fingerprint, "VISUAL_DESCRIPTION", prompt_version="vision-description-v1")["id"] == second["id"]
    assert cache.get_valid_evidence(file_id, fingerprint, "VISUAL_DESCRIPTION", prompt_version="vision-description-v2") is None
    assert cache.force_refresh(file_id, fingerprint, "VISUAL_DESCRIPTION") == 1
    assert cache.get_valid_evidence(file_id, fingerprint, "VISUAL_DESCRIPTION") is None
    database.close()


def test_failed_generation_is_retryable(project_root: Path, tmp_path: Path):
    database, _, _, file_id, path = _fixture(project_root, tmp_path)
    cache = EvidenceCacheService(database); fingerprint = fingerprint_for_path(path)
    cache.store_evidence(file_id=file_id, content_fingerprint=fingerprint, evidence_kind="VISUAL_DESCRIPTION",
        payload={"error": "timeout"}, producer_type="CLOUD_MODEL", producer_name="DeepSeek", state="ERROR", error_code="TIMEOUT")
    assert cache.get_valid_evidence(file_id, fingerprint, "VISUAL_DESCRIPTION") is None
    retry = cache.store_evidence(file_id=file_id, content_fingerprint=fingerprint, evidence_kind="VISUAL_DESCRIPTION",
        payload={"description": "retry"}, normalized_content="retry", producer_type="CLOUD_MODEL", producer_name="DeepSeek")
    assert retry["state"] == "VALID"
    database.close()


def test_restart_clear_and_scope_safe_cache(project_root: Path, tmp_path: Path):
    database, _, _, file_id, path = _fixture(project_root, tmp_path)
    fingerprint = fingerprint_for_path(path); cache = EvidenceCacheService(database)
    cache.store_evidence(file_id=file_id, content_fingerprint=fingerprint, evidence_kind="TEXT_EXTRACT",
        payload={"text": "local"}, normalized_content="local", producer_type="LOCAL_PARSER", producer_name="pypdf")
    database.close()
    reopened = Database(tmp_path / "app.sqlite3", project_root / "contracts" / "database.sql"); reopened.initialize()
    cache2 = EvidenceCacheService(reopened)
    assert cache2.get_valid_evidence(file_id, fingerprint, "TEXT_EXTRACT")["normalized_content"] == "local"
    before = path.read_bytes(); assert cache2.clear() == 1; assert path.read_bytes() == before
    reopened.close()


def test_single_flight_serializes_same_key(project_root: Path, tmp_path: Path):
    database, _, _, file_id, path = _fixture(project_root, tmp_path)
    cache = EvidenceCacheService(database); fingerprint = fingerprint_for_path(path)
    active = 0; peak = 0; guard = threading.Lock()

    def worker():
        nonlocal active, peak
        with cache.single_flight(file_id, fingerprint, "VISUAL_DESCRIPTION"):
            with guard:
                active += 1; peak = max(peak, active)
            time.sleep(0.02)
            with guard:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [thread.start() for thread in threads]; [thread.join() for thread in threads]
    assert peak == 1
    database.close()


def test_500_file_lookup_only_refreshes_missing_subset(project_root: Path, tmp_path: Path):
    root = tmp_path / "bulk"; root.mkdir()
    database = Database(tmp_path / "bulk.sqlite3", project_root / "contracts" / "database.sql"); database.initialize()
    repository = TaskRepository(database)
    task = repository.create("bulk", TaskSettings(scan_mode="current_only"), {"user_instructions": ""})
    files = [ScannedFile("current", root / f"file-{index}.txt", f"file-{index}.txt", "text", 1, index + 1, "eligible") for index in range(500)]
    repository.store_scan(task["id"], [ScanScope("current", "current_only", root, root, "bulk")], files, [], "preview_move")
    with database.engine.connect() as connection:
        ids = [row[0] for row in connection.execute(__import__("sqlalchemy").text("SELECT id FROM files WHERE task_id=:task ORDER BY id"), {"task": task["id"]}).all()]
    cache = EvidenceCacheService(database); fingerprint = "b" * 64
    for file_id in ids[:450]:
        cache.store_evidence(file_id=file_id, content_fingerprint=fingerprint, evidence_kind="TEXT_EXTRACT",
            payload={"text": "cached"}, normalized_content="cached", producer_type="LOCAL_PARSER", producer_name="fixture")
    started = perf_counter()
    missing = [file_id for file_id in ids if cache.get_valid_evidence(file_id, fingerprint, "TEXT_EXTRACT") is None]
    elapsed = perf_counter() - started
    assert len(ids) == 500 and len(missing) == 50 and elapsed < 5
    database.close()
