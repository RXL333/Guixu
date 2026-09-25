from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from guixu.api.app import create_app  # noqa: E402
from guixu.infrastructure.models.credentials import WindowsCredentialStore  # noqa: E402


def enabled_deepseek() -> dict[str, object]:
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
    profile = dict(row)
    if not WindowsCredentialStore().has(str(profile["id"])):
        raise RuntimeError("DEEPSEEK_SECRET_UNAVAILABLE")
    return profile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def insert_profile(app, profile: dict[str, object]) -> None:
    columns = [
        "id", "name", "provider", "runtime", "base_url", "model_id", "secret_ref",
        "capabilities_json", "options_json", "trust_scope", "enabled", "revision", "created_at", "updated_at",
    ]
    with app.state.database.begin() as connection:
        names = ",".join(columns)
        values = ",".join(f":{name}" for name in columns)
        connection.execute(text(f"INSERT INTO model_profiles({names}) VALUES({values})"), {
            name: profile[name] for name in columns
        })


def expect_ok(response, label: str):
    if response.status_code // 100 != 2:
        raise RuntimeError(f"{label}: {response.status_code} {response.text}")
    return response.json()["data"]


def main() -> int:
    first_only = "--first-only" in sys.argv[1:]
    profile = enabled_deepseek()
    fixtures = ROOT / "artifacts" / "test-workspaces" / "phase-n-datasets" / "dataset-a-images"
    report_path = ROOT / "artifacts" / "reports" / (
        "phase-n-real-deepseek-first-execution.json" if first_only else "phase-n-real-deepseek-e2e.json")
    token = "phase-n-real-e2e"
    with tempfile.TemporaryDirectory(prefix="guixu-phase-n-") as temp_name:
        temp = Path(temp_name)
        source = temp / "source"
        source.mkdir()
        selected = sorted(fixtures.glob("image-*.jpg"))[:5]
        for item in selected:
            shutil.copy2(item, source / item.name)
        before = {item.name: sha256(item) for item in source.iterdir()}
        data_dir = temp / "data"
        app = create_app(project_root=ROOT, data_dir=data_dir, session_token=token, allow_typed_grants=True)
        insert_profile(app, profile)
        headers = {"X-Guixu-Session": token}

        with TestClient(app) as client:
            grant = expect_ok(client.post("/api/v1/dev/grants", headers=headers, json={
                "path": str(source), "purpose": "source",
            }), "grant")["grant_id"]
            conversation = expect_ok(client.post("/api/v1/conversations", headers=headers, json={
                "title": "Phase N 真实 E2E", "model_profile_id": profile["id"], "scope_grant": grant,
            }), "conversation")
            first = expect_ok(client.post(f"/api/v1/conversations/{conversation['id']}/turns", headers=headers, json={
                "content": "帮我按照内容整理这些文件，不要分得太细。", "acknowledge_privacy": True,
            }), "first turn")
            v1 = first["plan_version"]
            if first_only:
                target = v1
                v2 = None
                diff = None
            else:
                message = expect_ok(client.post(f"/api/v1/conversations/{conversation['id']}/messages", headers=headers, json={
                    "role": "USER", "content": "建筑单独分类，截图和文档照片分开。",
                    "expected_context_revision": first["context"]["context_revision"],
                }), "revision message")
                revised = expect_ok(client.post(
                    f"/api/v1/conversations/{conversation['id']}/refinements/prepare", headers=headers, json={
                        "user_message": "建筑单独分类，截图和文档照片分开。",
                        "trigger_message_id": message["id"],
                    },
                ), "pre-execution replan")
                v2 = revised["plan_version"]
                target = v2
                diff = expect_ok(client.get(
                    f"/api/v1/conversations/{conversation['id']}/plan-versions/{v2['id']}/diff",
                    headers=headers, params={"from_version_id": v1["id"]},
                ), "plan diff")
            before_approval = {item.name: sha256(item) for item in source.iterdir()}
            if before_approval != before:
                raise RuntimeError("DISK_CHANGED_BEFORE_APPROVAL")
            context = expect_ok(client.get(
                f"/api/v1/conversations/{conversation['id']}/context", headers=headers,
            ), "context")
            expect_ok(client.post(
                f"/api/v1/conversations/{conversation['id']}/plan-versions/{target['id']}/approve",
                headers=headers, json={
                    "expected_context_revision": context["context_revision"], "plan_hash": target["plan_hash"],
                    "authorization": {"kind": "interactive", "surface": "phase-n-real-e2e"},
                },
            ), "approve")
            execution_response = client.post(
                f"/api/v1/conversations/{conversation['id']}/plan-versions/{target['id']}/execute",
                headers=headers, json={
                    "expected_context_revision": context["context_revision"], "plan_hash": target["plan_hash"],
                },
            )
            if execution_response.status_code // 100 != 2:
                with app.state.database.engine.connect() as connection:
                    state = connection.execute(text("""
                        SELECT pv.status AS version_status,p.status AS plan_status,
                          (pv.plan_hash=p.plan_hash) AS version_matches_plan,
                          (a.plan_hash=p.plan_hash) AS approval_matches_plan,
                          a.status AS approval_status,p.approved_task_revision,t.revision AS task_revision
                        FROM conversation_plan_versions pv JOIN plans p ON p.id=pv.plan_id
                        JOIN conversation_plan_approvals a ON a.plan_version_id=pv.id
                        JOIN tasks t ON t.id=p.task_id WHERE pv.id=:version
                    """), {"version": target["id"]}).mappings().first()
                raise RuntimeError(f"execute: {execution_response.status_code} {execution_response.text}; state={dict(state) if state else None}")
            executed = execution_response.json()["data"]
            persisted = expect_ok(client.get(
                f"/api/v1/conversations/{conversation['id']}", headers=headers,
            ), "conversation after execution")
        app.state.database.close()

        restarted = create_app(project_root=ROOT, data_dir=data_dir, session_token=token, allow_typed_grants=True)
        with TestClient(restarted) as client:
            restored = {
                "conversation": expect_ok(client.get(f"/api/v1/conversations/{conversation['id']}", headers=headers), "restart conversation"),
                "messages": expect_ok(client.get(f"/api/v1/conversations/{conversation['id']}/messages", headers=headers), "restart messages"),
                "plans": expect_ok(client.get(f"/api/v1/conversations/{conversation['id']}/plan-versions", headers=headers), "restart plans"),
                "executions": expect_ok(client.get(f"/api/v1/conversations/{conversation['id']}/executions", headers=headers), "restart rounds"),
                "files": expect_ok(client.get(f"/api/v1/conversations/{conversation['id']}/files", headers=headers), "restart files"),
            }
        with restarted.state.database.engine.connect() as connection:
            calls = [dict(row) for row in connection.execute(text("""
                SELECT purpose,response_status,input_tokens,output_tokens,latency_ms,error_code
                FROM model_calls ORDER BY created_at
            """)).mappings()]
        restarted.state.database.close()

        result = {
            "status": "PASSED",
            "test_type": "REAL_DEEPSEEK_REAL_FILESYSTEM_INTEGRATION",
            "model_id": profile["model_id"],
            "input_file_count": len(selected),
            "v1": {"id": v1["id"], "status": "EXECUTED" if first_only else "SUPERSEDED", "plan_hash": v1["plan_hash"]},
            "v2": {"id": v2["id"], "parent": v2["parent_plan_version_id"], "status": v2["status"], "plan_hash": v2["plan_hash"]} if v2 else None,
            "diff_summary": diff.get("summary_counts") if diff else None,
            "pre_approval_disk_unchanged": before_approval == before,
            "execution_round": executed["execution_round"]["round_number"],
            "execution_status": executed["execution_round"]["status"],
            "conversation_status": persisted["status"],
            "restart_counts": {name: len(value) for name, value in restored.items() if isinstance(value, list)},
            "restart_conversation_status": restored["conversation"]["status"],
            "model_calls": calls,
            "secret_recorded": False,
        }
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
