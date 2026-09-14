from __future__ import annotations

import json
import uuid
from typing import Any, Protocol

from sqlalchemy import text

from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.repository import canonical_json
from guixu.infrastructure.models.transport import DeepSeekAdapter, ModelTransportError, OpenAICompatibleTransport, QwenLocalAdapter, validate_endpoint


class SecretStore(Protocol):
    def set(self, profile_id: str, secret: str) -> str: ...
    def get(self, profile_id: str) -> str | None: ...
    def delete(self, profile_id: str) -> None: ...
    def has(self, profile_id: str) -> bool: ...


class ModelError(RuntimeError): pass


CAPABILITY_KEYS = ("reachable", "authentication", "text", "vision", "json_mode", "cancellation")
RUNTIMES = {"deepseek", "openai_compatible", "ollama", "lmstudio", "vllm", "llamacpp"}


def unknown_capabilities() -> dict[str, Any]:
    return {key: {"status": "unknown", "message": "尚未探测。", "tested_at": None} for key in CAPABILITY_KEYS}


class ModelProfileService:
    def __init__(self, database: Database, secrets: SecretStore, transport: OpenAICompatibleTransport | None = None) -> None:
        self.database = database; self.secrets = secrets; self.transport = transport or OpenAICompatibleTransport()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate(payload)
        profile_id = str(uuid.uuid4()); now = utc_now(); caps = unknown_capabilities()
        with self.database.begin() as connection:
            connection.execute(text("""INSERT INTO model_profiles(id,name,provider,runtime,base_url,model_id,secret_ref,capabilities_json,options_json,trust_scope,enabled,revision,created_at,updated_at)
                VALUES(:id,:name,:provider,:runtime,:url,:model,NULL,:caps,:options,:trust,:enabled,1,:now,:now)"""),
                {"id": profile_id, "name": payload["name"], "provider": payload["provider"], "runtime": payload["runtime"],
                 "url": payload["base_url"].rstrip("/"), "model": payload["model_id"], "caps": canonical_json(caps),
                 "options": canonical_json(payload["options"]), "trust": payload["trust_scope"], "enabled": int(payload["enabled"]), "now": now})
        return self.get(profile_id)

    def list(self) -> list[dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM model_profiles WHERE enabled=1 ORDER BY created_at,id")
            ).mappings().all()
        return [self._public(dict(row)) for row in rows]

    def get(self, profile_id: str) -> dict[str, Any]:
        with self.database.engine.connect() as connection:
            row = connection.execute(text("SELECT * FROM model_profiles WHERE id=:id"), {"id": profile_id}).mappings().first()
        if row is None: raise KeyError(profile_id)
        return self._public(dict(row))

    def update(self, profile_id: str, expected_revision: int, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.get(profile_id); merged = {key: current[key] for key in ("name","provider","runtime","base_url","model_id","trust_scope","options","enabled")}
        merged.update(changes); self._validate(merged)
        invalidate = any(key in changes and changes[key] != current[key] for key in ("base_url", "model_id", "runtime", "provider"))
        caps = unknown_capabilities() if invalidate else current["capabilities"]
        with self.database.begin() as connection:
            changed = connection.execute(text("""UPDATE model_profiles SET name=:name,provider=:provider,runtime=:runtime,base_url=:url,model_id=:model,
              capabilities_json=:caps,options_json=:options,trust_scope=:trust,enabled=:enabled,revision=revision+1,updated_at=:now WHERE id=:id AND revision=:revision"""),
              {"id": profile_id, "revision": expected_revision, "name": merged["name"], "provider": merged["provider"], "runtime": merged["runtime"],
               "url": merged["base_url"].rstrip("/"), "model": merged["model_id"], "caps": canonical_json(caps), "options": canonical_json(merged["options"]),
               "trust": merged["trust_scope"], "enabled": int(merged["enabled"]), "now": utc_now()})
            if changed.rowcount != 1: raise ModelError("REVISION_CONFLICT")
        return self.get(profile_id)

    def set_secret(self, profile_id: str, expected_revision: int, secret: str | None) -> dict[str, bool]:
        current = self.get(profile_id)
        if current["revision"] != expected_revision: raise ModelError("REVISION_CONFLICT")
        secret_ref = None
        if secret is None: self.secrets.delete(profile_id)
        else: secret_ref = self.secrets.set(profile_id, secret)
        with self.database.begin() as connection:
            changed = connection.execute(text("UPDATE model_profiles SET secret_ref=:ref,revision=revision+1,updated_at=:now WHERE id=:id AND revision=:revision"),
                {"ref": secret_ref, "now": utc_now(), "id": profile_id, "revision": expected_revision})
            if changed.rowcount != 1:
                if secret is not None: self.secrets.delete(profile_id)
                raise ModelError("REVISION_CONFLICT")
        return {"has_secret": secret is not None}

    def disable(self, profile_id: str, expected_revision: int) -> dict[str, bool]:
        self.update(profile_id, expected_revision, {"enabled": False}); return {"disabled": True}

    def probe(self, profile_id: str) -> dict[str, Any]:
        profile = self.get(profile_id); secret = self.secrets.get(profile_id)
        now = utc_now(); caps = unknown_capabilities()
        def cap(status: str, message: str) -> dict[str, Any]: return {"status": status, "message": message, "tested_at": now}
        adapter = DeepSeekAdapter(self.transport) if profile["provider"] == "deepseek" else QwenLocalAdapter(self.transport)
        fixed_text = [{"role":"user","content":"Reply with exactly GUIXU_PROBE_OK."}]
        try:
            result = adapter.chat(profile, fixed_text, secret)
            caps["reachable"] = cap("supported", f"服务可达，{result.latency_ms} ms。")
            caps["authentication"] = cap("supported", "认证通过或服务无需认证。")
            caps["text"] = cap("supported" if "GUIXU_PROBE_OK" in result.content else "error", "固定文本探测完成。")
        except ModelTransportError as exc:
            caps["reachable"] = cap("error" if exc.status is None else "supported", exc.code)
            caps["authentication"] = cap("error" if exc.code == "MODEL_AUTH_FAILED" else "unknown", exc.code)
            self._save_capabilities(profile_id, caps); return caps
        try:
            result = adapter.chat(profile, [{"role":"user","content":"Return JSON with probe=true."}], secret, json_mode=True)
            parsed = json.loads(result.content); ok = parsed.get("probe") is True
            caps["json_mode"] = cap("supported" if ok else "unsupported", "固定 JSON 探测完成。")
        except (ModelTransportError, ValueError, TypeError): caps["json_mode"] = cap("unsupported", "服务未返回要求的 JSON。")
        pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nWQAAAAASUVORK5CYII="
        try:
            adapter.chat(profile, [{"role":"user","content":[{"type":"text","text":"Describe the single built-in test pixel."},{"type":"image_url","image_url":{"url":pixel}}]}], secret)
            caps["vision"] = cap("supported", "内置几何测试图可处理。")
        except ModelTransportError as exc: caps["vision"] = cap("unsupported" if exc.status == 400 else "error", exc.code)
        caps["cancellation"] = cap("supported", "HTTP 请求使用受控超时并可由调用方取消；未向用户文件发请求。")
        self._save_capabilities(profile_id, caps); return caps

    def _save_capabilities(self, profile_id: str, caps: dict[str, Any]) -> None:
        with self.database.begin() as connection:
            connection.execute(text("UPDATE model_profiles SET capabilities_json=:caps,updated_at=:now WHERE id=:id"), {"caps": canonical_json(caps), "now": utc_now(), "id": profile_id})

    def _validate(self, payload: dict[str, Any]) -> None:
        if payload.get("provider") not in {"deepseek", "qwen_local"} or payload.get("runtime") not in RUNTIMES: raise ModelError("MODEL_PROFILE_INVALID")
        if payload["provider"] == "deepseek" and payload["runtime"] != "deepseek": raise ModelError("MODEL_RUNTIME_MISMATCH")
        if payload["provider"] == "qwen_local" and payload["runtime"] == "deepseek": raise ModelError("MODEL_RUNTIME_MISMATCH")
        if payload["provider"] == "qwen_local" and payload["trust_scope"] == "cloud": raise ModelError("MODEL_TRUST_SCOPE_INVALID")
        validate_endpoint(payload["base_url"], payload["trust_scope"], payload["provider"])
        if not (1 <= len(payload.get("name", "")) <= 80 and 1 <= len(payload.get("model_id", "")) <= 200): raise ModelError("MODEL_PROFILE_INVALID")

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "name": row["name"], "provider": row["provider"], "runtime": row["runtime"], "base_url": row["base_url"],
                "model_id": row["model_id"], "trust_scope": row["trust_scope"], "options": json.loads(row["options_json"]),
                "enabled": bool(row["enabled"]), "revision": row["revision"], "has_secret": bool(row["secret_ref"] and self.secrets.has(row["id"])),
                "capabilities": json.loads(row["capabilities_json"])}
