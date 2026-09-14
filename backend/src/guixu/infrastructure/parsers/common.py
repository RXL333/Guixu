from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


PARSER_VERSION = "guixu-parser-1"
MAX_ARCHIVE_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class ParseLimitError(ValueError):
    pass


def stratified_indices(total: int, maximum: int) -> list[int]:
    if total <= 0 or maximum <= 0:
        return []
    if total <= maximum:
        return list(range(total))
    if maximum == 1:
        return [0]
    return sorted({round(index * (total - 1) / (maximum - 1)) for index in range(maximum)})


def validate_zip_container(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ParseLimitError("ARCHIVE_ENTRY_LIMIT")
        total = sum(item.file_size for item in entries)
        compressed = sum(max(item.compress_size, 1) for item in entries)
        if total > MAX_UNCOMPRESSED_BYTES or (total / compressed if compressed else total) > MAX_COMPRESSION_RATIO:
            raise ParseLimitError("ARCHIVE_EXPANSION_LIMIT")
        for item in entries:
            parts = Path(item.filename).parts
            if item.filename.startswith(("/", "\\")) or ".." in parts:
                raise ParseLimitError("ARCHIVE_PATH_INVALID")


def options_hash(options: dict[str, object]) -> str:
    import json
    return hashlib.sha256(json.dumps(options, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

