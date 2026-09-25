from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from guixu.application.model_gateway import ModelGateway  # noqa: E402
from guixu.application.models import ModelProfileService  # noqa: E402
from guixu.application.post_execution import PostExecutionConversationService  # noqa: E402
from guixu.application.privacy import PrivacyService  # noqa: E402
from guixu.domain.privacy import scope_hash  # noqa: E402
from guixu.infrastructure.filesystem.identity import read_identity  # noqa: E402
from guixu.infrastructure.models.credentials import WindowsCredentialStore  # noqa: E402


def load_fixture_builder():
    path = ROOT / "backend" / "tests" / "integration" / "test_post_execution_conversation.py"
    spec = importlib.util.spec_from_file_location("post_execution_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("FIXTURE_BUILDER_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_service


def enabled_deepseek() -> dict:
    app_db = Path.home() / "AppData" / "Local" / "Guixu" / "app.sqlite3"
    connection = sqlite3.connect(app_db)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM model_profiles WHERE enabled=1 AND provider='deepseek' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise RuntimeError("DEEPSEEK_PROFILE_UNAVAILABLE")
    return dict(row)


def main() -> int:
    output = Path(os.environ.get(
        "GUIXU_SMOKE_OUTPUT",
        ROOT / "artifacts" / "test-workspaces" / "post-execution-deepseek",
    ))
    output.mkdir(parents=True, exist_ok=True)
    make_service = load_fixture_builder()
    database, conversations, _, conversation_id, _, round1, file_ids, workspace, _ = make_service(
        ROOT, output, building_count=10, other_count=10
    )
    profile = enabled_deepseek()
    credential_store = WindowsCredentialStore()
    if not credential_store.has(profile["id"]):
        raise RuntimeError("DEEPSEEK_SECRET_UNAVAILABLE")

    # Replace the tiny test bytes with valid, project-generated images. The existing
    # FileProfile evidence deliberately remains unchanged so this run proves reuse.
    for index, path in enumerate(sorted(workspace.rglob("*.jpg"))):
        label = "BUILDING NIGHT" if "building" in path.name and index < 2 else (
            "BUILDING DAY" if "building" in path.name else "LANDSCAPE DAY"
        )
        image = Image.new("RGB", (480, 270), "#101d35" if "NIGHT" in label else "#7bb9e8")
        draw = ImageDraw.Draw(image)
        draw.rectangle((25, 25, 455, 245), outline="white", width=4)
        draw.text((145, 125), label, fill="white")
        image.save(path, format="JPEG")
        identity = read_identity(path)
        file_id = file_ids[path.name]
        with database.begin() as connection:
            connection.execute(text("""
                UPDATE files SET sha256=:sha,size_bytes=:size,mtime_ns=:mtime,updated_at=:now WHERE id=:file
            """), {"sha": identity.sha256, "size": identity.size_bytes, "mtime": identity.mtime_ns,
                    "now": profile["updated_at"], "file": file_id})
            connection.execute(text("""
                UPDATE conversation_files SET first_seen_fingerprint=:sha,current_fingerprint=:sha,
                  current_size_bytes=:size,current_mtime_ns=:mtime WHERE conversation_id=:conversation AND file_id=:file
            """), {"sha": identity.sha256, "size": identity.size_bytes, "mtime": identity.mtime_ns,
                    "conversation": conversation_id, "file": file_id})

    file_snapshot = {
        file_ids[path.name]: (path, read_identity(path).sha256)
        for path in workspace.rglob("*.jpg")
    }
    disk_file_count_before = sum(1 for path in workspace.rglob("*.jpg") if path.is_file())

    columns = [
        "id", "name", "provider", "runtime", "base_url", "model_id", "secret_ref",
        "capabilities_json", "options_json", "trust_scope", "enabled", "revision", "created_at", "updated_at",
    ]
    with database.begin() as connection:
        connection.execute(text("DELETE FROM model_profiles WHERE id='model-1'"))
        names = ",".join(columns)
        values = ",".join(f":{name}" for name in columns)
        connection.execute(text(f"INSERT INTO model_profiles({names}) VALUES({values})"), {name: profile[name] for name in columns})
        task_id = connection.execute(text("SELECT id FROM tasks LIMIT 1")).scalar_one()
        connection.execute(text("UPDATE tasks SET model_profile_id=:profile,model_snapshot_json=:snapshot WHERE id=:task"), {
            "profile": profile["id"], "snapshot": json.dumps({"id": profile["id"], "name": profile["name"]}, ensure_ascii=False),
            "task": task_id,
        })
        connection.execute(text("UPDATE conversations SET model_profile_id=:profile WHERE id=:conversation"), {
            "profile": profile["id"], "conversation": conversation_id,
        })
        connection.execute(text("UPDATE conversation_contexts SET model_profile_id=:profile WHERE conversation_id=:conversation"), {
            "profile": profile["id"], "conversation": conversation_id,
        })

    privacy = PrivacyService(database)
    budget = {"max_calls": 10, "max_input_tokens": 100000, "max_output_tokens": 20000, "max_cost_micros": None}
    data_types = ["derivative_images"]
    task = database.engine.connect().execute(text("SELECT revision FROM tasks WHERE id=:task"), {"task": task_id}).first()
    privacy.grant(task_id, profile["id"], data_types, budget, scope_hash(profile["id"], data_types, budget), int(task[0]), True)
    gateway = ModelGateway(database, ModelProfileService(database, credential_store), privacy)
    original = conversations.get_context(conversation_id)
    service = PostExecutionConversationService(
        database=database,
        conversations=conversations,
        tasks=database and __import__("guixu.infrastructure.db.repository", fromlist=["TaskRepository"]).TaskRepository(database),
        journal=__import__("guixu.infrastructure.db.operation_journal", fromlist=["SqliteOperationJournal"]).SqliteOperationJournal(database),
        coordinator=None,
        parsing=None,
        evaluator=gateway.evaluate_refinement,
    )
    # Reuse the fixture's production coordinator/journal wiring while replacing only the evaluator.
    from guixu.application.coordinator import TaskCoordinator
    from guixu.application.operations import OperationService
    from guixu.application.parsing import ParsingService
    from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
    from guixu.infrastructure.db.repository import TaskRepository
    tasks = TaskRepository(database)
    journal = SqliteOperationJournal(database)
    service.tasks = tasks
    service.journal = journal
    service.coordinator = TaskCoordinator(tasks, journal, OperationService(tasks, journal))
    service.parsing = ParsingService(tasks, output / "cache")

    instruction = "建筑里的夜景放到风景，其他不要动。"
    conversations.append_message(conversation_id, "USER", instruction)
    prepared = service.prepare_refinement(conversation_id, user_message=instruction)
    candidate_file_ids = set(prepared["affected_scope"]["candidate_file_ids"])
    version = prepared["plan_version"]
    context = conversations.get_context(conversation_id)
    service.approve(conversation_id, version["id"], expected_context_revision=context["context_revision"],
                    plan_hash=version["plan_hash"], authorization={"kind": "real-smoke"})
    executed = service.execute(conversation_id, version["id"], expected_context_revision=context["context_revision"],
                               plan_hash=version["plan_hash"])
    unaffected_file_ids = set(file_snapshot) - candidate_file_ids
    for file_id in unaffected_file_ids:
        original_path, original_sha256 = file_snapshot[file_id]
        if not original_path.is_file() or read_identity(original_path).sha256 != original_sha256:
            raise RuntimeError(f"UNRELATED_FILE_CHANGED:{file_id}")
    disk_file_count_after = sum(1 for path in workspace.rglob("*.jpg") if path.is_file())
    if disk_file_count_after != disk_file_count_before:
        raise RuntimeError("DISK_FILE_COUNT_CHANGED")
    with database.engine.connect() as connection:
        calls = [dict(row) for row in connection.execute(text("""
            SELECT purpose,response_status,input_tokens,output_tokens,latency_ms,error_code
            FROM model_calls ORDER BY created_at
        """)).mappings()]
    result = {
        "status": "PASSED",
        "profile_id": profile["id"],
        "model_id": profile["model_id"],
        "conversation_id": conversation_id,
        "baseline_round_id": round1["id"],
        "context_revision_before": original["context_revision"],
        "affected_scope": prepared["affected_scope"],
        "metrics": prepared["metrics"],
        "unaffected_files_unchanged": len(unaffected_file_ids),
        "disk_file_count_before": disk_file_count_before,
        "disk_file_count_after": disk_file_count_after,
        "plan_kind": version["plan_kind"],
        "execution_round": executed["execution_round"]["round_number"],
        "execution_status": executed["execution_round"]["status"],
        "model_calls": calls,
        "conversation_status": conversations.get(conversation_id)["status"],
    }
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
