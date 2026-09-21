from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path

import psutil

from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.scanner import Scanner


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "artifacts" / "test-workspaces" / "phase-08-10000"
DATA_DIR = ROOT / "artifacts" / "runtime-phase-08-performance"
PERF_RESULT = ROOT / "artifacts" / "reports" / "phase-08-performance.json"


def percentile(values: list[float], percentile_value: float) -> float:
    values = sorted(values)
    position = min(len(values) - 1, math.ceil(percentile_value * len(values)) - 1)
    return values[position]


def main() -> None:
    if PERF_RESULT.exists():
        raise SystemExit(f"refusing to overwrite existing result: {PERF_RESULT}")
    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    if any(BENCHMARK_ROOT.iterdir()):
        raise SystemExit("10,000-file benchmark root is not empty")
    for index in range(10_000):
        (BENCHMARK_ROOT / f"metadata-{index:05d}.txt").write_text(f"fixture {index}\n", encoding="utf-8")

    settings = TaskSettings(scan_mode="current_only", operation_mode="report_only")
    process = psutil.Process()
    rss_before = process.memory_info().rss
    started = time.perf_counter(); cold = Scanner().scan(BENCHMARK_ROOT, settings); cold_seconds = time.perf_counter() - started
    started = time.perf_counter(); warm = Scanner().scan(BENCHMARK_ROOT, settings); warm_seconds = time.perf_counter() - started
    rss_after_scan = process.memory_info().rss
    assert len(cold.files) == len(warm.files) == 10_000

    database = Database(DATA_DIR / "app.sqlite3", ROOT / "contracts" / "database.sql")
    database.initialize()
    repository = TaskRepository(database)
    task = repository.create("10k metadata benchmark", settings, {"user_instructions":"性能测试"})
    started = time.perf_counter()
    revision = repository.begin_scan(task["id"], task["revision"])
    assert revision == 2
    repository.store_scan(task["id"], cold.scopes, cold.files, cold.warnings, settings.operation_mode)
    persisted_seconds = time.perf_counter() - started
    latencies = []
    for offset in range(0, 5_000, 100):
        started = time.perf_counter(); items, total = repository.list_files(task["id"], 100, offset); latencies.append((time.perf_counter() - started) * 1000)
        assert len(items) == 100 and total == 10_000
    rss_after_database = process.memory_info().rss
    database.close()

    performance = {
        "environment": {"platform": "Windows", "python": "3.12", "logical_cpu_count": psutil.cpu_count(),
                        "memory_total_bytes": psutil.virtual_memory().total, "storage": "project workspace volume"},
        "metadata_scan": {"files": 10_000, "bytes": sum(item.size_bytes for item in cold.files),
                          "cold_seconds": cold_seconds, "warm_seconds": warm_seconds,
                          "persisted_scan_seconds": persisted_seconds},
        "list_pagination": {"rows_read": 5_000, "page_size": 100, "requests": len(latencies),
                            "median_ms": statistics.median(latencies), "p95_ms": percentile(latencies, .95),
                            "max_ms": max(latencies)},
        "process_rss_bytes": {"before": rss_before, "after_scan": rss_after_scan, "after_database": rss_after_database},
        "model_service_memory": None,
        "notes": ["OS cache state is approximated by first and immediate second scan.",
                  "Model service memory is unavailable because no authorized real service was configured."],
    }
    PERF_RESULT.write_text(json.dumps(performance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"performance": performance}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
