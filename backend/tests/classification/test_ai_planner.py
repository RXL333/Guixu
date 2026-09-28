from __future__ import annotations

import json
from pathlib import Path

import pytest

from guixu.application.ai_taxonomy_planner import AITaxonomyPlanner, TaxonomyPlanningError
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


class FakePlannerGateway:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def plan_taxonomy(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def setup(project_root: Path, tmp_path: Path, *, source="auto_plan", request=None, depth=2):
    folder = tmp_path / "source"; folder.mkdir()
    (folder / "network.txt").write_text("TCP 三次握手 Wireshark IP 路由", "utf-8")
    (folder / "system.txt").write_text("进程 PCB 调度 虚拟内存", "utf-8")
    database = Database(tmp_path / "app.sqlite3", project_root / "contracts" / "database.sql"); database.initialize()
    model = ModelProfileService(database, Secrets()).create({"name":"Fake","provider":"qwen_local","runtime":"openai_compatible",
        "base_url":"http://127.0.0.1:8000/v1","model_id":"fake","trust_scope":"loopback",
        "options":{"thinking_mode":"disabled","timeout_seconds":5,"max_concurrency":1},"enabled":True})
    repository = TaskRepository(database); grants = SourceRegistry(); grant = grants.register_typed_directory(str(folder), "source")
    settings = TaskSettings(scan_mode="current_only", operation_mode="preview_move", classification_source="auto_plan", max_depth=depth)
    service = TaskService(repository, grants)
    task = service.create_task("AI plan", grant.grant_id, None, settings,
                               {"user_instructions": (request or {}).get("user_instructions", "")}, model["id"], model)
    service.start(task["id"], task["revision"])
    if source != "auto_plan":
        legacy_settings = settings.model_dump(mode="json")
        legacy_settings["classification_source"] = source
        snapshot = {}
        if source == "template":
            snapshot = next(item for item in json.loads((project_root / "seed" / "templates.json").read_text("utf-8"))["templates"]
                            if item["template_id"] == (request or {}).get("template_key"))
        with database.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tasks SET settings_json=?,classification_request_json=?,template_snapshot_json=? WHERE id=?",
                (json.dumps(legacy_settings, ensure_ascii=False), json.dumps(request or {}, ensure_ascii=False),
                 json.dumps(snapshot, ensure_ascii=False), task["id"]),
            )
        task = repository.get(task["id"])
    return database, repository, ParsingService(repository, tmp_path / "cache"), TaxonomyService(database), task


def categories():
    return {"categories": [
        {"category_id":"course.network","name":"计算机网络","parent_id":None,"description":"TCP、路由与网络协议", "selection_criteria":"网络正文", "selectable":True},
        {"category_id":"course.os","name":"操作系统","parent_id":None,"description":"进程、内存与调度", "selection_criteria":"系统正文", "selectable":True},
    ], "rationale":"正文呈现两个课程主题"}


def test_auto_plan_uses_semantic_profiles_and_records_events(project_root: Path, tmp_path: Path):
    db, repo, parsing, taxonomies, task = setup(project_root, tmp_path)
    gateway = FakePlannerGateway(categories())
    drafts = AITaxonomyPlanner(repo, parsing, taxonomies, gateway).plan_task(task["id"])
    assert {node["name"] for node in drafts[0]["nodes"]} == {"计算机网络", "操作系统"}
    call = gateway.calls[0]
    assert call["request"]["classification_source"] == "auto_plan"
    summaries = " ".join(profile.content_summary for profile, _ in call["profiles"])
    assert "TCP" in summaries and "虚拟内存" in summaries
    event_types = [item["event_type"] for item in repo.events(task["id"], 0, 100)]
    assert "AI_PLANNER_STARTED" in event_types and "AI_PLANNER_COMPLETED" in event_types
    assert repo.get(task["id"])["status"] == "AWAITING_TAXONOMY_APPROVAL"
    db.close()


def test_conversation_replan_uses_current_category_language(project_root: Path, tmp_path: Path):
    db, repo, parsing, taxonomies, task = setup(project_root, tmp_path)
    db.seed_json("default_settings", {"category_language": "en"})
    with db.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tasks SET classification_request_json=? WHERE id=?",
            (json.dumps({"conversation_id": "conversation-1", "user_instructions": "按内容分类"}), task["id"]),
        )
    gateway = FakePlannerGateway(categories())
    AITaxonomyPlanner(repo, parsing, taxonomies, gateway).plan_task(task["id"])
    assert gateway.calls[0]["request"]["category_language"] == "en"
    db.close()


def test_template_guidance_and_user_instructions_reach_planner(project_root: Path, tmp_path: Path):
    request = {"template_key":"document.academic", "user_instructions":"按照课程分类"}
    db, repo, parsing, taxonomies, task = setup(project_root, tmp_path, source="template", request=request)
    gateway = FakePlannerGateway(categories())
    AITaxonomyPlanner(repo, parsing, taxonomies, gateway).plan_task(task["id"])
    supplied = gateway.calls[0]["request"]
    assert supplied["user_instructions"] == "按照课程分类"
    assert supplied["template_guidance"]["name"] == "学术学习文档"
    db.close()


def test_fixed_categories_are_user_constraints_not_local_rules(project_root: Path, tmp_path: Path):
    fixed = {"categories":[
        {"category_id":"study","name":"学习","parent_id":None,"description":"学习内容"},
        {"category_id":"work","name":"工作","parent_id":None,"description":"工作内容"},
    ]}
    db, repo, parsing, taxonomies, task = setup(project_root, tmp_path, source="fixed_categories", request={"fixed_tree":fixed})
    gateway = FakePlannerGateway(categories())
    draft = AITaxonomyPlanner(repo, parsing, taxonomies, gateway).plan_task(task["id"])[0]
    assert gateway.calls == [] and {node["category_id"] for node in draft["nodes"]} == {"study", "work"}
    db.close()


def test_planner_rejects_path_output_and_depth_overflow(project_root: Path, tmp_path: Path):
    db, repo, parsing, taxonomies, task = setup(project_root, tmp_path, depth=1)
    bad_path = {"categories":[{"category_id":"bad","name":"D:\\Private","parent_id":None}]}
    with pytest.raises(TaxonomyPlanningError, match="PLANNER_PATH_FORBIDDEN"):
        AITaxonomyPlanner(repo, parsing, taxonomies, FakePlannerGateway(bad_path)).plan_task(task["id"])
    deep = {"categories":[{"category_id":"a","name":"A","parent_id":None},
                           {"category_id":"b","name":"B","parent_id":"a"}]}
    with pytest.raises(ValueError, match="TAXONOMY_DEPTH_LIMIT"):
        AITaxonomyPlanner(repo, parsing, taxonomies, FakePlannerGateway(deep)).plan_task(task["id"])
    db.close()


def test_draft_taxonomy_can_be_renamed_added_and_reparented_before_approval(project_root: Path, tmp_path: Path):
    db, repo, parsing, taxonomies, task = setup(project_root, tmp_path)
    draft = AITaxonomyPlanner(repo, parsing, taxonomies, FakePlannerGateway(categories())).plan_task(task["id"])[0]
    edited = [{key: node[key] for key in ("category_id", "parent_id", "name", "selectable", "definition", "is_fallback")}
              for node in draft["nodes"]]
    edited[0]["name"] = "网络课程"
    edited.append({"category_id":"course.lab","name":"实验材料","parent_id":"course.network",
                   "selectable":True,"definition":{"description":"课程实验","selection_criteria":"实验正文"},
                   "is_fallback":False})
    updated = taxonomies.replace_draft(task["id"], draft["taxonomy_id"], draft["tree_hash"], edited,
                                       repo.get(task["id"])["revision"])
    assert updated["taxonomy_id"] != draft["taxonomy_id"]
    assert any(node["name"] == "网络课程" for node in updated["nodes"])
    assert next(node for node in updated["nodes"] if node["category_id"] == "course.lab")["parent_id"] == "course.network"
    assert taxonomies.get(task["id"], draft["taxonomy_id"])["status"] == "superseded"
    db.close()
