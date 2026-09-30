from __future__ import annotations

import os
import unicodedata
from pathlib import Path


WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))
}
INVALID_CHARS = set('<>:"/\\|?*')


class PathPolicyError(ValueError):
    pass


def validate_category_segment(raw: str) -> str:
    value = unicodedata.normalize("NFC", raw)
    if not value or value in {".", ".."} or len(value) > 60:
        raise PathPolicyError("CATEGORY_NAME_INVALID")
    if value[-1] in {" ", "."} or any(ord(char) < 32 or char in INVALID_CHARS for char in value):
        raise PathPolicyError("CATEGORY_NAME_INVALID")
    if value.split(".", 1)[0].upper() in WINDOWS_RESERVED:
        raise PathPolicyError("CATEGORY_NAME_RESERVED")
    return value


def ensure_within(path: Path, root: Path) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise PathPolicyError("PATH_OUTSIDE_GRANT") from exc
    if str(resolved).startswith("\\\\") or str(resolved).startswith("\\?\\"):
        raise PathPolicyError("NETWORK_OR_DEVICE_PATH_BLOCKED")
    # The containment check above must use the resolved form so a junction or a `..`
    # segment cannot slip past it. The returned path must not: on Windows, resolving a
    # leaf that does not exist yet rewrites it to the on-disk casing of a
    # case-insensitively equal name. With `photo.jpg` already in the destination, a
    # plan targeting `Photo.jpg` would silently republish the user's file under the
    # occupant's casing. That is invisible on NTFS and a real rename on a
    # case-preserving target — a network share, an exFAT card, a synced folder.
    return Path(os.path.abspath(path))


def target_key(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()

