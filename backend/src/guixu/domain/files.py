from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MODALITY_EXTENSIONS: dict[str, set[str]] = {
    "image": {".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"},
    "text": {".csv", ".json", ".log", ".md", ".rst", ".txt", ".yaml", ".yml"},
    "document": {".docx", ".odp", ".ods", ".odt", ".pdf", ".pptx", ".xlsx"},
    "audio": {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma"},
    "video": {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm", ".wmv"},
}


def detect_modality(path: Path) -> str:
    suffix = path.suffix.lower()
    for modality, extensions in MODALITY_EXTENSIONS.items():
        if suffix in extensions:
            return modality
    return "other"


@dataclass(frozen=True)
class ScannedFile:
    scope_id: str
    path: Path
    relative_path: str
    modality: str
    size_bytes: int
    mtime_ns: int
    scan_status: str
    exclusion_code: str | None = None
    companion_group_id: str | None = None
