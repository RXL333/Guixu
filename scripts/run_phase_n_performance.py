"""Repeatable backend performance benchmark.

Single-shot timings are not usable as a release signal: earlier runs of this script
recorded the same 5,000-file attach path at anything from 1.3 s to 12.4 s, which says
more about disk and antivirus state than about the code. Every stage is therefore
sampled `--repeat` times against a freshly created database, and reported as a
distribution rather than a lone number.

Each repeat uses its own data directory on purpose. The scenario being measured is a
first open of a large conversation, so warming the database between repeats would
quietly benchmark a different thing. Those directories are created fresh and never
deleted: a benchmark run is evidence, and a later run must not be able to erase it.

Desktop WebView render time and frame rate are not measured here and stay a separate
acceptance item.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
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

STAGES = (
    "scan_seconds",
    "db_persist_seconds",
    "conversation_attach_seconds",
    "conversation_open_seconds",
    "workspace_projection_seconds",
    "workspace_reconcile_seconds",
    "cache_lookup_mean_ms",
)


def timed(call):
    started = time.perf_counter()
    value = call()
    return value, time.perf_counter() - started


def summarize(samples: list[float]) -> dict[str, object]:
    """Nearest-rank distribution. Below 20 samples p95 degenerates to the maximum."""
    ordered = sorted(samples)
    rank = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "samples": len(ordered),
        "min": round(ordered[0], 4),
        "p50": round(statistics.median(ordered), 4),
        "p95": round(ordered[rank], 4),
        "max": round(ordered[-1], 4),
    }


def run_once(count: int, repeat: int) -> dict[str, object]:
    source = DATASET / str(count)
    settings = TaskSettings(scan_mode="current_only", operation_mode="report_only")
    process = psutil.Process()
    rss_before = process.memory_info().rss
    scan, scan_seconds = timed(lambda: Scanner().scan(source, settings))
    if len(scan.files) != count + 1:
        raise RuntimeError(f"unexpected scan count for {count}: {len(scan.files)}")

    data_dir = Path(tempfile.mkdtemp(prefix=f"{count}-r{repeat}-", dir=RUNTIME))
    database = Database(data_dir / "app.sqlite3", ROOT / "contracts" / "database.sql")
    database.initialize()
    tasks = TaskRepository(database)
    task = tasks.create(f"phase-n-{count}-r{repeat}", settings, {"user_instructions": "性能验收"})

    def persist():
        tasks.begin_scan(task["id"], task["revision"])
        tasks.store_scan(task["id"], scan.scopes, scan.files, scan.warnings, settings.operation_mode)

    _, persist_seconds = timed(persist)
    rows, total = tasks.list_files(task["id"], limit=count + 10, offset=0)
    if total != count + 1:
        raise RuntimeError(f"unexpected persisted count for {count}: {total}")

    conversations = ConversationRepository(database)
    conversation = conversations.create(title=f"{count} 文件性能验收 r{repeat}", scope={
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
    # The dataset is tiny text, so wall-clock alone would hide a cost that scales with
    # file bytes rather than file count. Recording the payload keeps the number honest.
    reconciled_bytes = sum(int(row.get("size_bytes") or 0) for row in rows)

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
    if integrity != "ok":
        raise RuntimeError(f"sqlite integrity_check failed for {count} r{repeat}: {integrity}")
    return {
        "requested_files": count,
        "observed_files": total,
        "data_dir": str(data_dir),
        "scan_seconds": scan_seconds,
        "db_persist_seconds": persist_seconds,
        "conversation_attach_seconds": attach_seconds,
        "conversation_open_seconds": open_seconds,
        "workspace_projection_seconds": workspace_open_seconds,
        "workspace_reconcile_seconds": reconcile_seconds,
        "cache_lookup_mean_ms": statistics.fmean(sample_latencies),
        "reconciled_payload_bytes": reconciled_bytes,
        "rss_delta_bytes": rss_after - rss_before,
        "sqlite_integrity_check": integrity,
    }


def run_size(count: int, repeat: int) -> dict[str, object]:
    runs = [run_once(count, index) for index in range(repeat)]
    stages = {stage: summarize([float(run[stage]) for run in runs]) for stage in STAGES}
    return {
        "requested_files": count,
        "observed_files": runs[0]["observed_files"],
        "repeat": repeat,
        "stages": stages,
        "slowest_stage": max(stages, key=lambda name: stages[name]["p50"]),
        "rss_delta_bytes_max": max(int(run["rss_delta_bytes"]) for run in runs),
        "reconciled_payload_bytes": runs[0]["reconciled_payload_bytes"],
        "mean_file_bytes": int(runs[0]["reconciled_payload_bytes"] / count),
        "sqlite_integrity_check": runs[0]["sqlite_integrity_check"],
        "sample_data_dirs": [run["data_dir"] for run in runs],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=5, help="samples per size (default 5)")
    parser.add_argument("--sizes", type=int, nargs="+", default=[500, 1000, 5000])
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.repeat < 1:
        raise SystemExit("--repeat must be at least 1")

    if not DATASET.is_dir():
        raise SystemExit("phase N datasets are missing; run create_phase_n_datasets.py first")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    results = [run_size(count, args.repeat) for count in args.sizes]
    payload = {
        "schema_version": 2,
        "test_type": "REAL_FILESYSTEM_PERFORMANCE",
        "environment": {
            "platform": "Windows",
            "logical_cpu_count": psutil.cpu_count(),
            "memory_total_bytes": psutil.virtual_memory().total,
        },
        "method": {
            "repeat": args.repeat,
            "cold_database_per_repeat": True,
            "percentiles": "nearest-rank over the per-repeat samples",
            "caveat": "p95 equals the maximum when fewer than 20 samples are taken; "
                      "raise --repeat before quoting p95 as a service level.",
        },
        "results": results,
        "limitations": [
            "Backend storage and reconciliation benchmark; desktop WebView render/FPS is not measured.",
            "Fixtures are small text files, so timings measure per-file overhead, not per-byte "
            "cost. `mean_file_bytes` is recorded per size so the gap is explicit; parsing and "
            "vision decode of real media are not represented at all.",
            "Numbers are from one machine on one filesystem and are not a cross-platform guarantee.",
        ],
    }
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
