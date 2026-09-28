"""Real local Qwen first-analysis smoke using only generated test images."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from guixu.api.app import create_app  # noqa: E402


def expect_ok(response, label: str):
    if response.status_code // 100 != 2:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        raise RuntimeError(f"{label}: HTTP {response.status_code} {error}")
    return response.json()["data"]


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    fixture_dir = ROOT / "artifacts" / "test-workspaces" / "phase-n-datasets" / "dataset-a-images"
    fixtures = sorted(fixture_dir.glob("image-*.jpg"))[:3]
    if len(fixtures) != 3:
        raise RuntimeError("THREE_IMAGE_FIXTURE_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="guixu-local-qwen-preview-") as raw:
        temp = Path(raw)
        source = temp / "source"
        source.mkdir()
        for fixture in fixtures:
            shutil.copy2(fixture, source / fixture.name)
        before = {path.name: checksum(path) for path in source.iterdir()}

        token = "local-qwen-preview-smoke"
        app = create_app(project_root=ROOT, data_dir=temp / "data", session_token=token, allow_typed_grants=True)
        profile = app.state.models.create({
            "name": "Local Qwen smoke", "provider": "qwen_local", "runtime": "ollama",
            "base_url": "http://127.0.0.1:11434/v1", "model_id": "qwen3-vl:4b-instruct",
            "trust_scope": "loopback", "options": {"thinking_mode": "server_default", "timeout_seconds": 120,
                                                 "max_concurrency": 1, "batch_size": 20}, "enabled": True,
        })
        capabilities = app.state.models.probe(profile["id"])
        if any(capabilities[key]["status"] != "supported" for key in ("text", "vision")):
            raise RuntimeError("LOCAL_QWEN_CAPABILITY_UNAVAILABLE")
        import os
        if os.environ.get("GUIXU_TEST_DIAG_SHAPE") == "1":
            original_call = app.state.model_gateway._call

            def diagnostic_call(task_id, model, purpose, messages, **kwargs):
                response = original_call(task_id, model, purpose, messages, **kwargs)
                if purpose in {"taxonomy_planner", "classification_batch", "repair"}:
                    stripped = response.content.lstrip()
                    try:
                        json.loads(response.content)
                        parse_error = None
                    except ValueError as exc:
                        parse_error = {"message": getattr(exc, "msg", str(exc)), "position": getattr(exc, "pos", None)}
                    try:
                        parsed = json.loads(response.content)
                        root_keys = sorted(parsed) if isinstance(parsed, dict) else [type(parsed).__name__]
                        child_shape = {key: (sorted(value) if isinstance(value, dict) else type(value).__name__)
                                       for key, value in parsed.items()} if isinstance(parsed, dict) else {}
                    except ValueError:
                        root_keys = []
                        child_shape = {}
                    print(json.dumps({"purpose": purpose, "length": len(response.content),
                                      "first_char": stripped[:1], "last_char": stripped[-1:],
                                      "starts_fence": stripped.startswith("```"),
                                      "has_categories": '"categories"' in response.content,
                                      "parse_error": parse_error, "root_keys": root_keys,
                                      "child_shape": child_shape}, ensure_ascii=False))
                return response

            app.state.model_gateway._call = diagnostic_call
        headers = {"X-Guixu-Session": token}
        with TestClient(app) as client:
            grant = expect_ok(client.post("/api/v1/dev/grants", headers=headers, json={
                "path": str(source), "purpose": "source",
            }), "grant")["grant_id"]
            conversation = expect_ok(client.post("/api/v1/conversations", headers=headers, json={
                "title": "Local Qwen preview smoke", "model_profile_id": profile["id"], "scope_grant": grant,
            }), "conversation")
            result = expect_ok(client.post(f"/api/v1/conversations/{conversation['id']}/turns",
                                           headers=headers, json={
                "content": "请按照图片内容分类，分类目录名称全部使用中文。",
                "acknowledge_privacy": True,
            }), "first analysis")
            plan = result["plan_version"]
            preview = expect_ok(client.get(
                f"/api/v1/conversations/{conversation['id']}/plan-versions/{plan['id']}/preview",
                headers=headers), "preview")
            candidates = [item for item in preview["operations"]
                          if item["action"] in {"skip", "noop"} and item.get("suggested_category_id")
                          and not item.get("abstain")]
            if not candidates:
                raise RuntimeError("NO_REVIEWABLE_LOCAL_QWEN_SUGGESTION")
            context = expect_ok(client.get(f"/api/v1/conversations/{conversation['id']}/context",
                                           headers=headers), "context")
            reviewed_version = expect_ok(client.post(
                f"/api/v1/conversations/{conversation['id']}/plan-versions/{plan['id']}/confirm-suggestions",
                headers=headers, json={"expected_context_revision": context["context_revision"],
                                       "file_ids": [candidates[0]["file_id"]]}), "review suggestion")
            reviewed_preview = expect_ok(client.get(
                f"/api/v1/conversations/{conversation['id']}/plan-versions/{reviewed_version['id']}/preview",
                headers=headers), "reviewed preview")
            reviewed_operation = next(item for item in reviewed_preview["operations"]
                                      if item["file_id"] == candidates[0]["file_id"])
            if reviewed_operation["action"] not in {"move", "copy"}:
                raise RuntimeError("REVIEW_DID_NOT_CREATE_FILE_OPERATION")
            with app.state.database.engine.connect() as connection:
                calls = [dict(row) for row in connection.execute(text(
                    "SELECT purpose,response_status,error_code FROM model_calls ORDER BY created_at,id"
                )).mappings()]
                plan_count = connection.execute(text("SELECT COUNT(*) FROM conversation_plan_versions")).scalar_one()
                planned_count = connection.execute(text("SELECT COUNT(*) FROM operations WHERE state='PLANNED'")).scalar_one()
                executed_count = connection.execute(text("SELECT COUNT(*) FROM operations WHERE state!='PLANNED'")).scalar_one()
                actions = [dict(row) for row in connection.execute(text(
                    "SELECT action,COUNT(*) AS count FROM operations GROUP BY action ORDER BY action"
                )).mappings()]
                categories = [dict(row) for row in connection.execute(text(
                    "SELECT category_id,name FROM categories ORDER BY category_id"
                )).mappings()]
                review_bands = [dict(row) for row in connection.execute(text(
                    "SELECT review_band,COUNT(*) AS count FROM classifications GROUP BY review_band ORDER BY review_band"
                )).mappings()]
            after = {path.name: checksum(path) for path in source.iterdir()}
            if before != after or executed_count:
                raise RuntimeError("DISK_CHANGED_BEFORE_APPROVAL")
            if any(item["category_id"] in {"stable-id", "meaningful_unique_lowercase_id", "example-id"}
                   for item in categories):
                raise RuntimeError("PLACEHOLDER_CATEGORY_IN_PLAN")
            payload = {
                "status": "PASSED", "test_type": "REAL_LOCAL_QWEN_FIRST_PREVIEW",
                "model_id": profile["model_id"], "input_file_count": len(before),
                "plan_status": plan["status"], "plan_count": plan_count,
                "planned_operation_count": planned_count, "executed_operation_count": executed_count,
                "actions": actions, "categories": categories, "review_bands": review_bands,
                "reviewed_version_number": reviewed_version["version_number"],
                "reviewed_action": reviewed_operation["action"],
                "reviewed_target_path": reviewed_operation["target_path"],
                "source_unchanged": True,
                "model_calls": calls,
            }
            report = ROOT / "artifacts" / "reports" / "phase-n-local-qwen-first-preview.json"
            report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
