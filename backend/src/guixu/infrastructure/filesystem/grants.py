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


def _protected_locations() -> tuple[list[Path], list[Path]]:
    """Locations an organizer must never be pointed at, however they were typed.

    Returns `(whole_subtrees, roots_only)`. The split matters: Windows and the
    program directories are off limits all the way down, but the user profile is
    only off limits *as a whole*. Blocking the profile subtree would take
    Documents, Downloads, Pictures and every project folder with it, which is
    exactly what the product is for.

    The typed-grant API accepts any string, and a file organizer given a root will
    eventually move things inside it. Pointing one at the profile root would put
    `AppData`, `.ssh` and profile-root configuration within reach of a category
    rename; pointing it at a drive root would put the entire volume there.
    """
    subtrees: list[str] = []
    for variable in ("SystemRoot", "ProgramFiles", "ProgramW6432", "ProgramData"):
        value = os.environ.get(variable)
        if value:
            subtrees.append(value)
    roots_only: list[str] = []
    if os.name == "nt":
        subtrees += [r"C:\Program Files (x86)", r"C:\System Volume Information",
                     r"C:\$Recycle.Bin", r"C:\Recovery", r"C:\Users\Public"]
        roots_only.append(r"C:\Users")
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            roots_only.append(letter + ":\\")
    for variable in ("USERPROFILE", "HOME"):
        value = os.environ.get(variable)
        if value:
            roots_only.append(value)

    def _resolve_all(values: list[str]) -> list[Path]:
        resolved: list[Path] = []
        for candidate in values:
            try:
                resolved.append(Path(candidate).resolve(strict=False))
            except (OSError, RuntimeError):
                continue
        return resolved

    return _resolve_all(subtrees), _resolve_all(roots_only)


def _is_protected(resolved: Path) -> bool:
    """Containment test that survives case differences and near-miss prefixes.

    `Path.relative_to` is case-sensitive and Windows is not, so without the
    normcase step a typed `C:/WINDOWS` would sail past a `C:/Windows` entry.
    Comparing with an explicit separator also stops `C:/WindowsOld` from matching
    a `C:/Windows` rule by string prefix.
    """
    target = os.path.normcase(str(resolved)).rstrip("\\/")
    subtrees, roots_only = _protected_locations()
    for root in subtrees:
        root_text = os.path.normcase(str(root)).rstrip("\\/")
        if target == root_text or target.startswith(root_text + os.sep):
            return True
    return any(target == os.path.normcase(str(root)).rstrip("\\/") for root in roots_only)


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
    if _is_protected(resolved):
        raise GrantError("PROTECTED_LOCATION_BLOCKED")
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
