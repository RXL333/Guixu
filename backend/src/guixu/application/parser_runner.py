from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil

from guixu.domain.profiles import ParseOutcome, with_file_context
from guixu.infrastructure.filesystem.identity import sha256_file
from guixu.infrastructure.parsers.common import PARSER_VERSION, options_hash


class ParserRunner:
    def __init__(self, cache_dir: Path, timeout_seconds: float = 120, max_output_bytes: int = 2 * 1024 * 1024, max_worker_memory_bytes: int = 768 * 1024 * 1024) -> None:
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.max_worker_memory_bytes = max_worker_memory_bytes
        cache_dir.mkdir(parents=True, exist_ok=True)

    def parse(self, path: Path, file_id: str, preset: str = "standard", cancel_event: threading.Event | None = None) -> ParseOutcome:
        # Cache directories may be cleared by the user between application
        # startup and a parse request; recreate only this app-owned directory.
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        content_hash = sha256_file(path)
        key = f"{content_hash}-{PARSER_VERSION}-{options_hash({'preset': preset})}"
        # Keep the on-disk name bounded for Windows MAX_PATH while preserving the
        # full semantic key in the profile database.
        cache_file = self.cache_dir / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"
        if cache_file.exists() and cache_file.stat().st_size <= self.max_output_bytes:
            cached = ParseOutcome.model_validate_json(cache_file.read_text("utf-8"))
            # The payload is content-addressed, but file_id is task/file context and
            # must never leak from the first file that populated the cache.
            rebound = cached.model_copy(update={"profile": cached.profile.model_copy(update={"file_id": file_id})})
            return with_file_context(rebound, path)
        with tempfile.TemporaryDirectory(prefix="guixu-parser-") as temporary:
            temporary_path = Path(temporary)
            job_file = temporary_path / "job.json"; output_file = temporary_path / "result.json"
            job_file.write_text(json.dumps({"path": str(path), "file_id": file_id, "preset": preset, "artifact_dir": str(self.cache_dir / "thumbnails")}), "utf-8")
            process = subprocess.Popen(self._command(job_file, output_file), cwd=Path(__file__).resolve().parents[3], env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"})
            failure = self._monitor(process, cancel_event)
            if failure:
                self._terminate_tree(process.pid)
                return self._failure(file_id, path, failure)
            if process.returncode != 0 or not output_file.exists() or output_file.stat().st_size > self.max_output_bytes:
                return self._failure(file_id, path, "PARSER_WORKER_FAILED")
            outcome = ParseOutcome.model_validate_json(output_file.read_text("utf-8"))
            temporary_cache = cache_file.with_suffix(".tmp")
            temporary_cache.write_text(outcome.model_dump_json(), "utf-8")
            os.replace(temporary_cache, cache_file)
            return with_file_context(outcome, path)

    def _monitor(self, process: subprocess.Popen, cancel_event: threading.Event | None) -> str | None:
        deadline = time.monotonic() + self.timeout_seconds
        while process.poll() is None:
            if cancel_event and cancel_event.is_set():
                return "PARSER_CANCELLED"
            if time.monotonic() >= deadline:
                return "PARSER_TIMEOUT"
            try:
                parent = psutil.Process(process.pid)
                memory = parent.memory_info().rss + sum(child.memory_info().rss for child in parent.children(recursive=True))
                if memory > self.max_worker_memory_bytes:
                    return "PARSER_MEMORY_LIMIT"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            time.sleep(0.025)
        return None

    def _command(self, job_file: Path, output_file: Path) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "--worker", "--job", str(job_file), "--output", str(output_file)]
        return [sys.executable, "-m", "guixu.worker", "--job", str(job_file), "--output", str(output_file)]

    @staticmethod
    def _terminate_tree(pid: int) -> None:
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            psutil.wait_procs([parent], timeout=5)
        except psutil.Error:
            return

    @staticmethod
    def _failure(file_id: str, path: Path, warning: str) -> ParseOutcome:
        from guixu.domain.files import detect_modality
        from guixu.domain.profiles import Coverage, FileProfile
        profile = FileProfile(file_id=file_id, modality=detect_modality(path), metadata={}, coverage=Coverage(mode="metadata_only"), warnings=[warning], capabilities_used=[], parser_version=PARSER_VERSION)
        return with_file_context(ParseOutcome(status="failed", profile=profile), path)
