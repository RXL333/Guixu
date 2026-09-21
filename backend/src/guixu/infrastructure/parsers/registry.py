from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from guixu.domain.files import detect_modality
from guixu.domain.profiles import Coverage, FileProfile, ParseOutcome, with_file_context
from guixu.infrastructure.parsers.common import PARSER_VERSION
from guixu.infrastructure.parsers.documents import DOCUMENT_PARSERS
from guixu.infrastructure.parsers.images import parse_image
from guixu.infrastructure.parsers.media import parse_media
from guixu.infrastructure.parsers.text import parse_text


TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".tsv", ".log", ".rst", ".yaml", ".yml"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".m4v"}


class ParserRegistry:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in TEXT_SUFFIXES | IMAGE_SUFFIXES | set(DOCUMENT_PARSERS) | AUDIO_SUFFIXES | VIDEO_SUFFIXES

    def parse(self, path: Path, file_id: str, preset: str = "standard", artifact_dir: Path | None = None) -> ParseOutcome:
        suffix = path.suffix.lower(); modality = detect_modality(path)
        try:
            self._validate_signature(path, suffix)
            if suffix in TEXT_SUFFIXES:
                outcome = parse_text(path, file_id, preset)
            elif suffix in DOCUMENT_PARSERS:
                outcome = DOCUMENT_PARSERS[suffix](path, file_id, preset)
            elif suffix in IMAGE_SUFFIXES:
                outcome = parse_image(path, file_id, preset, artifact_dir or path.parent / ".guixu-thumbnails")
            elif suffix in AUDIO_SUFFIXES:
                outcome = parse_media(path, file_id, "audio", preset)
            elif suffix in VIDEO_SUFFIXES:
                outcome = parse_media(path, file_id, "video", preset)
            else:
                outcome = self._failure(file_id, modality, "unsupported", "UNSUPPORTED_FORMAT")
        except Exception as exc:
            code = str(exc) if str(exc).isupper() or "_" in str(exc) else type(exc).__name__.upper()
            outcome = self._failure(file_id, modality, "failed", code[:300])
        return with_file_context(outcome, path)

    def _validate_signature(self, path: Path, suffix: str) -> None:
        header = path.read_bytes()[:16]
        if suffix == ".pdf" and not header.startswith(b"%PDF-"):
            raise ValueError("FORMAT_SIGNATURE_MISMATCH")
        if suffix in {".docx", ".pptx", ".xlsx"} and not header.startswith(b"PK"):
            raise ValueError("FORMAT_SIGNATURE_MISMATCH")
        if suffix in TEXT_SUFFIXES and b"\x00" in header:
            raise ValueError("FORMAT_SIGNATURE_MISMATCH")
        if suffix in IMAGE_SUFFIXES:
            try:
                with Image.open(path) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError) as exc:
                raise ValueError("FORMAT_SIGNATURE_MISMATCH") from exc

    @staticmethod
    def _failure(file_id: str, modality: str, status: str, warning: str) -> ParseOutcome:
        profile = FileProfile(file_id=file_id, modality=modality, metadata={}, coverage=Coverage(mode="metadata_only"), warnings=[warning], capabilities_used=[], parser_version=PARSER_VERSION)
        return ParseOutcome(status=status, profile=profile)
