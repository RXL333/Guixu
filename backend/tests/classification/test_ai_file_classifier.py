from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from sqlalchemy import text

from guixu.application.ai_file_classifier import AIFileClassifier
from guixu.application.classification import ClassificationService
from guixu.application.models import ModelProfileService
from guixu.application.parsing import ParsingService
from guixu.application.tasks import TaskService
from guixu.application.taxonomies import TaxonomyService
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.filesystem.grants import SourceRegistry


class Secrets:
    def set(self, key, value): return key
    def get(self, key): return None
    def delete(self, key): pass
    def has(self, key): return False


class SemanticBatchGateway:
    def __init__(self):
        self.calls = []

    def classify_batch(self, **kwargs):
        self.calls.append(kwargs)
        taxonomy_id = kwargs["taxonomy"]["taxonomy_id"]
        results = []
        for profile, _ in kwargs["items"]:
            text_value = " ".join([profile.content_summary, *(item.text for item in profile.evidence)])
            if profile.modality == "image":
                category = "visual.warm" if profile.name.startswith("warm") else "visual.cool"
                evidence_ids = []
                visual = "暖色的红色测试图" if category == "visual.warm" else "冷色的蓝色测试图"
            else:
                category = "course.network" if "TCP" in text_value else "course.os"
                evidence_ids = [profile.evidence[0].id]
                visual = None
            result = {"file_id": profile.file_id, "taxonomy_id": taxonomy_id, "category_id": category,
                      "abstain": False, "model_score": 0.96, "evidence_ids": evidence_ids,
                      "reason": "根据文件内容证据归类", "tags": [], "warnings": []}
            if visual:
                result["visual_description"] = visual
            results.append(result)
        return results


def setup_task(project_root: Path, tmp_path: Path, files: dict[str, str | tuple[int, int, int]], nodes: list[dict]):
    source = tmp_path / "source"; source.mkdir()
    for name, content in files.items():
        path = source / name
        if isinstance(content, tuple):
            Image.new("RGB", (20, 20), content).save(path)
        else:
            path.write_text(content, "utf-8")
    database = Database(tmp_path / "app.sqlite3", project_root / "contracts" / "database.sql"); database.initialize()
    model = ModelProfileService(database, Secrets()).create({"name":"Fake AI","provider":"qwen_local",
        "runtime":"openai_compatible","base_url":"http://127.0.0.1:8000/v1","model_id":"fake",
        "trust_scope":"loopback","options":{"thinking_mode":"disabled","timeout_seconds":5,
        "max_concurrency":1,"batch_size":20},"enabled":True})
    repository = TaskRepository(database); registry = SourceRegistry()
    grant = registry.register_typed_directory(str(source), "source")
    settings = TaskSettings(scan_mode="current_only", operation_mode="preview_move", classification_source="auto_plan")
    task_service = TaskService(repository, registry)
    task = task_service.create_task("AI classify", grant.grant_id, None, settings,
        {"user_instructions":"按内容语义整理"}, model["id"], model)
    task_service.start(task["id"], task["revision"])
    scope_id = repository.list_scopes(task["id"])[0]["id"]
    draft = TaxonomyService(database).save_draft(task["id"], scope_id, nodes, "fixed",
        max_depth=2, max_siblings=12, max_nodes=80)
    taxonomy = TaxonomyService(database).approve(task["id"], draft["taxonomy_id"], draft["tree_hash"])
    parsing = ParsingService(repository, tmp_path / "cache")
    classifications = ClassificationService(database, project_root / "contracts" / "schemas" / "classification-result.schema.json")
    gateway = SemanticBatchGateway()
    return database, repository, task, taxonomy, AIFileClassifier(repository, parsing, classifications, gateway), gateway


def node(category_id: str, name: str):
    return {"category_id":category_id, "parent_id":None, "name":name, "selectable":True,
            "definition":{"description":name, "selection_criteria":f"内容属于{name}"}}


def test_same_extension_documents_are_classified_by_content(project_root: Path, tmp_path: Path):
    nodes = [node("course.network", "计算机网络"), node("course.os", "操作系统")]
    db, repo, task, taxonomy, classifier, gateway = setup_task(project_root, tmp_path, {
        "lesson-a.txt":"TCP 三次握手、IP 路由与 Wireshark", "lesson-b.txt":"进程调度、PCB 与虚拟内存"
    }, nodes)
    results = classifier.classify_taxonomy(task["id"], taxonomy)
    assert {item["category_id"] for item in results} == {"course.network", "course.os"}
    assert len(gateway.calls) == 1 and len(gateway.calls[0]["items"]) == 2
    events = [item["event_type"] for item in repo.events(task["id"], 0, 100)]
    assert "AI_CLASSIFY_BATCH_STARTED" in events and "AI_CLASSIFY_BATCH_COMPLETED" in events
    db.close()


def test_all_jpg_flow_uses_visual_descriptions_as_evidence(project_root: Path, tmp_path: Path):
    nodes = [node("visual.warm", "暖色图片"), node("visual.cool", "冷色图片")]
    db, repo, task, taxonomy, classifier, gateway = setup_task(project_root, tmp_path, {
        "warm.jpg":(220, 30, 20), "cool.jpg":(20, 60, 220)
    }, nodes)
    results = classifier.classify_taxonomy(task["id"], taxonomy)
    assert {item["category_id"] for item in results} == {"visual.warm", "visual.cool"}
    assert len(gateway.calls) == 2
    assert all(len(call["items"]) == 1 and call["items"][0][1] for call in gateway.calls)
    with db.engine.connect() as connection:
        profiles = [json.loads(row[0]) for row in connection.execute(text(
            "SELECT profile_json FROM file_profiles WHERE cache_key LIKE '%-vision-%' ORDER BY created_at"
        ))]
    assert len(profiles) == 2
    assert all(any(item["kind"] == "visual_description" for item in profile["evidence"]) for profile in profiles)
    assert repo.advance_after_classification(task["id"])["status"] == "AWAITING_EXECUTION_APPROVAL"
    db.close()
