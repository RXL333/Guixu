from __future__ import annotations

import hmac
import os
import stat
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path


class GrantError(ValueError):
    pass


@dataclass(frozen=True)
class DirectoryGrant:
    grant_id: str
    purpose: str
    canonical_root: Path
    display_path: str
    writable: bool


def canonicalize_directory(raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    try:
        original_attrs = path.lstat()
    except OSError as exc:
        raise GrantError("PATH_INVALID") from exc
    if stat.S_ISLNK(original_attrs.st_mode) or bool(
        os.name == "nt" and getattr(original_attrs, "st_file_attributes", 0) & 0x400
    ):
        raise GrantError("REPARSE_POINT_BLOCKED")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise GrantError("PATH_INVALID") from exc
    if not resolved.is_dir():
        raise GrantError("PATH_INVALID")
    return resolved


class SourceRegistry:
    PURPOSES = {"source", "output", "export", "component_import"}

    def __init__(self) -> None:
        self._grants: dict[str, DirectoryGrant] = {}
        self._lock = threading.RLock()

    def register_typed_directory(self, raw_path: str, purpose: str) -> DirectoryGrant:
        if purpose not in self.PURPOSES:
            raise GrantError("INVALID_PURPOSE")
        root = canonicalize_directory(raw_path)
        grant = DirectoryGrant(
            grant_id=str(uuid.uuid4()),
            purpose=purpose,
            canonical_root=root,
            display_path=str(root),
            writable=os.access(root, os.W_OK),
        )
        with self._lock:
            self._grants[grant.grant_id] = grant
        return grant

    def get(self, grant_id: str, purpose: str | None = None) -> DirectoryGrant:
        with self._lock:
            grant = self._grants.get(grant_id)
        if grant is None or (purpose is not None and not hmac.compare_digest(grant.purpose, purpose)):
            raise GrantError("PATH_OUTSIDE_GRANT")
        return grant
