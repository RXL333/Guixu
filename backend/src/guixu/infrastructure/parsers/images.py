from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from guixu.domain.profiles import Coverage, Evidence, EvidenceLocator, FileProfile, ParseOutcome
from guixu.infrastructure.parsers.common import PARSER_VERSION, stratified_indices
from guixu.infrastructure.parsers.ocr import recognize


MAX_IMAGE_PIXELS = 64_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def parse_image(path: Path, file_id: str, preset: str, artifact_dir: Path) -> ParseOutcome:
    maximum_edge = {"fast": 960, "standard": 1280, "deep": 1920}[preset]
    warnings = []; evidence = []; artifacts = []
    with Image.open(path) as image:
        width, height = image.size
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError("IMAGE_PIXEL_LIMIT")
        frame_count = getattr(image, "n_frames", 1)
        frame_indexes = stratified_indices(frame_count, 3 if frame_count > 1 else 1)
        metadata = {"width": width, "height": height, "format": image.format, "mode": image.mode, "frames": frame_count, "animated": frame_count > 1}
        exif = image.getexif()
        if exif:
            metadata["orientation"] = exif.get(274)
            metadata["captured_at"] = exif.get(36867) or exif.get(306)
            metadata["camera_make"] = exif.get(271)
            metadata["camera_model"] = exif.get(272)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        for ordinal, frame_index in enumerate(frame_indexes):
            image.seek(frame_index)
            frame = ImageOps.exif_transpose(image.copy()).convert("RGB")
            frame.thumbnail((maximum_edge, maximum_edge))
            output = artifact_dir / f"{file_id}-frame-{frame_index}.jpg"
            frame.save(output, "JPEG", quality=85, optimize=True)
            artifacts.append(str(output))
            evidence.append(Evidence(id=f"frame-{ordinal + 1}", kind="metadata", text=f"图像帧 {frame_index + 1}/{frame_count}，{width}×{height}", locator=EvidenceLocator(frame_id=f"frame-{frame_index}"), quality="high", origin="Pillow"))
        if frame_count > len(frame_indexes):
            warnings.append("ANIMATED_IMAGE_SAMPLED")
        image.seek(frame_indexes[0])
        ocr_lines, ocr_warning = recognize(ImageOps.exif_transpose(image.copy()).convert("RGB"))
        if ocr_lines:
            evidence.append(Evidence(id="ocr-1", kind="ocr", text="\n".join(line for line, _ in ocr_lines)[:12_000], locator=EvidenceLocator(frame_id=f"frame-{frame_indexes[0]}"), quality="high" if min(score for _, score in ocr_lines) >= 0.8 else "medium", origin="RapidOCR-local-verified"))
        if ocr_warning:
            warnings.append(ocr_warning)
    summary = "\n".join(item.text for item in evidence if item.kind == "ocr")[:2000]
    capabilities = ["Pillow", "exif-stripped-thumbnail"] + (["RapidOCR-CPU"] if ocr_lines else [])
    profile = FileProfile(file_id=file_id, modality="image", metadata=metadata, content_summary=summary, summary_origin="deterministic" if summary else "none", evidence=evidence, coverage=Coverage(mode="sampled" if frame_count > len(frame_indexes) else "full", truncated=frame_count > len(frame_indexes)), warnings=warnings, capabilities_used=capabilities, parser_version=PARSER_VERSION)
    return ParseOutcome(status="partial" if warnings else "ready", profile=profile, cache_artifacts=artifacts)
