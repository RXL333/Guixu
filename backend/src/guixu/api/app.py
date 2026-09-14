from __future__ import annotations

import hmac
import hashlib
import json
import secrets
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from guixu import __version__
from guixu.api.schemas import ApprovePlanRequest, ApproveTaxonomyRequest, BulkReviewRequest, ComponentImportRequest, ConsentRequest, CreateTaskRequest, DuplicateTemplateRequest, ExecutePlanRequest, ExpectedRevisionRequest, ExportReportRequest, ModelInputRequest, ModelPatchRequest, ModelSecretRequest, ReanalyzeRequest, RegisterGrantRequest, RuleInputRequest, RuleTestRequest, StartTaskRequest, TemplateImportRequest
from guixu.application.classification import ClassificationService
from guixu.application.coordinator import TaskCoordinator
from guixu.application.operations import OperationService
from guixu.application.models import ModelError, ModelProfileService
from guixu.application.model_gateway import BudgetError, ModelGateway
from guixu.application.privacy import PrivacyService
from guixu.application.reporting import ReportService
from guixu.application.previews import PreviewTicketService
from guixu.application.parsing import ParsingService
from guixu.application.tasks import TaskService
from guixu.application.taxonomies import TaxonomyService
from guixu.application.templates import TemplateError, TemplateService
from guixu.application.rules import RuleService
from guixu.domain.classification import ClassificationError
from guixu.domain.settings import load_default_settings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.filesystem.grants import GrantError, SourceRegistry
from guixu.infrastructure.resources.components import ComponentError, ComponentManager, status_dict
from guixu.infrastructure.models.credentials import CredentialError, WindowsCredentialStore
from guixu.infrastructure.models.transport import ModelTransportError
from guixu.domain.privacy import PrivacyError


def envelope(data: Any, request_id: str) -> dict[str, Any]:
    return {"data": data, "meta": {"request_id": request_id}}


def error_response(status: int, code: str, message: str, request_id: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details, "retryable": status >= 500}, "request_id": request_id},
    )


def create_app(
    *,
    project_root: Path,
    data_dir: Path,
    session_token: str | None = None,
    allowed_origins: set[str] | None = None,
    allow_typed_grants: bool = False,
    allow_direct_move: bool = False,
) -> FastAPI:
    token = session_token or secrets.token_urlsafe(32)
    database = Database(data_dir / "app.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    defaults = load_default_settings(project_root)
    database.seed_json("default_settings", defaults.model_dump(mode="json"))
    template_seed = json.loads((project_root / "seed" / "templates.json").read_text("utf-8"))
    for template in template_seed["templates"]:
        database.seed_builtin_template(template)
    registry = SourceRegistry()
    repository = TaskRepository(database)
    tasks = TaskService(repository, registry, allow_direct_move=allow_direct_move)
    journal = SqliteOperationJournal(database)
    operations = OperationService(repository, journal)
    coordinator = TaskCoordinator(repository, journal, operations)
    interrupted_tasks = coordinator.audit_startup()
    parsing = ParsingService(repository, data_dir / "cache" / "profiles")
    components = ComponentManager(database, data_dir / "components")
    templates = TemplateService(database, project_root / "contracts" / "schemas" / "template.schema.json")
    rules = RuleService(database)
    taxonomies = TaxonomyService(database)
    classifications = ClassificationService(database, project_root / "contracts" / "schemas" / "classification-result.schema.json")
    credential_store = WindowsCredentialStore()
    models = ModelProfileService(database, credential_store)
    privacy = PrivacyService(database)
    model_gateway = ModelGateway(database, models, privacy)
    reporting = ReportService(database, repository, registry)
    previews = PreviewTicketService(repository)
    frontend_dist = project_root / "frontend" / "dist"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        database.close()

    app = FastAPI(title="Guixu Local API", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.session_token = token
    app.state.database = database
    app.state.registry = registry
    app.state.repository = repository
    app.state.tasks = tasks
    app.state.operations = operations
    app.state.coordinator = coordinator
    app.state.interrupted_tasks = interrupted_tasks
    app.state.parsing = parsing
    app.state.components = components
    app.state.templates = templates
    app.state.rules = rules
    app.state.taxonomies = taxonomies
    app.state.classifications = classifications
    app.state.models = models
    app.state.privacy = privacy
    app.state.model_gateway = model_gateway
    app.state.reporting = reporting
    app.state.previews = previews
    app.state.project_root = project_root
    app.state.allow_typed_grants = allow_typed_grants
    app.state.allowed_origins = allowed_origins or set()

    @app.middleware("http")
    async def secure_local_api(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        ticket_stream = request.method == "GET" and request.url.path.startswith("/api/v1/previews/")
        if request.url.path != "/api/v1/health" and not request.url.path.startswith("/assets/") and request.url.path != "/" and not ticket_stream:
            host = request.headers.get("host", "")
            expected_hosts = {origin.split("//", 1)[-1] for origin in app.state.allowed_origins}
            if app.state.allow_typed_grants:
                expected_hosts.add("testserver")
            if host not in expected_hosts:
                return error_response(403, "HOST_REJECTED", "请求主机不受信任。", request_id)
            supplied = request.headers.get("X-Guixu-Session", "")
            if not hmac.compare_digest(supplied, token):
                return error_response(401, "SESSION_INVALID", "本地会话无效，请重新打开应用。", request_id)
            origin = request.headers.get("origin")
            if origin and origin not in app.state.allowed_origins:
                return error_response(403, "ORIGIN_REJECTED", "请求来源不受信任。", request_id)
        idempotency_key = request.headers.get("Idempotency-Key")
        endpoint = f"{request.method}:{request.url.path}"
        request_hash = None
        if idempotency_key and request.method in {"POST", "PATCH", "DELETE"}:
            raw_body = await request.body()
            request_hash = hashlib.sha256(raw_body).hexdigest()
            with database.engine.connect() as connection:
                saved = connection.execute(text("""
                    SELECT request_hash,response_json,status_code FROM idempotency_keys
                    WHERE endpoint=:endpoint AND key=:key AND expires_at>:now
                """), {"endpoint": endpoint, "key": idempotency_key, "now": datetime.now(UTC).isoformat()}).mappings().first()
            if saved:
                if not hmac.compare_digest(saved["request_hash"], request_hash):
                    return error_response(409, "IDEMPOTENCY_KEY_REUSED", "同一幂等键不能用于不同请求。", request_id)
                return JSONResponse(status_code=saved["status_code"], content=json.loads(saved["response_json"]), headers={"X-Request-ID": request_id, "Cache-Control": "no-store"})
        response = await call_next(request)
        if idempotency_key and request_hash and response.status_code < 500:
            chunks = [chunk async for chunk in response.body_iterator]
            body = b"".join(chunk.encode() if isinstance(chunk, str) else chunk for chunk in chunks)
            try:
                decoded = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                decoded = None
            if decoded is not None:
                with database.begin() as connection:
                    connection.execute(text("""
                        INSERT OR IGNORE INTO idempotency_keys(key,endpoint,request_hash,response_json,status_code,created_at,expires_at)
                        VALUES(:key,:endpoint,:hash,:response,:status,:now,:expires)
                    """), {"key": idempotency_key, "endpoint": endpoint, "hash": request_hash,
                            "response": json.dumps(decoded, ensure_ascii=False, separators=(",", ":")),
                            "status": response.status_code, "now": datetime.now(UTC).isoformat(),
                            "expires": (datetime.now(UTC) + timedelta(days=1)).isoformat()})
            response = Response(content=body, status_code=response.status_code, headers=dict(response.headers), media_type=response.media_type)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        safe_errors = [{key: item.get(key) for key in ("type", "loc", "msg") if key in item} for item in exc.errors()]
        return error_response(422, "SCHEMA_INVALID", "请求字段不符合契约。", request.state.request_id, safe_errors)

    @app.exception_handler(GrantError)
    async def grant_error(request: Request, exc: GrantError):
        code = str(exc)
        status = 403 if code == "PATH_OUTSIDE_GRANT" else 422
        return error_response(status, code, "目录授权无效或路径不安全。", request.state.request_id)

    @app.exception_handler(ComponentError)
    async def component_error(request: Request, exc: ComponentError):
        return error_response(422, str(exc), "离线组件资源包校验失败。", request.state.request_id)

    @app.exception_handler(TemplateError)
    async def template_error(request: Request, exc: TemplateError):
        return error_response(400, str(exc), "模板未通过校验或内置模板不可覆盖。", request.state.request_id)

    @app.exception_handler(ClassificationError)
    async def classification_error(request: Request, exc: ClassificationError):
        code = str(exc); status = 409 if code in {"RULE_CONFLICT", "SCOPE_CONFLICT", "REVISION_CONFLICT"} else 422
        return error_response(status, code, "分类或规则未通过受限契约校验。", request.state.request_id)

    @app.exception_handler(ModelError)
    @app.exception_handler(ModelTransportError)
    async def model_error(request: Request, exc: Exception):
        code = getattr(exc, "code", str(exc)); status = 409 if code == "REVISION_CONFLICT" else 422
        return error_response(status, code, "模型连接配置或调用失败。", request.state.request_id)

    @app.exception_handler(PrivacyError)
    async def privacy_error(request: Request, exc: PrivacyError):
        code = str(exc); status = 409 if code in {"REVISION_CONFLICT", "CONSENT_SCOPE_CHANGED"} else 403
        return error_response(status, code, "出站请求未获得匹配的任务授权。", request.state.request_id)

    @app.exception_handler(BudgetError)
    async def budget_error(request: Request, exc: BudgetError):
        return error_response(429, str(exc), "模型预算已达到限制，任务已安全停止新请求。", request.state.request_id)

    @app.exception_handler(CredentialError)
    async def credential_error(request: Request, exc: CredentialError):
        return error_response(503, str(exc).split(":",1)[0], "Windows 凭据管理器不可用。", request.state.request_id)

    @app.get("/api/v1/health")
    def health(request: Request):
        return envelope({"version": __version__, "ready": True}, request.state.request_id)

    @app.get("/api/v1/capabilities")
    def capabilities(request: Request):
        return envelope(
            {
                "scan": True,
                "report_only": True,
                "file_operations": False,
                "models": {"deepseek": "configured" if any(x["provider"] == "deepseek" and x["enabled"] for x in models.list()) else "unavailable", "qwen_local": "configured" if any(x["provider"] == "qwen_local" and x["enabled"] for x in models.list()) else "unavailable"},
                "parsers": "ready",
                "components": [status_dict(item) for item in components.list()],
            },
            request.state.request_id,
        )

    @app.get("/api/v1/settings")
    def get_settings(request: Request):
        return envelope({"revision": 1, "values": defaults.model_dump(mode="json")}, request.state.request_id)

    @app.get("/api/v1/components")
    def get_components(request: Request):
        return envelope([status_dict(item) for item in components.list()], request.state.request_id)

    @app.get("/api/v1/models")
    def list_models(request: Request):
        return envelope(models.list(), request.state.request_id)

    @app.post("/api/v1/models", status_code=201)
    def create_model(payload: ModelInputRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(models.create(payload.model_dump(mode="python")), request.state.request_id)

    @app.patch("/api/v1/models/{model_id}")
    def patch_model(model_id: str, payload: ModelPatchRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(models.update(model_id, payload.expected_revision, payload.changes), request.state.request_id)

    @app.delete("/api/v1/models/{model_id}")
    def delete_model(model_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(models.disable(model_id, payload.expected_revision), request.state.request_id)

    @app.post("/api/v1/models/{model_id}/secret")
    def model_secret(model_id: str, payload: ModelSecretRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(models.set_secret(model_id, payload.expected_revision, payload.secret), request.state.request_id)

    @app.post("/api/v1/models/{model_id}/probe")
    def probe_model(model_id: str, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(models.probe(model_id), request.state.request_id)

    @app.post("/api/v1/components/import")
    def import_component(payload: ComponentImportRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        grant = registry.get(payload.component_grant, "component_import")
        imported = components.import_directory(grant.canonical_root, payload.component_type, payload.expected_manifest_sha256)
        return envelope(status_dict(imported), request.state.request_id)

    @app.get("/api/v1/templates")
    def list_templates(request: Request, modality: str | None = None, origin: str | None = None, limit: int = Query(100, ge=1, le=500)):
        items = templates.list(modality=modality)
        if origin: items = [item for item in items if item["origin"] == origin]
        definitions = [item["definition"] for item in items[:limit]]
        return envelope({"items": definitions, "total": len(items), "next_cursor": None}, request.state.request_id)

    @app.get("/api/v1/templates/{template_key}")
    def get_template(template_key: str, request: Request):
        try: item = templates.get(template_key)
        except KeyError: return error_response(404, "TEMPLATE_NOT_FOUND", "模板不存在。", request.state.request_id)
        return envelope(item["definition"], request.state.request_id)

    @app.post("/api/v1/templates/import")
    def import_templates(payload: TemplateImportRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope([templates.import_user(item)["definition"] for item in payload.templates], request.state.request_id)

    @app.post("/api/v1/templates/{template_key}/duplicate", status_code=201)
    def duplicate_template(template_key: str, payload: DuplicateTemplateRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        new_key = payload.template_key or f"user.{template_key.replace('.', '_')}"
        return envelope(templates.duplicate(template_key, new_key, payload.name)["definition"], request.state.request_id)

    @app.get("/api/v1/rules")
    def list_rules(request: Request):
        items = rules.list(); return envelope({"items": items, "total": len(items), "next_cursor": None}, request.state.request_id)

    @app.post("/api/v1/rules", status_code=201)
    def create_rule(payload: RuleInputRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(rules.create(payload.model_dump(mode="python")), request.state.request_id)

    @app.post("/api/v1/rules/test")
    def test_rule(payload: RuleTestRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(rules.test(payload.task_id, payload.file_ids, payload.draft_rule.model_dump(mode="python")), request.state.request_id)

    @app.post("/api/v1/dev/grants")
    def register_grant(payload: RegisterGrantRequest, request: Request):
        if not app.state.allow_typed_grants:
            return error_response(404, "NOT_AVAILABLE", "浏览器路径授权仅在显式开发模式可用。", request.state.request_id)
        grant = registry.register_typed_directory(payload.path, payload.purpose)
        return envelope(
            {"grant_id": grant.grant_id, "display_path": grant.display_path, "exists": True, "writable": grant.writable, "warnings": []},
            request.state.request_id,
        )

    @app.get("/api/v1/tasks")
    def list_tasks(request: Request):
        return envelope({"items": repository.list()}, request.state.request_id)

    @app.post("/api/v1/tasks", status_code=201)
    def create_task(payload: CreateTaskRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            classification_request = dict(payload.classification_request)
            for key, value in {"template_key":payload.template_key,"template_version":payload.template_version,"user_instructions":payload.user_instructions,"rule_ids":payload.rule_ids,"fixed_tree":payload.fixed_tree}.items():
                if value not in (None, "", []): classification_request[key] = value
            model_snapshot = models.get(payload.model_profile_id) if payload.model_profile_id else None
            task = tasks.create_task(
                payload.name, payload.source_grant, payload.output_grant, payload.settings, classification_request,
                payload.model_profile_id, model_snapshot
            )
        except GrantError:
            raise
        except KeyError:
            return error_response(404, "MODEL_NOT_FOUND", "模型连接不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(400, "INVALID_CONFIGURATION", str(exc), request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}")
    def get_task(task_id: str, request: Request):
        try:
            task = repository.get(task_id)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/start", status_code=202)
    def start_task(task_id: str, payload: StartTaskRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            tasks.start(task_id, payload.expected_revision)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在或目录授权已失效。", request.state.request_id)
        except ValueError as exc:
            code = str(exc)
            status = 409 if code == "REVISION_CONFLICT" else 503
            return error_response(status, code, "当前阶段仅开放只读报告模式。", request.state.request_id)
        started_task = repository.get(task_id)
        if started_task["settings"]["classification_source"] == "template" and not taxonomies.list_task(task_id):
            template_key = started_task["classification_request"].get("template_key", "universal.types")
            try:
                definition = started_task["template_snapshot"] or templates.get(template_key)["definition"]
                settings = started_task["settings"]
                scopes = repository.list_scopes(task_id)
                if len(definition["nodes"]) * len(scopes) > settings["max_new_directories"]:
                    raise ValueError("TASK_DIRECTORY_LIMIT")
                for scope in scopes:
                    taxonomies.save_draft(task_id, scope["id"], definition["nodes"], "template", max_depth=settings["max_depth"], max_siblings=settings["max_siblings"], max_nodes=settings["max_nodes_per_scope"], policy={"template_key": template_key, "template_version": definition["version"]})
            except (KeyError, ValueError) as exc:
                return error_response(400, "INVALID_TEMPLATE", str(exc), request.state.request_id)
        return envelope(repository.get(task_id), request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}/files")
    def list_files(task_id: str, request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                   q: str = Query("", max_length=200), scan_status: str | None = None):
        try:
            repository.get(task_id)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        if scan_status not in {None, "eligible", "excluded", "missing", "error", "discovered"}:
            return error_response(422, "SCAN_STATUS_INVALID", "文件状态筛选值无效。", request.state.request_id)
        items, total = repository.list_files(task_id, limit, offset, q, scan_status)
        return envelope({"items": items, "total": total, "next_cursor": offset + len(items) if offset + len(items) < total else None}, request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}/files/{file_id}")
    def file_detail(task_id: str, file_id: str, request: Request):
        try:
            detail = repository.file_detail(task_id, file_id)
        except KeyError:
            return error_response(404, "FILE_NOT_FOUND", "文件不存在。", request.state.request_id)
        return envelope(detail, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/files/{file_id}/preview-ticket", status_code=201)
    def issue_preview_ticket(task_id: str, file_id: str, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            result = previews.issue(task_id, file_id)
        except KeyError:
            return error_response(404, "FILE_NOT_FOUND", "预览文件不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(422, str(exc), "此格式不会作为原始活动内容提供预览。", request.state.request_id)
        result["url"] = f"/api/v1/previews/{result['ticket']}"
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/previews/{ticket}")
    def stream_preview(ticket: str, request: Request):
        try:
            grant = previews.resolve(ticket)
        except KeyError:
            return error_response(404, "PREVIEW_TICKET_INVALID", "预览票据无效或已过期。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "预览源文件已发生变化。", request.state.request_id)
        start, end = 0, grant.size - 1
        status = 200
        range_header = request.headers.get("range")
        if range_header:
            if not range_header.startswith("bytes=") or "," in range_header:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{grant.size}"})
            try:
                first, last = range_header[6:].split("-", 1)
                if first:
                    start = int(first); end = min(int(last), grant.size - 1) if last else grant.size - 1
                else:
                    length = int(last); start = max(0, grant.size - length); end = grant.size - 1
                if start < 0 or start > end or start >= grant.size:
                    raise ValueError
            except ValueError:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{grant.size}"})
            status = 206
        with grant.path.open("rb") as stream:
            stream.seek(start); content = stream.read(end - start + 1)
        headers = {"Accept-Ranges": "bytes", "Content-Length": str(len(content)), "Cache-Control": "no-store",
                   "Content-Security-Policy": "default-src 'none'", "X-Content-Type-Options": "nosniff"}
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{grant.size}"
        return Response(content=content, status_code=status, media_type=grant.media_type, headers=headers)

    @app.post("/api/v1/tasks/{task_id}/reanalyze", status_code=202)
    def reanalyze(task_id: str, payload: ReanalyzeRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            repository.assert_revision(task_id, payload.expected_revision)
            outcomes = [parsing.parse(task_id, file_id) for file_id in payload.file_ids]
        except KeyError:
            return error_response(404, "FILE_NOT_FOUND", "任务或文件不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "文件无法按当前状态重新解析。", request.state.request_id)
        return envelope({"command_id": str(uuid.uuid4()), "status": "completed", "profiles": [item.profile.model_dump(mode="json") for item in outcomes]}, request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}/taxonomies")
    def list_task_taxonomies(task_id: str, request: Request):
        try: repository.get(task_id)
        except KeyError: return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        return envelope(taxonomies.list_task(task_id), request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/taxonomies/{taxonomy_id}/approve", status_code=202)
    def approve_taxonomy(task_id: str, taxonomy_id: str, payload: ApproveTaxonomyRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            taxonomy = taxonomies.approve(task_id, taxonomy_id, payload.tree_hash, payload.expected_revision)
        except KeyError: return error_response(404, "TAXONOMY_NOT_FOUND", "分类树不存在。", request.state.request_id)
        except ValueError as exc: return error_response(409, str(exc), "分类树版本或哈希已变化。", request.state.request_id)
        classification_status = "completed"
        template_key = taxonomy["policy"].get("template_key", "universal.types")
        try:
            for file_id in repository.eligible_file_ids(task_id, taxonomy["scope_id"]):
                profile = parsing.parse(task_id, file_id).profile
                task = repository.get(task_id)
                callback = None
                if task.get("model_profile_id"):
                    callback = lambda _payload, p=profile: model_gateway.classify(task_id=task_id, profile_id=task["model_profile_id"], profile=p, taxonomy=taxonomy, policy=taxonomy["policy"], rule_hints=[])
                classifications.classify(task_id=task_id, file_id=file_id, taxonomy=taxonomy, profile=profile, template_key=template_key, rules=task["rules_snapshot"], test_model=callback)
        except (ClassificationError, PrivacyError, BudgetError, ModelTransportError) as exc:
            code = getattr(exc, "code", str(exc))
            if code not in {"MODEL_UNAVAILABLE", "PRIVACY_CONSENT_REQUIRED", "BUDGET_EXCEEDED"}: raise
            classification_status = code.lower()
            repository.append_event(task_id, classification_status, {"taxonomy_id": taxonomy_id})
        repository.refresh_counters(task_id)
        repository.append_event(task_id, "classification_completed", {"taxonomy_id": taxonomy_id, "status": classification_status})
        return envelope({"command_id": str(uuid.uuid4()), "status": "completed", "taxonomy": taxonomy, "classification_status": classification_status}, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/reviews/bulk")
    def bulk_reviews(task_id: str, payload: BulkReviewRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        result = classifications.review_bulk(task_id, [item.model_dump(mode="python") for item in payload.items], payload.expected_revision)
        repository.refresh_counters(task_id)
        repository.append_event(task_id, "reviews_applied", {"count": result["applied"]})
        return envelope({key: result[key] for key in ("applied", "new_revision", "invalidated_plan_ids")}, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/consents", status_code=201)
    def grant_consent(task_id: str, payload: ConsentRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        result = privacy.grant(task_id, payload.provider_profile_id, payload.data_types,
                               payload.budget.model_dump(mode="python"), payload.scope_hash,
                               payload.expected_revision, payload.acknowledge_content_disclosure)
        return envelope(result, request.state.request_id)

    @app.delete("/api/v1/tasks/{task_id}/consents/{consent_id}")
    def revoke_consent(task_id: str, consent_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        return envelope(privacy.revoke(task_id, consent_id, payload.expected_revision), request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}/events")
    def task_events(task_id: str, request: Request, after_seq: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=200)):
        return envelope({"items": repository.events(task_id, after_seq, limit)}, request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}/report")
    def report(task_id: str, request: Request):
        try:
            result = reporting.build(task_id)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/report/export", status_code=201)
    def export_report(task_id: str, payload: ExportReportRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            result = reporting.export(task_id, payload.export_grant, payload.format, payload.filename)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        except FileExistsError:
            return error_response(409, "TARGET_APPEARED", "报告文件已存在，不会覆盖。", request.state.request_id)
        except ValueError as exc:
            return error_response(422, str(exc), "报告文件名无效。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/plan/compile", status_code=201)
    def compile_plan(task_id: str, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            plan = operations.compile(task_id)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "任务尚未准备好生成计划。", request.state.request_id)
        return envelope(asdict(plan), request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}/plan")
    def get_plan(task_id: str, request: Request, plan_id: str | None = None):
        try:
            if plan_id is None:
                with database.engine.connect() as connection:
                    plan_id = connection.exec_driver_sql("SELECT id FROM plans WHERE task_id=? ORDER BY version DESC LIMIT 1", (task_id,)).scalar()
            if not plan_id: raise KeyError(task_id)
            plan = journal.load_plan(plan_id)
            if plan.task_id != task_id: raise KeyError(task_id)
        except KeyError:
            return error_response(404, "PLAN_NOT_FOUND", "整理计划不存在。", request.state.request_id)
        return envelope(asdict(plan), request.state.request_id)

    @app.get("/api/v1/tasks/{task_id}/operations")
    def list_operations(task_id: str, request: Request, plan_id: str | None = None, state: str | None = None,
                        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        params: dict[str, Any] = {"task": task_id, "limit": limit, "offset": offset}
        clauses = ["p.task_id=:task"]
        if plan_id:
            clauses.append("p.id=:plan"); params["plan"] = plan_id
        if state:
            allowed_states = {"PLANNED","PREPARED","COPYING","TEMP_WRITTEN","VERIFIED","PUBLISHED","SOURCE_REMOVED","COMMITTED","SKIPPED","FAILED","CONFLICT","UNDO_PREPARED","UNDONE","UNDO_CONFLICT"}
            if state not in allowed_states:
                return error_response(422, "OPERATION_STATE_INVALID", "操作状态筛选值无效。", request.state.request_id)
            clauses.append("o.state=:state"); params["state"] = state
        where = " AND ".join(clauses)
        with database.engine.connect() as connection:
            total = int(connection.execute(text(f"SELECT count(*) FROM operations o JOIN plans p ON p.id=o.plan_id WHERE {where}"), params).scalar_one())
            rows = connection.execute(text(f"""
                SELECT o.id AS operation_id,o.plan_id,o.file_id,o.ordinal,o.action,o.source_path,o.target_path,
                       o.state,o.error_code,o.companion_group_id,o.updated_at,p.plan_kind
                FROM operations o JOIN plans p ON p.id=o.plan_id WHERE {where}
                ORDER BY p.version DESC,o.ordinal LIMIT :limit OFFSET :offset
            """), params).mappings()
            items = [dict(row) for row in rows]
        return envelope({"items": items, "total": total, "next_cursor": offset + len(items) if offset + len(items) < total else None}, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/plan/approve")
    def approve_plan(task_id: str, payload: ApprovePlanRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            operations.approve(task_id, payload.plan_id, payload.plan_hash, payload.expected_revision)
        except ValueError as exc:
            return error_response(409, str(exc), "计划已失效或哈希不匹配。", request.state.request_id)
        return envelope({"plan_id": payload.plan_id, "plan_hash": payload.plan_hash, "status": "approved"}, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/execute", status_code=202)
    def execute_plan(task_id: str, payload: ExecutePlanRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            plan = coordinator.execute(task_id, payload.plan_id, payload.plan_hash, payload.expected_revision)
        except (ValueError, KeyError) as exc:
            return error_response(409, str(exc), "计划未批准、已失效或执行条件发生变化。", request.state.request_id)
        return envelope(asdict(plan), request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/pause", status_code=202)
    def pause_task(task_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            task = coordinator.request_pause(task_id, payload.expected_revision)
        except (ValueError, KeyError) as exc:
            return error_response(409, str(exc), "任务当前不能暂停或版本已变化。", request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/resume", status_code=202)
    def resume_task(task_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            task = coordinator.resume(task_id, payload.expected_revision)
        except (ValueError, KeyError) as exc:
            return error_response(409, str(exc), "任务当前不能恢复或版本已变化。", request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/cancel", status_code=202)
    def cancel_task(task_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            task = coordinator.request_cancel(task_id, payload.expected_revision)
        except (ValueError, KeyError) as exc:
            return error_response(409, str(exc), "任务当前不能取消或版本已变化。", request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/recover", status_code=202)
    def recover_task(task_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            result = coordinator.recover(task_id, payload.expected_revision)
        except (ValueError, KeyError) as exc:
            return error_response(409, str(exc), "恢复前置状态或磁盘事实不一致。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/undo/plan", status_code=201)
    def compile_undo(task_id: str, payload: ApprovePlanRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            forward = journal.load_plan(payload.plan_id)
            if forward.plan_hash != payload.plan_hash:
                raise ValueError("PLAN_STALE")
            plan = operations.compile_undo(task_id, payload.plan_id, payload.expected_revision)
        except (ValueError, KeyError) as exc:
            return error_response(409, str(exc), "无法根据当前磁盘状态生成撤销计划。", request.state.request_id)
        return envelope(asdict(plan), request.state.request_id)

    if frontend_dist.exists():
        assets = frontend_dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            candidate = frontend_dist / path
            if path and candidate.is_file() and frontend_dist in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app
