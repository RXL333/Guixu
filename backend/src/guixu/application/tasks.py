from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.grants import SourceRegistry
from guixu.infrastructure.filesystem.scanner import Scanner


class TaskService:
    def __init__(self, repository: TaskRepository, registry: SourceRegistry, allow_direct_move: bool = False) -> None:
        self.repository = repository
        self.registry = registry
        self.scanner = Scanner()
        self._task_grants: dict[str, tuple[str, str | None]] = {}
        self._lock = threading.RLock()
        self.allow_direct_move = allow_direct_move

    def create_task(
        self,
        name: str,
        source_grant: str,
        output_grant: str | None,
        settings: TaskSettings,
        classification_request: dict[str, Any],
        model_profile_id: str | None = None,
        model_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.registry.get(source_grant, "source")
        if output_grant:
            self.registry.get(output_grant, "output")
        if settings.operation_mode == "copy" and not output_grant:
            raise ValueError("copy mode requires output_grant")
        if settings.operation_mode == "direct_move" and not self.allow_direct_move:
            raise ValueError("direct_move is disabled until phase 08 safety acceptance")
        task = self.repository.create(name, settings, classification_request, model_profile_id, model_snapshot)
        with self._lock:
            self._task_grants[task["id"]] = (source_grant, output_grant)
        return task

    def start(self, task_id: str, expected_revision: int) -> None:
        task = self.repository.get(task_id)
        self.repository.begin_scan(task_id, expected_revision)
        try:
            with self._lock:
                source_grant, output_grant = self._task_grants[task_id]
            source = self.registry.get(source_grant, "source").canonical_root
            output = self.registry.get(output_grant, "output").canonical_root if output_grant else None
            settings = TaskSettings.model_validate(task["settings"])
            known_outputs = tuple(path for path in self.repository.known_output_roots() if path != source)
            result = self.scanner.scan(source, settings, output, known_outputs)
            scopes = result.scopes
            if settings.operation_mode == "copy" and output:
                scopes = [
                    replace(scope, destination_root=(output / scope.display_name) if scope.kind == "protected_child" else output)
                    for scope in scopes
                ]
            self.repository.store_scan(task_id, scopes, result.files, result.warnings, settings.operation_mode)
        except Exception:
            self.repository.fail_scan(task_id, "SCAN_FAILED")
            raise
