from __future__ import annotations

from pathlib import Path

from guixu.application.parser_runner import ParserRunner
from guixu.infrastructure.db.repository import TaskRepository
from guixu.domain.profiles import with_file_context
from guixu.infrastructure.filesystem.identity import sha256_file
from guixu.infrastructure.parsers.common import PARSER_VERSION, options_hash


class ParsingService:
    def __init__(self, repository: TaskRepository, cache_dir: Path) -> None:
        self.repository = repository
        self.runner = ParserRunner(cache_dir)

    def parse(self, task_id: str, file_id: str, preset: str = "standard"):
        file = self.repository.get_file(task_id, file_id)
        if file["scan_status"] != "eligible":
            raise ValueError("FILE_NOT_ELIGIBLE")
        path = Path(file["current_path"])
        if not path.is_file():
            raise ValueError("SOURCE_MISSING")
        content_hash = sha256_file(path)
        option_digest = options_hash({"preset": preset})
        cache_key = f"{content_hash}-{PARSER_VERSION}-{option_digest}"
        cached = self.repository.load_profile(file_id, cache_key)
        if cached is not None:
            cached = with_file_context(cached, path)
            self.repository.store_profile(cached, cache_key, option_digest)
            return cached
        outcome = self.runner.parse(path, file_id, preset)
        self.repository.store_profile(outcome, cache_key, option_digest)
        return outcome
