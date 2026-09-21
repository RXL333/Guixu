from __future__ import annotations

import json
from pathlib import Path

from guixu.application.ai_file_classifier import AIFileClassifier
from guixu.application.ai_taxonomy_planner import AITaxonomyPlanner
from guixu.application.classification import ClassificationService
from guixu.application.coordinator import TaskCoordinator
from guixu.application.models import ModelProfileService
from guixu.application.operations import OperationService
from guixu.application.parsing import ParsingService
from guixu.application.tasks import TaskService
from guixu.application.taxonomies import TaxonomyService
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.grants import SourceRegistry


class Secrets:
    def set(self, key, value): return key
    def get(self, key): return None
    def delete(self, key): pass
    def has(self, key): return False


class FakeSemanticAI:
    def plan_taxonomy(self, **kwargs):
        assert len(kwargs["profiles"]) == 10
        return {"categories":[
            {"category_id":"course.network","name":"计算机网络","parent_id":None,
             "description":"网络协议与抓包","selection_criteria":"正文涉及 TCP、IP 或路由","selectable":True},
            {"category_id":"course.os","name":"操作系统","parent_id":None,
             "description":"进程、内存与调度","selection_criteria":"正文涉及 PCB、进程或内存","selectable":True},
        ],"rationale":"十份正文自然分为网络和操作系统两个课程主题"}

    def classify_batch(self, **kwargs):
        taxonomy_id = kwargs["taxonomy"]["taxonomy_id"]; results = []
        for profile, _ in kwargs["items"]:
            content = " ".join([profile.content_summary, *(item.text for item in profile.evidence)])
            category = "course.network" if "TCP" in content else "course.os"
            results.append({"file_id":profile.file_id,"taxonomy_id":taxonomy_id,"category_id":category,
                "abstain":False,"model_score":0.98,"evidence_ids":[profile.evidence[0].id],
                "reason":"AI 根据正文课程主题分类","tags":[],"warnings":[]})
        return results


def test_ten_file_ai_only_pipeline_moves_to_semantic_targets(project_root: Path, tmp_path: Path):
    source = tmp_path / "source"; source.mkdir()
    for index in range(5):
        (source / f"network-{index}.txt").write_text(f"第{index}讲 TCP 三次握手 IP 路由 Wireshark", "utf-8")
        (source / f"system-{index}.txt").write_text(f"第{index}讲 进程 PCB 调度 虚拟内存", "utf-8")
    database = Database(tmp_path / "data" / "app.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    model = ModelProfileService(database, Secrets()).create({"name":"Fixture AI","provider":"qwen_local",
        "runtime":"openai_compatible","base_url":"http://127.0.0.1:8000/v1","model_id":"fixture",
        "trust_scope":"loopback","options":{"thinking_mode":"disabled","timeout_seconds":5,
        "max_concurrency":1,"batch_size":20},"enabled":True})
    repository = TaskRepository(database); registry = SourceRegistry()
    grant = registry.register_typed_directory(str(source), "source")
    settings = TaskSettings(scan_mode="current_only", operation_mode="preview_move",
                            classification_source="auto_plan", analysis_preset="fast")
    tasks = TaskService(repository, registry)
    task = tasks.create_task("10-file AI pipeline", grant.grant_id, None, settings,
                             {"user_instructions":"按课程主题整理"}, model["id"], model)
    tasks.start(task["id"], task["revision"])

    parsing = ParsingService(repository, tmp_path / "cache")
    taxonomies = TaxonomyService(database); fake = FakeSemanticAI()
    draft = AITaxonomyPlanner(repository, parsing, taxonomies, fake).plan_task(task["id"])[0]
    current = repository.get(task["id"])
    taxonomy = taxonomies.approve(task["id"], draft["taxonomy_id"], draft["tree_hash"], current["revision"])
    classifications = ClassificationService(database, project_root / "contracts" / "schemas" / "classification-result.schema.json")
    results = AIFileClassifier(repository, parsing, classifications, fake).classify_taxonomy(task["id"], taxonomy)
    assert len(results) == 10 and {item["category_id"] for item in results} == {"course.network", "course.os"}
    repository.advance_after_classification(task["id"])

    first = repository.list_files(task["id"], limit=1)[0][0]
    current = repository.get(task["id"])
    reviewed = classifications.review_bulk(task["id"], [{"file_id":first["id"],"taxonomy_id":taxonomy["taxonomy_id"],
        "category_id":next(item["category_id"] for item in results if item["file_id"] == first["id"]),
        "decision":"accept","note":"临时目录完整闭环确认"}], current["revision"])
    assert reviewed["applied"] == 1

    journal = SqliteOperationJournal(database); operations = OperationService(repository, journal)
    coordinator = TaskCoordinator(repository, journal, operations)
    plan = operations.compile(task["id"]); current = repository.get(task["id"])
    operations.approve(task["id"], plan.plan_id, plan.plan_hash, current["revision"])
    verified = journal.plan_metadata(plan.plan_id)
    assert verified["approved"] is True and journal.load_plan(plan.plan_id).plan_hash == plan.plan_hash
    coordinator.execute(task["id"], plan.plan_id, plan.plan_hash, current["revision"])

    assert not list(source.glob("*.txt"))
    assert len(list((source / "计算机网络").glob("*.txt"))) == 5
    assert len(list((source / "操作系统").glob("*.txt"))) == 5
    operation_results = journal.operation_results(plan.plan_id)
    assert len(operation_results) == 10 and all(item["state"] == "COMMITTED" for item in operation_results)
    event_types = [item["event_type"] for item in repository.events(task["id"], 0, 200)]
    assert {"AI_PLANNER_STARTED","AI_PLANNER_COMPLETED","AI_CLASSIFY_BATCH_STARTED",
            "AI_CLASSIFY_BATCH_COMPLETED","execution_started","execution_finished"} <= set(event_types)
    assert repository.get(task["id"])["status"] == "COMPLETED"
    database.close()
