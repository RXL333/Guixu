from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import text

from guixu.domain.taxonomy import canonical_json, validate_nodes
from guixu.infrastructure.db.database import Database, utc_now


class TaxonomyService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_draft(self, task_id: str, scope_id: str, nodes: list[dict[str, Any]], source: str, *, max_depth: int, max_siblings: int, max_nodes: int, policy: dict[str, Any] | None = None) -> dict[str, Any]:
        paths = validate_nodes(nodes, max_depth=max_depth, max_siblings=max_siblings, max_nodes=max_nodes)
        normalized = [{**node, "path_segments": paths[node["category_id"]]} for node in nodes]
        digest = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
        with self.database.engine.connect() as connection:
            task_scope = connection.execute(text("SELECT 1 FROM task_scopes WHERE task_id=:task AND id=:scope"), {"task": task_id, "scope": scope_id}).first()
            version = int(connection.execute(text("SELECT COALESCE(MAX(version),0)+1 FROM taxonomies WHERE scope_id=:scope"), {"scope": scope_id}).scalar_one())
        if not task_scope:
            raise ValueError("SCOPE_CONFLICT")
        taxonomy_id = str(uuid.uuid4()); now = utc_now()
        with self.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO taxonomies(id,task_id,scope_id,version,source,status,policy_json,tree_hash,created_at)
                VALUES(:id,:task,:scope,:version,:source,'draft',:policy,:hash,:now)
            """), {"id": taxonomy_id, "task": task_id, "scope": scope_id, "version": version,
                    "source": source, "policy": canonical_json(policy or {}), "hash": digest, "now": now})
            for ordinal, node in enumerate(normalized):
                connection.execute(text("""
                    INSERT INTO categories(taxonomy_id,category_id,parent_id,name,path_segments_json,depth,ordinal,selectable,definition_json,is_fallback)
                    VALUES(:taxonomy,:category,:parent,:name,:path,:depth,:ordinal,:selectable,:definition,:fallback)
                """), {"taxonomy": taxonomy_id, "category": node["category_id"], "parent": node.get("parent_id"),
                        "name": node["name"], "path": canonical_json(node["path_segments"]), "depth": len(node["path_segments"]),
                        "ordinal": ordinal, "selectable": int(node["selectable"]), "definition": canonical_json(node["definition"]),
                        "fallback": int(node.get("is_fallback", False))})
            connection.execute(text("UPDATE plans SET status='superseded' WHERE task_id=:task AND status IN ('draft','validated','approved')"), {"task": task_id})
        return self.get(task_id, taxonomy_id)

    def approve(self, task_id: str, taxonomy_id: str, tree_hash: str, expected_revision: int | None = None) -> dict[str, Any]:
        taxonomy = self.get(task_id, taxonomy_id)
        if taxonomy["tree_hash"] != tree_hash or taxonomy["status"] != "draft":
            raise ValueError("TAXONOMY_STALE")
        now = utc_now()
        with self.database.begin() as connection:
            if expected_revision is not None:
                changed = connection.execute(text("UPDATE tasks SET revision=revision+1,updated_at=:now WHERE id=:task AND revision=:revision"), {"task": task_id, "revision": expected_revision, "now": now})
                if changed.rowcount != 1:
                    raise ValueError("REVISION_CONFLICT")
            connection.execute(text("UPDATE taxonomies SET status='superseded' WHERE scope_id=:scope AND status='approved'"), {"scope": taxonomy["scope_id"]})
            changed = connection.execute(text("UPDATE taxonomies SET status='approved',approved_at=:now WHERE id=:id AND task_id=:task AND status='draft'"), {"now": now, "id": taxonomy_id, "task": task_id})
            if changed.rowcount != 1:
                raise ValueError("TAXONOMY_STALE")
        return self.get(task_id, taxonomy_id)

    def get(self, task_id: str, taxonomy_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM taxonomies WHERE task_id=:task AND id=:id"), {"task": task_id, "id": taxonomy_id}).mappings().first()
            if row is None:
                raise KeyError(taxonomy_id)
            categories = connection.execute(text("SELECT * FROM categories WHERE taxonomy_id=:id ORDER BY ordinal"), {"id": taxonomy_id}).mappings()
            nodes = [{"category_id": item["category_id"], "parent_id": item["parent_id"], "name": item["name"],
                      "selectable": bool(item["selectable"]), "definition": json.loads(item["definition_json"]),
                      "is_fallback": bool(item["is_fallback"])} for item in categories]
        return {"schema_version": 1, "taxonomy_id": row["id"], "scope_id": row["scope_id"],
                "version": row["version"], "source": row["source"], "status": row["status"], "tree_hash": row["tree_hash"],
                "policy": json.loads(row["policy_json"]), "nodes": nodes}

    def current_for_scope(self, task_id: str, scope_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT id FROM taxonomies WHERE task_id=:task AND scope_id=:scope AND status='approved' ORDER BY version DESC LIMIT 1"), {"task": task_id, "scope": scope_id}).first()
        if row is None:
            raise KeyError(scope_id)
        return self.get(task_id, row[0])

    def list_task(self, task_id: str) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            ids = [row[0] for row in connection.execute(text("SELECT id FROM taxonomies WHERE task_id=:task ORDER BY scope_id,version"), {"task": task_id})]
        return [self.get(task_id, taxonomy_id) for taxonomy_id in ids]
