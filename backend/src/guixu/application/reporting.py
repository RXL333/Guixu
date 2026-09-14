from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.grants import SourceRegistry


def _csv_safe(value: object) -> str:
    text_value = "" if value is None else str(value)
    if text_value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text_value
    return text_value


class ReportService:
    def __init__(self, database: Database, repository: TaskRepository, registry: SourceRegistry) -> None:
        self.database = database
        self.repository = repository
        self.registry = registry

    def build(self, task_id: str) -> dict[str, Any]:
        counters = self.repository.refresh_counters(task_id)
        task = self.repository.get(task_id)
        with self.database.engine.connect() as connection:
            classes = connection.execute(text(
                "SELECT review_band,count(*) FROM classifications WHERE task_id=:id GROUP BY review_band"
            ), {"id": task_id}).all()
            operations = connection.execute(text("""
                SELECT o.state,count(*) FROM operations o JOIN plans p ON p.id=o.plan_id
                WHERE p.task_id=:id AND p.plan_kind='forward' GROUP BY o.state
            """), {"id": task_id}).all()
            undo_count = int(connection.execute(text("""
                SELECT count(*) FROM operations o JOIN plans p ON p.id=o.plan_id
                WHERE p.task_id=:id AND p.plan_kind='undo'
            """), {"id": task_id}).scalar_one())
            recoverable = int(connection.execute(text("""
                SELECT count(*) FROM operations forward_op
                JOIN plans forward_plan ON forward_plan.id=forward_op.plan_id
                WHERE forward_plan.task_id=:id AND forward_plan.plan_kind='forward'
                  AND forward_op.state='COMMITTED'
                  AND NOT EXISTS (
                    SELECT 1 FROM operations reverse_op JOIN plans reverse_plan ON reverse_plan.id=reverse_op.plan_id
                    WHERE reverse_op.reverses_operation_id=forward_op.id
                      AND reverse_plan.plan_kind='undo' AND reverse_op.state='UNDONE'
                  )
            """), {"id": task_id}).scalar_one())
            forward_plan = connection.execute(text("""
                SELECT id,plan_hash,status FROM plans WHERE task_id=:id AND plan_kind='forward'
                ORDER BY version DESC LIMIT 1
            """), {"id": task_id}).mappings().first()
        states = dict(operations)
        return {
            "task_id": task_id,
            "generated_at": utc_now(),
            "scan_summary": counters,
            "classification_summary": {"bands": dict(classes), "classified": sum(count for _, count in classes)},
            "execution_summary": {"executed_count": states.get("COMMITTED", 0), "states": states,
                                  "plan_id": forward_plan["id"] if forward_plan else None,
                                  "plan_hash": forward_plan["plan_hash"] if forward_plan else None,
                                  "plan_status": forward_plan["status"] if forward_plan else None},
            "undo_summary": {"available": recoverable > 0, "recoverable": recoverable, "planned_items": undo_count},
            "warnings": task["checkpoint"].get("warnings", []),
            "artifacts": [],
        }

    def export(self, task_id: str, export_grant: str, format_name: str, filename: str | None = None) -> dict[str, Any]:
        grant = self.registry.get(export_grant, "export")
        suffix = ".json" if format_name == "json" else ".csv"
        safe_name = filename or f"guixu-report-{task_id[:8]}{suffix}"
        if Path(safe_name).name != safe_name or not safe_name.lower().endswith(suffix):
            raise ValueError("EXPORT_FILENAME_INVALID")
        target = grant.canonical_root / safe_name
        report = self.build(task_id)
        if format_name == "json":
            with target.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        else:
            with target.open("x", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["section", "metric", "value"])
                for section in ("scan_summary", "classification_summary", "execution_summary", "undo_summary"):
                    for metric, value in report[section].items():
                        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
                        writer.writerow([_csv_safe(section), _csv_safe(metric), _csv_safe(serialized)])
                for warning in report["warnings"]:
                    writer.writerow(["warnings", "warning", _csv_safe(warning)])
        return {"format": format_name, "filename": safe_name, "display_path": str(target), "bytes": target.stat().st_size}
