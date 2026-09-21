from __future__ import annotations

import json
import base64
import io
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import text

from guixu.application.model_gateway import ModelGateway
from guixu.application.models import ModelProfileService, build_probe_png_data_url, unknown_capabilities
from guixu.application.privacy import PrivacyService
from guixu.domain.privacy import PrivacyError, build_outbound, scope_hash
from guixu.domain.profiles import Coverage, Evidence, FileProfile
from guixu.domain.settings import TaskSettings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.models.credentials import WindowsCredentialStore
from guixu.infrastructure.models.transport import DeepSeekAdapter, ModelTransportError, OpenAICompatibleTransport, validate_endpoint


class MemorySecrets:
    def __init__(self): self.values: dict[str, str] = {}
    def set(self, key, value): self.values[key] = value; return f"memory/{key}"
    def get(self, key): return self.values.get(key)
    def delete(self, key): self.values.pop(key, None)
    def has(self, key): return key in self.values


@contextmanager
def fake_service(responder):
    calls: list[dict] = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw); calls.append({"path": self.path, "body": body, "authorization": self.headers.get("Authorization")})
            status, headers, payload = responder(len(calls), body)
            self.send_response(status)
            for key, value in headers.items(): self.send_header(key, value)
            self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f"http://127.0.0.1:{server.server_port}/v1", calls
    finally: server.shutdown(); server.server_close(); thread.join()


@pytest.fixture
def services(tmp_path: Path, project_root: Path):
    db = Database(tmp_path / "models.sqlite3", project_root / "contracts" / "database.sql"); db.initialize()
    repo = TaskRepository(db); task = repo.create("model-test", TaskSettings(operation_mode="report_only", classification_source="template"), {})
    secrets = MemorySecrets(); models = ModelProfileService(db, secrets); privacy = PrivacyService(db)
    yield db, task, models, privacy, secrets
    db.close()


def model_input(url: str, *, runtime="openai_compatible", trust="loopback"):
    return {"name":"Qwen test","provider":"qwen_local","runtime":runtime,"base_url":url,"model_id":"qwen-test",
            "trust_scope":trust,"options":{"thinking_mode":"server_default","timeout_seconds":5,"max_concurrency":1},"enabled":True}


def mark_supported(models: ModelProfileService, model_id: str, *, vision: bool = False) -> None:
    caps = unknown_capabilities()
    for key in ("reachable", "authentication", "text", "json_mode", "cancellation"):
        caps[key] = {"status": "supported", "message": "test", "tested_at": "2026-09-15T00:00:00Z"}
    caps["vision"] = {"status": "supported" if vision else "unsupported", "message": "test", "tested_at": "2026-09-15T00:00:00Z"}
    models._save_capabilities(model_id, caps)


def profile() -> FileProfile:
    return FileProfile(file_id=str(uuid.uuid4()), modality="text", content_summary="private summary", summary_origin="deterministic",
        evidence=[Evidence(id="e1",kind="extracted_text",text="private body",quality="high",origin="text",locator={"paragraph":1})],
        coverage=Coverage(mode="full"), parser_version="test")


def test_ai05_auth_no_retry_and_retry_after():
    def auth(_, body): return 401, {}, {"error":"bad key"}
    with fake_service(auth) as (url, calls):
        transport = OpenAICompatibleTransport()
        with pytest.raises(ModelTransportError) as exc:
            transport.chat(base_url=url, model_id="m", messages=[], secret="x", timeout_seconds=5)
        assert exc.value.code == "MODEL_AUTH_FAILED" and len(calls) == 1
    slept=[]
    def limited(n, body):
        if n == 1: return 429, {"Retry-After":"0.01"}, {"error":"slow"}
        return 200, {}, {"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":2,"completion_tokens":1}}
    with fake_service(limited) as (url, calls):
        result=OpenAICompatibleTransport(sleeper=slept.append).chat(base_url=url,model_id="m",messages=[],secret=None,timeout_seconds=5)
        assert result.attempts == 2 and len(calls) == 2 and slept == [0.01]


def test_deepseek_protocol_fields_are_adapter_only():
    calls=[]
    def handler(request: httpx.Request):
        calls.append({"path":request.url.path,"body":json.loads(request.content),"authorization":request.headers.get("Authorization")})
        return httpx.Response(200,json={"choices":[{"message":{"content":"{\"probe\":true}"}}]})
    factory=lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler),timeout=kwargs["timeout"],follow_redirects=False,trust_env=False)
    adapter=DeepSeekAdapter(OpenAICompatibleTransport(client_factory=factory))
    adapter.chat({"base_url":"https://api.deepseek.com","model_id":"deepseek-flash","trust_scope":"cloud","options":{"thinking_mode":"disabled","timeout_seconds":5}},
                 [{"role":"user","content":"fixed probe"}],"test-key",json_mode=True)
    assert calls[0]["path"] == "/chat/completions"
    assert calls[0]["body"]["thinking"] == {"type":"disabled"}
    assert calls[0]["body"]["response_format"] == {"type":"json_object"}
    assert calls[0]["authorization"] == "Bearer test-key"


def test_deepseek_vision_uses_minimal_multimodal_request_and_valid_probe_png():
    data_url = build_probe_png_data_url()
    assert data_url.startswith("data:image/png;base64,")
    image_bytes = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    with Image.open(io.BytesIO(image_bytes)) as image:
        assert image.format == "PNG" and image.size == (64, 64)
        image.verify()

    calls = []
    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices":[{"message":{"content":"A red square on a blue background."}}]})
    factory = lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler), timeout=kwargs["timeout"],
                                             follow_redirects=False, trust_env=False)
    adapter = DeepSeekAdapter(OpenAICompatibleTransport(client_factory=factory))
    messages = [{"role":"user","content":[
        {"type":"text","text":"Describe the main visual content of this image briefly."},
        {"type":"image_url","image_url":{"url":data_url}},
    ]}]
    adapter.chat({"base_url":"https://api.deepseek.com","model_id":"deepseek-flash","trust_scope":"cloud",
                  "options":{"thinking_mode":"disabled","timeout_seconds":5}}, messages, "test-key")
    assert calls == [{"model":"deepseek-flash","messages":messages,"stream":False}]


def test_transport_preserves_provider_error_details():
    def handler(_: httpx.Request):
        return httpx.Response(400, json={"error":{"code":"invalid_request_error","message":"unsupported image"}})
    factory = lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler), timeout=kwargs["timeout"],
                                             follow_redirects=False, trust_env=False)
    with pytest.raises(ModelTransportError) as exc:
        OpenAICompatibleTransport(client_factory=factory).chat(base_url="http://127.0.0.1:1", model_id="m",
            messages=[], secret=None, timeout_seconds=5, max_attempts=1)
    assert exc.value.code == "MODEL_REQUEST_REJECTED"
    assert exc.value.provider_code == "invalid_request_error"
    assert exc.value.provider_message == "unsupported image"


def test_ai07_probe_each_capability_and_ai08_invalidation(services):
    db, task, models, privacy, secrets = services
    def qwen(_, body):
        content=body["messages"][0]["content"]
        if isinstance(content,list): return 400, {}, {"error":"vision unsupported"}
        answer='{"probe":true}' if "response_format" in body else "GUIXU_PROBE_OK"
        return 200, {}, {"choices":[{"message":{"content":answer}}]}
    with fake_service(qwen) as (url, calls):
        item=models.create(model_input(url)); caps=models.probe(item["id"])
        assert caps["text"]["status"] == "supported" and caps["json_mode"]["status"] == "supported"
        assert caps["vision"]["status"] == "unsupported" and len(calls) == 3
        changed=models.update(item["id"], item["revision"], {"model_id":"other"})
        assert changed["capabilities"]["text"]["status"] == "unknown"


def test_probe_persists_verified_vision_metadata(services):
    db, task, models, privacy, secrets = services
    def qwen(_, body):
        content = body["messages"][0]["content"]
        if isinstance(content, list):
            return 200, {}, {"choices":[{"message":{"content":"A red square on a blue background."}}]}
        answer = '{"probe":true}' if "response_format" in body else "GUIXU_PROBE_OK"
        return 200, {}, {"choices":[{"message":{"content":answer}}]}
    with fake_service(qwen) as (url, calls):
        item = models.create(model_input(url))
        caps = models.probe(item["id"])
        assert caps["vision"]["status"] == "supported"
        assert caps["vision"]["vision"] is True
        assert caps["vision"]["vision_verified"] is True
        assert caps["vision"]["probe_status"] == "success"
        assert caps["vision"]["probe_error"] is None
        assert caps["vision"]["last_probe_at"]
        reloaded = ModelProfileService(db, secrets).get(item["id"])
        assert reloaded["capabilities"]["vision"] == caps["vision"]


def test_ai04_single_repair_ai09_budget_counts_attempts(services):
    db, task, models, privacy, secrets = services
    def responder(n, body):
        content = "not-json" if n == 1 else json.dumps({"file_id":p.file_id,"taxonomy_id":"tax","category_id":None,"abstain":True,"model_score":None,"evidence_ids":[],"reason":"原结果无法通过结构与证据校验","tags":[],"warnings":["insufficient_evidence"]})
        return 200, {}, {"choices":[{"message":{"content":content}}],"usage":{"prompt_tokens":3,"completion_tokens":2}}
    p=profile()
    with fake_service(responder) as (url, calls):
        model=models.create(model_input(url)); mark_supported(models, model["id"]); budget={"max_calls":3,"max_input_tokens":1000,"max_output_tokens":1000,"max_cost_micros":None,"currency":None}
        consent_hash=scope_hash(model["id"],["extracted_text"],budget)
        privacy.grant(task["id"],model["id"],["extracted_text"],budget,consent_hash,task["revision"],True)
        result=ModelGateway(db,models,privacy).classify(task_id=task["id"],profile_id=model["id"],profile=p,
            taxonomy={"taxonomy_id":"tax","nodes":[{"category_id":"x","selectable":True}]},policy={})
        assert result["abstain"] is True and len(calls)==2 and privacy.usage(task["id"])["calls"]==2


def test_image_classification_requires_vision_and_sends_only_controlled_derivative(services, tmp_path: Path):
    db, task, models, privacy, secrets = services
    image = tmp_path / "derivative.jpg"
    from PIL import Image
    Image.new("RGB", (32, 32), "blue").save(image, "JPEG")
    seen = {}
    def responder(_, body):
        seen.update(body)
        return 200, {}, {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}
    visual = FileProfile(file_id=str(uuid.uuid4()), modality="image", metadata={}, evidence=[],
                         coverage=Coverage(mode="full"), parser_version="test")
    with fake_service(responder) as (url, calls):
        model = models.create(model_input(url))
        with pytest.raises(Exception, match="AI_CAPABILITY"):
            ModelGateway(db, models, privacy).classify(task_id=task["id"], profile_id=model["id"], profile=visual,
                taxonomy={"taxonomy_id":"tax","nodes":[{"category_id":"x","selectable":True}]}, policy={}, derivative_paths=[str(image)])
        mark_supported(models, model["id"], vision=True)
        budget={"max_calls":3,"max_input_tokens":100000,"max_output_tokens":1000,"max_cost_micros":None,"currency":None}
        consent_hash=scope_hash(model["id"],["derivative_images"],budget)
        current=TaskRepository(db).get(task["id"])
        privacy.grant(task["id"],model["id"],["derivative_images"],budget,consent_hash,current["revision"],True)
        ModelGateway(db, models, privacy).classify(task_id=task["id"], profile_id=model["id"], profile=visual,
            taxonomy={"taxonomy_id":"tax","nodes":[{"category_id":"x","selectable":True}]}, policy={}, derivative_paths=[str(image)])
        content=seen["messages"][1]["content"]
        assert isinstance(content,list) and content[1]["type"]=="image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert str(image) not in json.dumps(seen)


def test_ai06_ai10_ai11_ai12_privacy_and_no_secret_leak(services):
    db, task, models, privacy, secrets = services
    assert validate_endpoint("http://127.0.0.1:8000/v1","loopback","qwen_local")
    with pytest.raises(ModelTransportError): validate_endpoint("http://192.168.1.9:8000/v1","loopback","qwen_local")
    assert validate_endpoint("http://192.168.1.9:8000/v1","trusted_lan","qwen_local")
    with pytest.raises(ModelTransportError): validate_endpoint("http://127.0.0.1:8000/v1","cloud","deepseek")
    item=models.create(model_input("http://127.0.0.1:8000/v1")); models.set_secret(item["id"],item["revision"],"super-secret-key")
    listed=models.get(item["id"]); assert listed["has_secret"] and "super-secret-key" not in json.dumps(listed)
    with pytest.raises(PrivacyError): privacy.require(task["id"],item["id"],{"extracted_text"})
    envelope=build_outbound(profile(), {"extracted_text"}, max_chars=100)
    raw=json.dumps(envelope.as_dict()); assert "absolute" not in raw and "private body" in raw
    disk=(db.path.read_bytes()).decode("utf-8",errors="ignore")
    assert "super-secret-key" not in disk and "private body" not in disk and "base64" not in disk


def test_deleted_profile_is_hidden_but_retained_for_audit(services):
    db, task, models, privacy, secrets = services
    item = models.create(model_input("http://127.0.0.1:8000/v1"))
    assert [profile["id"] for profile in models.list()] == [item["id"]]
    assert models.disable(item["id"], item["revision"]) == {"disabled": True}
    assert models.list() == []
    retained = models.get(item["id"])
    assert retained["enabled"] is False and retained["revision"] == item["revision"] + 1


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows Credential Manager only')
def test_windows_credential_manager_round_trip():
    store=WindowsCredentialStore(); key="phase05-"+str(uuid.uuid4()); value="guixu-test-secret-"+str(uuid.uuid4())
    try:
        store.set(key,value); assert store.has(key) and store.get(key)==value
    finally: store.delete(key)
