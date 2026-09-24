from __future__ import annotations

from typing import Any

from guixu.application.classification import ClassificationService
from guixu.application.model_gateway import ModelGateway
from guixu.application.parsing import ParsingService
from guixu.application.semantic_cache import EvidenceCacheService, fingerprint_for_path
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.models.transport import ModelTransportError
from guixu.domain.profiles import Evidence, EvidenceLocator
from pathlib import Path


class AIFileClassifier:
    def __init__(self, repository: TaskRepository, parsing: ParsingService,
                 classifications: ClassificationService, gateway: ModelGateway,
                 evidence_cache: EvidenceCacheService | None = None) -> None:
        self.repository = repository
        self.parsing = parsing
        self.classifications = classifications
        self.gateway = gateway
        self.evidence_cache = evidence_cache

    def classify_taxonomy(self, task_id: str, taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
        task = self.repository.get(task_id)
        model = task["model_snapshot"]
        configured_batch = int(model.get("options", {}).get("batch_size", 20))
        file_ids = self.repository.eligible_file_ids(task_id, taxonomy["scope_id"])
        prepared = []
        cached_visual_ids: set[str] = set()
        for file_id in file_ids:
            outcome = self.parsing.parse(task_id, file_id, task["settings"]["analysis_preset"])
            profile = outcome.profile
            if self.evidence_cache is not None and profile.modality == "image":
                file = self.repository.get_file(task_id, file_id)
                path = Path(file["current_path"])
                if path.is_file():
                    fingerprint = fingerprint_for_path(path)
                    cached = self.evidence_cache.get_valid_evidence(file_id, fingerprint, "VISUAL_DESCRIPTION")
                    if cached:
                        text_value = str(cached.get("normalized_content") or cached.get("payload", {}).get("description") or cached.get("payload", {}).get("text") or "").strip()
                        if text_value:
                            profile = profile.model_copy(update={"evidence": [
                                *[item for item in profile.evidence if item.kind != "visual_description"],
                                Evidence(id=str(cached["id"]), kind="visual_description", text=text_value[:12_000],
                                        locator=EvidenceLocator(), quality=cached.get("quality") or "high",
                                        origin=f"CACHE:{cached.get('producer_name') or 'evidence'}"),
                            ]})
                            cached_visual_ids.add(file_id)
            prepared.append((file_id, profile, outcome.cache_artifacts))
        has_images = any(profile.modality == "image" for _, profile, _ in prepared)
        batch_size = min(configured_batch, 8) if has_images else configured_batch
        saved = []
        for batch_index, start in enumerate(range(0, len(prepared), batch_size), 1):
            batch = prepared[start:start + batch_size]
            event = {"model_profile_id": task["model_profile_id"], "taxonomy_id": taxonomy["taxonomy_id"],
                     "batch_index": batch_index, "batch_count": (len(prepared) + batch_size - 1) // batch_size,
                     "file_count": len(batch)}
            self.repository.append_event(task_id, "AI_CLASSIFY_BATCH_STARTED", event)
            try:
                results = self.gateway.classify_batch(task_id=task_id, profile_id=task["model_profile_id"],
                    items=[(profile, paths) for _, profile, paths in batch], taxonomy=taxonomy, policy=taxonomy["policy"],
                    vision_refresh_file_ids={file_id for file_id, _, _ in batch if file_id not in cached_visual_ids})
                expected = {file_id for file_id, _, _ in batch}
                by_id = {item.get("file_id"): item for item in results if isinstance(item, dict)}
                if set(by_id) != expected:
                    raise ModelTransportError("MODEL_BATCH_CONTEXT_MISMATCH")
                normalized = []
                for file_id, profile, _ in batch:
                    result = dict(by_id[file_id])
                    visual = result.pop("visual_description", None)
                    if profile.modality == "image":
                        if not isinstance(visual, str) or not visual.strip():
                            raise ModelTransportError("VISION_DESCRIPTION_MISSING")
                        profile, evidence_id = self.repository.append_model_evidence(file_id,
                            text_value=visual.strip(), model_profile_id=task["model_profile_id"],
                            prompt_version="classification-batch-v1")
                        result["evidence_ids"] = list(dict.fromkeys([*result.get("evidence_ids", []), evidence_id]))
                    normalized.append((file_id, profile, result))
                for file_id, profile, result in normalized:
                    saved.append(self.classifications.classify(task_id=task_id, file_id=file_id,
                        taxonomy=taxonomy, profile=profile, model_callback=lambda _payload, value=result: value))
            except Exception as exc:
                self.repository.append_event(task_id, "AI_CLASSIFY_BATCH_FAILED", {**event,
                    "code": getattr(exc, "code", str(exc))})
                raise
            self.repository.append_event(task_id, "AI_CLASSIFY_BATCH_COMPLETED", event)
        self.repository.refresh_counters(task_id)
        return saved
