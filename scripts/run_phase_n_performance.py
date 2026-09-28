from __future__ import annotations

import json
import shutil
import statistics
import time
from pathlib import Path

import psutil

from guixu.application.post_execution import WorkspaceStateService
from guixu.application.semantic_cache import EvidenceCacheService
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.scanner import Scanner


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "artifacts" / "test-workspaces" / "phase-n-datasets" / "dataset-d-pressure"
RUNTIME = ROOT / "artifacts" / "test-workspaces" / "phase-n-performance"
REPORT = ROOT / "artifacts" / "reports" / "phase-n-performance.json"


def timed(call):
    started = time.perf_counter()
    value = call()
    return value, time.perf_counter() - started


def run_size(count: int) -> dict[str, object]:
    source = DATASET / str(count)
    settings = TaskSettings(scan_mode="current_only", operation_mode="report_only")
    process = psutil.Process()
    rss_before = process.memory_info().rss
    scan, scan_seconds = timed(lambda: Scanner().scan(source, settings))
    if len(scan.files) != count + 1:
        raise RuntimeError(f"unexpected scan count for {count}: {len(scan.files)}")

    data_dir = RUNTIME / str(count)
    database = Database(data_dir / "app.sqlite3", ROOT / "contracts" / "database.sql")
    database.initialize()
    tasks = TaskRepository(database)
    task = tasks.create(f"phase-n-{count}", settings, {"user_instructions": "性能验收"})

    def persist():
        tasks.begin_scan(task["id"], task["revision"])
        tasks.store_scan(task["id"], scan.scopes, scan.files, scan.warnings, settings.operation_mode)

    _, persist_seconds = timed(persist)
    rows, total = tasks.list_files(task["id"], limit=count + 10, offset=0)
    if total != count + 1:
        raise RuntimeError(f"unexpected persisted count for {count}: {total}")

    conversations = ConversationRepository(database)
    conversation = conversations.create(title=f"{count} 文件性能验收", scope={
        "source_root": str(source), "display_name": source.name,
    })
    _, attach_seconds = timed(lambda: conversations.attach_files(
        conversation["id"], [row["id"] for row in rows], use_scanned_identity=True
    ))
    opened, open_seconds = timed(lambda: conversations.list_conversation_files(conversation["id"]))
    if len(opened) != count + 1:
        raise RuntimeError(f"unexpected conversation count for {count}: {len(opened)}")

    workspace = WorkspaceStateService(database, conversations)
    _, workspace_open_seconds = timed(lambda: workspace.current_state(conversation["id"]))
    reconciled, reconcile_seconds = timed(lambda: workspace.sync_workspace_state(conversation["id"]))
    if any(item["state"] != "UNCHANGED" for item in reconciled["sync_events"]):
        raise RuntimeError(f"unexpected external change in {count} dataset")

    cache = EvidenceCacheService(database)
    sample_latencies: list[float] = []
    for row in rows:
        started = time.perf_counter()
        cache.get_valid_evidence(row["id"], str(row.get("sha256") or ""), "VISUAL_DESCRIPTION")
        sample_latencies.append((time.perf_counter() - started) * 1000)
    rss_after = process.memory_info().rss
    with database.engine.connect() as connection:
        integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalar_one()
    database.close()
    return {
        "requested_files": count,
        "observed_files": total,
        "scan_seconds": scan_seconds,
        "db_persist_seconds": persist_seconds,
        "conversation_attach_seconds": attach_seconds,
        "conversation_open_seconds": open_seconds,
        "workspace_projection_seconds": workspace_open_seconds,
        "workspace_reconcile_seconds": reconcile_seconds,
        "cache_lookup_total_seconds": sum(sample_latencies) / 1000,
        "cache_lookup_median_ms": statistics.median(sample_latencies),
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_delta_bytes": rss_after - rss_before,
        "sqlite_integrity_check": integrity,
    }


def main() -> int:
    if not DATASET.is_dir():
        raise SystemExit("phase N datasets are missing; run create_phase_n_datasets.py first")
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir(parents=True)
    results = [run_size(count) for count in (500, 1000, 5000)]
    payload = {
        "schema_version": 1,
        "test_type": "REAL_FILESYSTEM_PERFORMANCE",
        "environment": {
            "platform": "Windows",
            "logical_cpu_count": psutil.cpu_count(),
            "memory_total_bytes": psutil.virtual_memory().total,
        },
        "results": results,
        "limitations": [
            "Backend storage and reconciliation benchmark; desktop WebView render/FPS is not measured.",
            "Generated small text fixtures do not represent large-media decode cost.",
        ],
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
