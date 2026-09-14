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
    return resolved


def target_key(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()

