from __future__ import annotations

import re
from typing import Any

from guixu.application.model_gateway import ModelGateway
from guixu.application.parsing import ParsingService
from guixu.application.taxonomies import TaxonomyService
from guixu.infrastructure.db.repository import TaskRepository


class TaxonomyPlanningError(ValueError):
    pass


_PATH_LIKE = re.compile(r"(?:^[A-Za-z]:[\\/]|[\\/]{2}|\.\.[\\/]|[<>:\"|?*])")


class AITaxonomyPlanner:
    """Build draft taxonomies without local semantic category decisions."""

    def __init__(self, repository: TaskRepository, parsing: ParsingService,
                 taxonomies: TaxonomyService, gateway: ModelGateway) -> None:
        self.repository = repository
        self.parsing = parsing
        self.taxonomies = taxonomies
        self.gateway = gateway

    def plan_task(self, task_id: str) -> list[dict[str, Any]]:
        task = self.repository.get(task_id)
        source = task["settings"]["classification_source"]
        request = task["classification_request"]
        if source == "fixed_categories":
            nodes = self._fixed_nodes(request.get("fixed_tree"))
            drafts = [self._save(task, scope, nodes, "fixed", {"classification_source": source})
                      for scope in self.repository.list_scopes(task_id)]
            self.repository.append_event(task_id, "USER_TAXONOMY_DRAFTED", {"scope_count": len(drafts)})
            self.repository.mark_taxonomy_review(task_id)
            return drafts

        template = task.get("template_snapshot") or {}
        guidance = self._template_guidance(template) if source == "template" else None
        drafts = []
        for scope in self.repository.list_scopes(task_id):
            profiles = []
            for file_id in self.repository.eligible_file_ids(task_id, scope["id"]):
                outcome = self.parsing.parse(task_id, file_id, task["settings"]["analysis_preset"])
                profiles.append((outcome.profile, outcome.cache_artifacts))
            representative = profiles[: self._sample_limit(task["settings"]["analysis_preset"])]
            payload = {
                "classification_source": source,
                "user_instructions": request.get("user_instructions", ""),
                "template_guidance": guidance,
                "organization_strategy": task["settings"]["organization_strategy"],
                "constraints": {
                    "max_depth": task["settings"]["max_depth"],
                    "max_siblings": task["settings"]["max_siblings"],
                    "max_nodes": task["settings"]["max_nodes_per_scope"],
                },
                "file_count": len(profiles),
                "modality_distribution": self._modality_distribution(profiles),
                "privacy": "Only supplied minimized evidence and controlled derivatives may be used.",
            }
            self.repository.append_event(task_id, "AI_PLANNER_STARTED", {
                "model_profile_id": task["model_profile_id"], "scope_id": scope["id"],
                "representative_count": len(representative),
            })
            try:
                result = self.gateway.plan_taxonomy(
                    task_id=task_id, profile_id=task["model_profile_id"], profiles=representative, request=payload
                )
                nodes, rationale = self._ai_nodes(result)
                draft = self._save(task, scope, nodes, "template" if source == "template" else "auto", {
                    "classification_source": source,
                    "template_key": request.get("template_key") if source == "template" else None,
                    "template_version": template.get("version") if template else None,
                    "user_instructions": request.get("user_instructions", ""),
                    "planner_rationale": rationale,
                })
            except Exception as exc:
                self.repository.append_event(task_id, "AI_PLANNER_FAILED", {
                    "model_profile_id": task["model_profile_id"], "scope_id": scope["id"],
                    "code": getattr(exc, "code", str(exc)),
                })
                raise
            self.repository.append_event(task_id, "AI_PLANNER_COMPLETED", {
                "model_profile_id": task["model_profile_id"], "scope_id": scope["id"],
                "taxonomy_id": draft["taxonomy_id"], "node_count": len(nodes),
            })
            drafts.append(draft)
        self.repository.mark_taxonomy_review(task_id)
        return drafts

    def _save(self, task: dict[str, Any], scope: dict[str, Any], nodes: list[dict[str, Any]],
              source: str, policy: dict[str, Any]) -> dict[str, Any]:
        return self.taxonomies.save_draft(
            task["id"], scope["id"], nodes, source,
            max_depth=task["settings"]["max_depth"], max_siblings=task["settings"]["max_siblings"],
            max_nodes=task["settings"]["max_nodes_per_scope"], policy=policy,
        )

    @staticmethod
    def _sample_limit(preset: str) -> int:
        return {"fast": 12, "standard": 32, "deep": 48}[preset]

    @staticmethod
    def _modality_distribution(profiles) -> dict[str, int]:
        result: dict[str, int] = {}
        for profile, _ in profiles:
            result[profile.modality] = result.get(profile.modality, 0) + 1
        return result

    @staticmethod
    def _template_guidance(template: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": template.get("name"), "description": template.get("description"),
            "planner_guidance": template.get("planner_guidance") or template.get("description"),
            "classifier_guidance": template.get("classifier_guidance") or template.get("safety_notes", []),
            "suggested_categories": [
                {"name": node.get("name"), "description": node.get("definition", {}).get("include", "")}
                for node in template.get("nodes", [])
            ],
            "examples": template.get("examples", {}),
        }

    @classmethod
    def _ai_nodes(cls, result: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        categories = result.get("categories")
        if not isinstance(categories, list) or not categories:
            raise TaxonomyPlanningError("PLANNER_SCHEMA_INVALID")
        nodes = []
        for item in categories:
            if not isinstance(item, dict):
                raise TaxonomyPlanningError("PLANNER_SCHEMA_INVALID")
            category_id, name = item.get("category_id"), item.get("name")
            if not isinstance(category_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,95}", category_id):
                raise TaxonomyPlanningError("PLANNER_CATEGORY_ID_INVALID")
            if not isinstance(name, str) or not 1 <= len(name) <= 60 or _PATH_LIKE.search(name):
                raise TaxonomyPlanningError("PLANNER_PATH_FORBIDDEN")
            description = str(item.get("description", "AI 根据内容语义选择此类别。"))[:500]
            criteria = str(item.get("selection_criteria", description))[:300]
            nodes.append({"category_id": category_id, "parent_id": item.get("parent_id"), "name": name,
                "selectable": bool(item.get("selectable", True)), "definition": {
                    "include": description or "AI 根据内容语义选择此类别。",
                    "exclude": "内容证据不足或更符合其他已批准类别。",
                    "evidence_required_any": ["extracted_text", "ocr", "visual_caption", "transcript", "subtitle", "user_context"],
                    "tie_breaker": criteria or "选择内容证据最充分的类别；不确定时 abstain。"},
                "is_fallback": False})
        return nodes, str(result.get("rationale", ""))[:2000]

    @classmethod
    def _fixed_nodes(cls, fixed_tree: Any) -> list[dict[str, Any]]:
        if not isinstance(fixed_tree, dict) or not isinstance(fixed_tree.get("categories"), list):
            raise TaxonomyPlanningError("FIXED_TREE_INVALID")
        nodes, _ = cls._ai_nodes({"categories": fixed_tree["categories"]})
        return nodes
