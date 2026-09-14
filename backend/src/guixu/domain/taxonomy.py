from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class TaxonomyError(ValueError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_template(template: dict[str, Any], schema_path: Path) -> None:
    Draft202012Validator(json.loads(schema_path.read_text("utf-8")), format_checker=FormatChecker()).validate(template)
    validate_nodes(template["nodes"], max_depth=3, max_siblings=20, max_nodes=200)


def validate_nodes(nodes: list[dict[str, Any]], *, max_depth: int, max_siblings: int, max_nodes: int) -> dict[str, list[str]]:
    if not nodes or len(nodes) > max_nodes:
        raise TaxonomyError("TAXONOMY_NODE_LIMIT")
    by_id = {node["category_id"]: node for node in nodes}
    if len(by_id) != len(nodes):
        raise TaxonomyError("CATEGORY_ID_DUPLICATE")
    sibling_names = Counter((node.get("parent_id"), str(node["name"]).casefold()) for node in nodes)
    if any(count > 1 for count in sibling_names.values()):
        raise TaxonomyError("CATEGORY_NAME_DUPLICATE")
    sibling_counts = Counter(node.get("parent_id") for node in nodes)
    if any(count > max_siblings for count in sibling_counts.values()):
        raise TaxonomyError("TAXONOMY_SIBLING_LIMIT")
    paths: dict[str, list[str]] = {}

    def resolve(category_id: str, trail: set[str]) -> list[str]:
        if category_id in paths:
            return paths[category_id]
        if category_id in trail:
            raise TaxonomyError("TAXONOMY_CYCLE")
        node = by_id[category_id]
        parent = node.get("parent_id")
        if parent is not None and parent not in by_id:
            raise TaxonomyError("CATEGORY_PARENT_MISSING")
        prefix = resolve(parent, trail | {category_id}) if parent else []
        path = [*prefix, node["name"]]
        if len(path) > max_depth:
            raise TaxonomyError("TAXONOMY_DEPTH_LIMIT")
        paths[category_id] = path
        return path

    for category_id in by_id:
        resolve(category_id, set())
    return paths


def build_taxonomy(template: dict[str, Any], scope_id: str, strategy: str, *, max_depth: int, max_siblings: int, max_nodes: int) -> dict[str, Any]:
    if strategy not in template["compatible_strategies"]:
        raise TaxonomyError("TEMPLATE_STRATEGY_INCOMPATIBLE")
    if max_depth < template["minimum_depth"]:
        raise TaxonomyError("TEMPLATE_DEPTH_INCOMPATIBLE")
    nodes = template["nodes"]
    if strategy == "modality_first" and max_depth == 1:
        mapping = {
            "image": ("modality.image", "图片"), "text": ("modality.text", "文本"),
            "document": ("modality.document", "文档"), "audio": ("modality.audio", "音频"),
            "video": ("modality.video", "视频"), "other": ("modality.other", "其他"),
        }
        nodes = [{"category_id": mapping[item][0], "parent_id": None, "name": mapping[item][1], "selectable": True,
                  "definition": {"include": f"真实模态为 {item}", "exclude": "格式证据不足或损坏。", "evidence_required_any": ["metadata"], "tie_breaker": "仅按已验证模态。"}, "is_fallback": item == "other"}
                 for item in template["modalities"]]
    paths = validate_nodes(nodes, max_depth=max_depth, max_siblings=max_siblings, max_nodes=max_nodes)
    normalized = [dict(node) for node in nodes]
    digest = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
    return {"schema_version": 1, "taxonomy_id": str(uuid.uuid4()), "scope_id": scope_id, "version": 1,
            "source": "template", "status": "draft", "tree_hash": digest, "nodes": normalized, "policy": {}}
