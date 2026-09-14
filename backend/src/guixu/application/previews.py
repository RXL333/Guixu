from __future__ import annotations

import mimetypes
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from guixu.infrastructure.db.repository import TaskRepository


SAFE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".wav", ".mp3", ".flac", ".m4a", ".mp4", ".mkv", ".mov"}


@dataclass(frozen=True)
class PreviewGrant:
    path: Path
    size: int
    mtime_ns: int
    media_type: str
    expires_at: datetime


class PreviewTicketService:
    def __init__(self, repository: TaskRepository, ttl_seconds: int = 60) -> None:
        self.repository = repository
        self.ttl_seconds = ttl_seconds
        self._tickets: dict[str, PreviewGrant] = {}
        self._lock = threading.RLock()

    def issue(self, task_id: str, file_id: str) -> dict[str, object]:
        file = self.repository.get_file(task_id, file_id)
        path = Path(file["current_path"])
        if path.suffix.lower() not in SAFE_EXTENSIONS or not path.is_file():
            raise ValueError("PREVIEW_UNSUPPORTED")
        stat = path.stat()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        expires = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        ticket = secrets.token_urlsafe(32)
        with self._lock:
            self._purge_expired()
            self._tickets[ticket] = PreviewGrant(path, stat.st_size, stat.st_mtime_ns, media_type, expires)
        return {"ticket": ticket, "expires_at": expires.isoformat(), "size_bytes": stat.st_size, "media_type": media_type}

    def resolve(self, ticket: str) -> PreviewGrant:
        with self._lock:
            self._purge_expired()
            grant = self._tickets.get(ticket)
        if grant is None:
            raise KeyError(ticket)
        try:
            stat = grant.path.stat()
        except OSError as exc:
            raise KeyError(ticket) from exc
        if stat.st_size != grant.size or stat.st_mtime_ns != grant.mtime_ns:
            with self._lock:
                self._tickets.pop(ticket, None)
            raise ValueError("PREVIEW_SOURCE_CHANGED")
        return grant

    def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        for key, value in list(self._tickets.items()):
            if value.expires_at <= now:
                self._tickets.pop(key, None)
