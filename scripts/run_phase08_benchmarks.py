from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
import uuid
from collections import Counter
from pathlib import Path

import psutil

from guixu.application.tasks import TaskService
from guixu.domain.classification import classify_universal_types
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.grants import SourceRegistry
from guixu.infrastructure.filesystem.scanner import Scanner
from guixu.infrastructure.parsers.registry import ParserRegistry


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / "artifacts" / "test-workspaces" / "phase-08-10000"
DATA_DIR = ROOT / "artifacts" / "runtime-phase-08-performance"
PERF_RESULT = ROOT / "artifacts" / "reports" / "phase-08-performance.json"
GOLD_MANIFEST = ROOT / "artifacts" / "evaluation" / "gold-manifest.json"
SMOKE_RESULT = ROOT / "artifacts" / "evaluation" / "technical-smoke-results.json"


def percentile(values: list[float], percentile_value: float) -> float:
    values = sorted(values)
    position = min(len(values) - 1, math.ceil(percentile_value * len(values)) - 1)
    return values[position]


def verify_fixture(path: Path, expected: str) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(f"fixture hash mismatch: {path}")


def main() -> None:
    for output in (PERF_RESULT, SMOKE_RESULT):
        if output.exists():
            raise SystemExit(f"refusing to overwrite existing result: {output}")
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
    repository = TaskRepository(database); registry = SourceRegistry(); service = TaskService(repository, registry)
    grant = registry.register_typed_directory(str(BENCHMARK_ROOT), "source")
    task = service.create_task("10k metadata benchmark", grant.grant_id, None, settings, {})
    started = time.perf_counter(); service.start(task["id"], task["revision"]); persisted_seconds = time.perf_counter() - started
    latencies = []
    for offset in range(0, 5_000, 100):
        started = time.perf_counter(); items, total = repository.list_files(task["id"], 100, offset); latencies.append((time.perf_counter() - started) * 1000)
        assert len(items) == 100 and total == 10_000
    rss_after_database = process.memory_info().rss
    database.close()

    manifest = json.loads(GOLD_MANIFEST.read_text("utf-8"))
    definition = next(item for item in json.loads((ROOT / "seed" / "templates.json").read_text("utf-8"))["templates"] if item["template_id"] == "universal.types")
    taxonomy = {"taxonomy_id": "phase-08-gold", "nodes": definition["nodes"]}
    actual = []
    parse_statuses = Counter()
    started = time.perf_counter()
    for case in manifest["cases"]:
        path = GOLD_MANIFEST.parent / "fixtures" / case["relative_path"]
        verify_fixture(path, case["sha256"])
        file_id = str(uuid.uuid4())
        outcome = ParserRegistry().parse(path, file_id)
        parse_statuses[outcome.status] += 1
        decision = classify_universal_types(file_id, taxonomy, outcome.profile)
        expected = set(case["acceptable_category_ids"])
        hit = decision["category_id"] in expected if not decision["abstain"] else bool(case["should_abstain"])
        actual.append({"id": case["id"], "status": outcome.status, "category_id": decision["category_id"], "abstain": decision["abstain"], "hit": hit})
    parse_seconds = time.perf_counter() - started
    hits = sum(item["hit"] for item in actual)
    automatic = sum(not item["abstain"] for item in actual)
    smoke = {
        "scope": "deterministic synthetic technical smoke test; not real-world semantic quality",
        "license": manifest["license"], "cases": len(actual), "manifest_hashes_verified": True,
        "accuracy": hits / len(actual), "macro_f1": hits / len(actual),
        "automatic_coverage": automatic / len(actual), "abstain_rate": 1 - automatic / len(actual),
        "parse_statuses": dict(parse_statuses), "elapsed_seconds": parse_seconds,
        "model_calls": 0, "results": actual,
    }
    performance = {
        "environment": {"platform": "Windows", "python": "3.12", "logical_cpu_count": psutil.cpu_count(),
                        "memory_total_bytes": psutil.virtual_memory().total, "storage": "project workspace volume"},
        "metadata_scan": {"files": 10_000, "bytes": sum(item.size_bytes for item in cold.files),
                          "cold_seconds": cold_seconds, "warm_seconds": warm_seconds,
                          "persisted_scan_seconds": persisted_seconds},
        "list_pagination": {"rows_read": 5_000, "page_size": 100, "requests": len(latencies),
                            "median_ms": statistics.median(latencies), "p95_ms": percentile(latencies, .95),
                            "max_ms": max(latencies)},
        "multimodal_batch": {"fixtures": len(actual), "elapsed_seconds": parse_seconds,
                             "parse_statuses": dict(parse_statuses)},
        "process_rss_bytes": {"before": rss_before, "after_scan": rss_after_scan, "after_database": rss_after_database},
        "model_service_memory": None,
        "notes": ["OS cache state is approximated by first and immediate second scan.",
                  "Model service memory is unavailable because no authorized real service was configured."],
    }
    PERF_RESULT.write_text(json.dumps(performance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SMOKE_RESULT.write_text(json.dumps(smoke, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"performance": performance, "smoke_summary": {key: smoke[key] for key in ("cases","accuracy","macro_f1","automatic_coverage","abstain_rate","parse_statuses","elapsed_seconds")}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
