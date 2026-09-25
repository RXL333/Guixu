from __future__ import annotations

import os
import sys
from pathlib import Path

from guixu.api.app import create_app
from guixu.domain.profiles import Coverage, Evidence, EvidenceLocator, FileProfile, ParseOutcome


class FakeVisionGateway:
    def classify_batch(self, **kwargs):
        return [{
            "file_id": profile.file_id,
            "taxonomy_id": kwargs["taxonomy"]["taxonomy_id"],
            "category_id": "topic.network",
            "abstain": False,
            "model_score": 0.98,
            "evidence_ids": [profile.evidence[0].id],
            "reason": "按授权的视觉证据分类。",
            "visual_description": f"第 {index} 张测试图中的街道与建筑。",
            "tags": [],
            "warnings": [],
        } for index, (profile, _) in enumerate(kwargs["items"])]


def main() -> None:
    project_root, data_dir = Path(sys.argv[1]), Path(sys.argv[2])
    task_id, taxonomy_id = sys.argv[3:5]
    crash_after = int(sys.argv[5])
    app = create_app(project_root=project_root, data_dir=data_dir, session_token="analysis-crash-child")
    gateway = FakeVisionGateway()
    app.state.ai_classifier.gateway = gateway

    def parser_cache_hit(path: Path, file_id: str, preset: str = "standard", cancel_event=None):
        profile = FileProfile(
            file_id=file_id,
            modality="image",
            metadata={"format": "JPEG"},
            evidence=[Evidence(id=f"meta-{file_id}", kind="metadata", text="JPEG image",
                               locator=EvidenceLocator(), quality="high", origin="test-parser")],
            coverage=Coverage(mode="full"),
            parser_version="phase-n-crash-fixture",
        )
        return ParseOutcome(status="ready", profile=profile, cache_artifacts=[str(path)])

    app.state.parsing.runner.parse = parser_cache_hit
    original_append = app.state.repository.append_model_evidence
    persisted = 0

    def persist_evidence_then_crash(*args, **kwargs):
        nonlocal persisted
        result = original_append(*args, **kwargs)
        persisted += 1
        if persisted == crash_after:
            os._exit(91)
        return result

    app.state.repository.append_model_evidence = persist_evidence_then_crash
    taxonomy = app.state.taxonomies.get(task_id, taxonomy_id)
    app.state.ai_classifier.classify_taxonomy(task_id, taxonomy)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
