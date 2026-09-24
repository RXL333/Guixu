from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from guixu.domain.profiles import FileProfile

ALLOWED_DATA_TYPES = {"extracted_text", "derivative_images", "video_frames", "asr_text", "basename", "precise_location", "original_images"}


class PrivacyError(RuntimeError):
    pass


def scope_hash(profile_id: str, data_types: list[str], budget: dict[str, Any]) -> str:
    encoded = json.dumps({"provider_profile_id": profile_id, "data_types": sorted(data_types), "budget": budget}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class OutboundEnvelope:
    file_id: str
    modality: str
    content_summary: str
    evidence: list[dict[str, Any]]
    coverage: dict[str, Any]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]: return self.__dict__.copy()


def build_outbound(profile: FileProfile, allowed: set[str], *, max_chars: int) -> OutboundEnvelope:
    if not allowed <= ALLOWED_DATA_TYPES: raise PrivacyError("DATA_TYPE_NOT_ALLOWED")
    evidence = []
    remaining = max_chars
    kind_map = {"extracted_text": "extracted_text", "ocr": "extracted_text", "transcript": "asr_text", "subtitle": "asr_text",
                "visual_caption": "derivative_images", "visual_description": "derivative_images"}
    for item in profile.evidence:
        data_type = kind_map.get(item.kind)
        # A cached visual description is already local text.  It may be sent as
        # minimized evidence without requesting a fresh derivative upload.
        if item.kind == "visual_description" and "derivative_images" not in allowed:
            data_type = "extracted_text"
        if data_type not in allowed or remaining <= 0: continue
        text = item.text[:remaining]; remaining -= len(text)
        evidence.append({"id": item.id, "kind": item.kind, "text": text, "locator": item.locator.model_dump(mode="json"), "quality": item.quality})
    summary = profile.content_summary[:min(2000, remaining)] if "extracted_text" in allowed else ""
    return OutboundEnvelope(profile.file_id, profile.modality, summary, evidence,
                            profile.coverage.model_dump(mode="json"), list(profile.warnings))
