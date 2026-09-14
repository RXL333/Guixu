from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError
from sqlalchemy import text

from guixu.domain.taxonomy import canonical_json, validate_template
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import digest_json


class TemplateError(ValueError):
    pass


class TemplateService:
    def __init__(self, database: Database, schema_path: Path) -> None:
        self.database = database
        self.schema_path = schema_path

    def list(self, *, modality: str | None = None, strategy: str | None = None) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT * FROM template_versions t WHERE version=(SELECT MAX(version) FROM template_versions WHERE template_key=t.template_key)
                ORDER BY template_key
            """)).mappings()
            items = [self._decode(row) for row in rows]
        if modality:
            items = [item for item in items if modality in item["definition"]["modalities"]]
        if strategy:
            items = [item for item in items if strategy in item["definition"]["compatible_strategies"]]
        return items

    def get(self, key: str, version: int | None = None) -> dict[str, Any]:
        query = "SELECT * FROM template_versions WHERE template_key=:key"
        params: dict[str, Any] = {"key": key}
        if version is None:
            query += " ORDER BY version DESC LIMIT 1"
        else:
            query += " AND version=:version"; params["version"] = version
        with self.database.engine.connect() as connection:
            row = connection.execute(text(query), params).mappings().first()
        if row is None:
            raise KeyError(key)
        return self._decode(row)

    def duplicate(self, source_key: str, new_key: str, name: str) -> dict[str, Any]:
        source = self.get(source_key)
        definition = copy.deepcopy(source["definition"])
        definition.update({"template_id": new_key, "version": 1, "name": name})
        return self.import_user(definition)

    def import_user(self, definition: dict[str, Any]) -> dict[str, Any]:
        try:
            validate_template(definition, self.schema_path)
        except (ValidationError, ValueError) as exc:
            raise TemplateError("INVALID_TEMPLATE") from exc
        key = definition["template_id"]
        try:
            existing = self.get(key)
        except KeyError:
            existing = None
        if existing and existing["origin"] == "builtin":
            raise TemplateError("BUILTIN_TEMPLATE_READ_ONLY")
        next_version = (existing["version"] + 1) if existing else 1
        stored = copy.deepcopy(definition); stored["version"] = next_version
        encoded = canonical_json(stored); digest = digest_json(stored)
        with self.database.begin() as connection:
            connection.execute(text("""
                INSERT INTO template_versions(id,template_key,version,name,origin,definition_json,definition_hash,created_at)
                VALUES(:id,:key,:version,:name,'user',:definition,:digest,:created)
            """), {"id": f"user:{key}:v{next_version}", "key": key, "version": next_version,
                    "name": stored["name"], "definition": encoded, "digest": digest, "created": utc_now()})
        return self.get(key, next_version)

    @staticmethod
    def _decode(row) -> dict[str, Any]:
        return {"id": row["id"], "template_key": row["template_key"], "version": row["version"], "name": row["name"],
                "origin": row["origin"], "definition_hash": row["definition_hash"], "definition": json.loads(row["definition_json"])}
