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
from guixu.api.schemas import (ApprovePlanRequest, ApproveTaxonomyRequest, BulkReviewRequest,
                               ComponentImportRequest, ConsentRequest, ConversationContextUpdateRequest,
                               ConversationExecutionRoundRequest, ConversationFileRequest,
                               ConversationMessageRequest, ConversationPatchRequest, ConversationTurnRequest,
                               ConversationPlanVersionApproveRequest, ConversationPlanVersionExecutionRequest,
                               ConversationPlanVersionRequest, ConversationPlanVersionRestoreRequest,
                               ConversationRefinementExecuteRequest, ConversationRefinementRequest,
                               ConversationTaskLinkRequest, ConversationRecoveryRequest,
                               ConversationRelinkScopeRequest, ConversationUndoRequest,
                               ConversationUndoApprovalRequest, ConversationUndoExecuteRequest,
                               CreateConversationRequest, CreateTaskRequest, DeleteTaskRequest,
                               ExecutePlanRequest, ExpectedRevisionRequest, ExportReportRequest,
                               ModelInputRequest, ModelPatchRequest, ModelSecretRequest,
                               ReanalyzeRequest, RegisterGrantRequest, RenameTaskRequest,
                               StartTaskRequest, TaskBatchRequest, UpdateTaxonomyRequest)
from guixu.application.classification import ClassificationService
from guixu.application.ai_file_classifier import AIFileClassifier
from guixu.application.ai_taxonomy_planner import AITaxonomyPlanner, TaxonomyPlanningError
from guixu.application.coordinator import TaskCoordinator
from guixu.application.operations import OperationService
from guixu.application.models import ModelError, ModelProfileService
from guixu.application.model_gateway import BudgetError, ModelGateway
from guixu.application.privacy import PrivacyService
from guixu.application.reporting import ReportService
from guixu.application.previews import PreviewTicketService
from guixu.application.parsing import ParsingService
from guixu.application.semantic_cache import EvidenceCacheService
from guixu.application.tasks import TaskService
from guixu.application.taxonomies import TaxonomyService
from guixu.domain.classification import ClassificationError
from guixu.domain.settings import load_default_settings
from guixu.infrastructure.db.database import Database
from guixu.infrastructure.db.repository import TaskRepository
from guixu.infrastructure.db.conversation_repository import ConversationRepository
from guixu.application.conversations import ConversationService
from guixu.application.plan_versions import PlanVersionService
from guixu.application.post_execution import PostExecutionConversationService
from guixu.application.file_references import ReferenceResolutionError, ReferenceResolver
from guixu.application.session_recovery import SessionRecoveryService
from guixu.application.conversational_undo import ConversationalUndoService, UndoError
from guixu.application.first_analysis import FirstAnalysisError, FirstOrganizationAnalysisService
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


def reference_error_message(code: str) -> str:
    return {
        "REFERENCE_AMBIGUOUS": "无法确定你指哪些文件，请在右侧选择后再发送。",
        "REFERENCE_DUPLICATE_FILENAME": "当前会话中有多个同名文件，请在右侧选择具体文件。",
        "REFERENCE_FILE_MISSING": "引用中有文件已不在当前目录，请检查后重试。",
        "REFERENCE_FILE_CHANGED": "引用中文件内容已变化，需要重新分析后再继续。",
        "REFERENCE_SCOPE_VIOLATION": "引用包含当前会话授权范围之外的文件。",
        "REFERENCE_CATEGORY_NOT_FOUND": "当前没有可用的分类范围，请明确选择文件。",
        "REFERENCE_NOT_FOUND": "没有找到可追踪的文件引用。",
        "REFERENCE_SET_EMPTY": "文件引用集合为空，请重新选择文件。",
        "REFERENCE_STALE": "文件引用已过期，请刷新当前会话后重试。",
    }.get(code, "文件引用需要确认。")


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
    registry = SourceRegistry()
    repository = TaskRepository(database)
    evidence_cache = EvidenceCacheService(database)
    repository.evidence_cache = evidence_cache
    conversation_repository = ConversationRepository(database)
    conversations = ConversationService(conversation_repository)
    plan_versions = PlanVersionService(conversation_repository, database)
    tasks = TaskService(repository, registry, allow_direct_move=allow_direct_move)
    journal = SqliteOperationJournal(database)
    operations = OperationService(repository, journal)
    coordinator = TaskCoordinator(repository, journal, operations)
    interrupted_tasks = coordinator.audit_startup()
    parsing = ParsingService(repository, data_dir / "cache" / "profiles", evidence_cache)
    components = ComponentManager(database, data_dir / "components")
    taxonomies = TaxonomyService(database)
    classifications = ClassificationService(database, project_root / "contracts" / "schemas" / "classification-result.schema.json")
    credential_store = WindowsCredentialStore()
    models = ModelProfileService(database, credential_store)
    privacy = PrivacyService(database)
    model_gateway = ModelGateway(database, models, privacy)
    ai_planner = AITaxonomyPlanner(repository, parsing, taxonomies, model_gateway, evidence_cache)
    ai_classifier = AIFileClassifier(repository, parsing, classifications, model_gateway, evidence_cache)
    first_analysis = FirstOrganizationAnalysisService(
        project_root=project_root, database=database, conversations=conversation_repository,
        repository=repository, tasks=tasks, registry=registry, models=models, privacy=privacy,
        planner=ai_planner, classifier=ai_classifier, taxonomies=taxonomies,
        operations=operations, journal=journal,
    )
    post_execution = PostExecutionConversationService(
        database=database, conversations=conversation_repository, tasks=repository,
        journal=journal, coordinator=coordinator, parsing=parsing,
        evaluator=model_gateway.evaluate_refinement, evidence_cache=evidence_cache,
    )
    session_recovery = SessionRecoveryService(database, conversation_repository, journal, evidence_cache)
    session_recovery_startup = session_recovery.audit_startup()
    conversational_undo = ConversationalUndoService(database, journal)
    reference_resolver = ReferenceResolver(database, conversation_repository)
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
    app.state.conversations = conversations
    app.state.plan_versions = plan_versions
    app.state.post_execution = post_execution
    app.state.reference_resolver = reference_resolver
    app.state.evidence_cache = evidence_cache
    app.state.session_recovery = session_recovery
    app.state.session_recovery_startup = session_recovery_startup
    app.state.conversational_undo = conversational_undo
    app.state.tasks = tasks
    app.state.operations = operations
    app.state.coordinator = coordinator
    app.state.interrupted_tasks = interrupted_tasks
    app.state.parsing = parsing
    app.state.components = components
    app.state.taxonomies = taxonomies
    app.state.classifications = classifications
    app.state.models = models
    app.state.privacy = privacy
    app.state.model_gateway = model_gateway
    app.state.ai_planner = ai_planner
    app.state.ai_classifier = ai_classifier
    app.state.first_analysis = first_analysis
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

    @app.exception_handler(ClassificationError)
    async def classification_error(request: Request, exc: ClassificationError):
        code = str(exc); status = 409 if code in {"RULE_CONFLICT", "SCOPE_CONFLICT", "REVISION_CONFLICT"} else 422
        return error_response(status, code, "AI 分类结果未通过受限契约校验。", request.state.request_id)

    @app.exception_handler(TaxonomyPlanningError)
    async def taxonomy_planning_error(request: Request, exc: TaxonomyPlanningError):
        return error_response(422, str(exc), "AI 分类树未通过结构或安全约束。", request.state.request_id)

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

    @app.post("/api/v1/dev/grants")
    def register_grant(payload: RegisterGrantRequest, request: Request):
        if not app.state.allow_typed_grants:
            return error_response(404, "NOT_AVAILABLE", "浏览器路径授权仅在显式开发模式可用。", request.state.request_id)
        grant = registry.register_typed_directory(payload.path, payload.purpose)
        return envelope(
            {"grant_id": grant.grant_id, "display_path": grant.display_path, "exists": True, "writable": grant.writable, "warnings": []},
            request.state.request_id,
        )

    # Conversation persistence and the bounded first-organization turn. The
    # turn composes the existing safe scanner/planner/classifier pipeline and
    # only produces a preview; it does not execute filesystem operations.
    @app.get("/api/v1/conversations")
    def list_conversations(request: Request, view: str = Query("active", pattern="^(active|deleted|all)$")):
        return envelope(conversations.list_conversations(view), request.state.request_id)

    @app.post("/api/v1/conversations", status_code=201)
    def create_conversation(payload: CreateConversationRequest, request: Request,
                            idempotency_key: str = Header(default="conversation-create")):
        del idempotency_key
        if not payload.scope_grant:
            return error_response(422, "CONVERSATION_SCOPE_REQUIRED", "会话必须绑定已授权的源目录。", request.state.request_id)
        try:
            grant = registry.get(payload.scope_grant, "source")
            scope = {
                "source_root": str(grant.canonical_root),
                "display_name": grant.canonical_root.name or str(grant.canonical_root),
                "scope_kind": "folder",
                "authorization_ref": grant.grant_id,
                "authorization": {"purpose": grant.purpose, "writable": grant.writable},
            }
            result = conversations.create_conversation(title=payload.title, model_profile_id=payload.model_profile_id,
                                                        scope=scope, metadata=payload.metadata, context=payload.context)
        except GrantError:
            raise
        except KeyError:
            return error_response(404, "MODEL_NOT_FOUND", "模型连接不存在。", request.state.request_id)
        except (ValueError, TypeError) as exc:
            return error_response(422, str(exc), "会话数据不符合约束。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, request: Request):
        try:
            result = conversations.get_conversation(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/recovery-status")
    def conversation_recovery_status(conversation_id: str, request: Request, reconcile: bool = True):
        try:
            result = session_recovery.status(conversation_id, reconcile=reconcile)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/reconcile")
    def reconcile_conversation(conversation_id: str, payload: ConversationRecoveryRequest, request: Request,
                               idempotency_key: str = Header(default="conversation-reconcile")):
        del idempotency_key
        try:
            result = session_recovery.reconcile(conversation_id, trigger=payload.trigger)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/revalidate-plan")
    def revalidate_conversation_plan(conversation_id: str, payload: dict[str, str], request: Request,
                                     idempotency_key: str = Header(default="conversation-revalidate-plan")):
        del idempotency_key
        plan_version_id = str(payload.get("plan_version_id") or "")
        if not plan_version_id:
            return error_response(422, "PLAN_VERSION_REQUIRED", "需要指定方案版本。", request.state.request_id)
        try:
            result = session_recovery.revalidate_plan(conversation_id, plan_version_id)
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "方案版本不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/resume-analysis", status_code=202)
    def resume_conversation_analysis(conversation_id: str, request: Request,
                                     idempotency_key: str = Header(default="conversation-resume-analysis")):
        del idempotency_key
        try:
            result = session_recovery.resume_analysis(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "当前会话需要先同步目录或重新授权。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/external-changes")
    def conversation_external_changes(conversation_id: str, request: Request):
        try:
            result = session_recovery.status(conversation_id, reconcile=False)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result.get("reconciliation"), request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/relink-scope")
    def relink_conversation_scope(conversation_id: str, payload: ConversationRelinkScopeRequest, request: Request,
                                  idempotency_key: str = Header(default="conversation-relink-scope")):
        del idempotency_key
        if not app.state.allow_typed_grants:
            return error_response(404, "NOT_AVAILABLE", "目录重新授权仅在桌面授权流程中可用。", request.state.request_id)
        try:
            grant = registry.get(payload.scope_grant, "source")
            result = conversation_repository.relink_scope(conversation_id, {
                "source_root": str(grant.canonical_root),
                "display_name": grant.canonical_root.name or str(grant.canonical_root),
                "scope_kind": "folder", "authorization_ref": grant.grant_id,
                "authorization": {"purpose": grant.purpose, "writable": grant.writable},
            })
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        except GrantError:
            raise
        except ValueError as exc:
            return error_response(409, str(exc), "新的目录授权不可用。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/agent-turns")
    def list_conversation_agent_turns(conversation_id: str, request: Request):
        try:
            result = session_recovery.status(conversation_id, reconcile=False).get("agent_turns", [])
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/agent-turns/{turn_id}/retry", status_code=202)
    def retry_conversation_agent_turn(conversation_id: str, turn_id: str, request: Request,
                                      idempotency_key: str = Header(default="conversation-agent-turn-retry")):
        del idempotency_key
        try:
            turn = session_recovery.get_agent_turn(turn_id)
            if turn["conversation_id"] != conversation_id:
                raise KeyError(turn_id)
            result = session_recovery.retry_agent_turn(turn_id)
        except KeyError:
            return error_response(404, "AGENT_TURN_NOT_FOUND", "中断的分析记录不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.patch("/api/v1/conversations/{conversation_id}")
    def patch_conversation(conversation_id: str, payload: ConversationPatchRequest, request: Request,
                           idempotency_key: str = Header(default="conversation-patch")):
        del idempotency_key
        try:
            result = conversations.get_conversation(conversation_id)
            if payload.title is not None:
                result = conversations.rename_conversation(conversation_id, payload.title)
            if payload.model_profile_id is not None:
                result = conversations.set_model_profile(conversation_id, payload.model_profile_id)
            if payload.status == "ARCHIVED":
                result = conversations.archive_conversation(conversation_id)
            elif payload.status == "ACTIVE" and result.get("status") == "ARCHIVED":
                result = conversations.activate_conversation(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        except ValueError as exc:
            message = "当前模型连接不可用。" if str(exc) == "MODEL_NOT_AVAILABLE" else "会话当前不能修改。"
            return error_response(409, str(exc), message, request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.delete("/api/v1/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str, request: Request,
                            idempotency_key: str = Header(default="conversation-delete")):
        del idempotency_key
        try:
            result = conversations.soft_delete_conversation(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope({"conversation": result, "disk_files_changed": False, "undo_started": False}, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/restore")
    def restore_conversation(conversation_id: str, request: Request,
                             idempotency_key: str = Header(default="conversation-restore")):
        del idempotency_key
        try:
            result = conversations.restore_conversation(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/messages")
    def list_conversation_messages(conversation_id: str, request: Request, include_redacted: bool = False):
        try:
            result = conversations.list_messages(conversation_id, include_redacted=include_redacted)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/messages", status_code=201)
    def append_conversation_message(conversation_id: str, payload: ConversationMessageRequest, request: Request,
                                    idempotency_key: str = Header(default="conversation-message")):
        del idempotency_key
        try:
            if payload.expected_context_revision is not None:
                current_context = conversations.get_context(conversation_id)
                if current_context["context_revision"] != payload.expected_context_revision:
                    raise ValueError("CONTEXT_REVISION_CONFLICT")
            resolved = reference_resolver.resolve(
                conversation_id, payload.content,
                selected_file_ids=payload.selected_file_ids,
                focused_file_id=payload.focused_file_id,
                active_category_id=payload.active_category_id,
            ) if payload.role == "USER" else {"source": "NONE", "file_ids": []}
            if resolved.get("missing"):
                raise ReferenceResolutionError(
                    "REFERENCE_FILE_MISSING",
                    details={"missing": resolved["missing"],
                             "remaining": [item for item in resolved["file_ids"] if item not in resolved["missing"]]},
                )
            if resolved.get("changed"):
                raise ReferenceResolutionError("REFERENCE_FILE_CHANGED", details={"changed": resolved["changed"]})
            result = conversations.append_message(conversation_id, payload.role, payload.content,
                                                  message_type=payload.message_type, metadata=payload.metadata,
                                                  referenced_plan_version_id=payload.referenced_plan_version_id,
                                                  referenced_execution_round_id=payload.referenced_execution_round_id,
                                                  referenced_file_ids=resolved.get("file_ids"),
                                                  reference_source=None if resolved.get("source") == "NONE" else resolved.get("source"),
                                                  reference_role=payload.reference_role)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        except ReferenceResolutionError as exc:
            return error_response(409, exc.code, reference_error_message(exc.code), request.state.request_id, exc.details)
        except ValueError as exc:
            return error_response(409, str(exc), "消息不能写入当前会话。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/turns")
    def first_conversation_turn(conversation_id: str, payload: ConversationTurnRequest, request: Request,
                                idempotency_key: str = Header(default="conversation-first-turn")):
        del idempotency_key
        if not payload.acknowledge_privacy:
            return error_response(409, "PRIVACY_CONSENT_REQUIRED", "首次分析前需要确认内容授权。", request.state.request_id)
        try:
            # In a brand-new Conversation, phrases such as “这些照片” refer
            # to the newly authorized folder, not to a prior message's file
            # set. Keep deterministic file-reference validation for explicit
            # selections/focus/filenames, while allowing the first organize
            # request to establish the initial scope through the scanner.
            first_context = conversations.get_context(conversation_id)
            is_first_organization = not first_context.get("current_plan_version_id") and not first_context.get("current_execution_round_id")
            try:
                resolved = reference_resolver.resolve(
                    conversation_id, payload.content,
                    selected_file_ids=payload.selected_file_ids,
                    focused_file_id=payload.focused_file_id,
                    active_category_id=payload.active_category_id,
                )
            except ReferenceResolutionError as exc:
                if not (is_first_organization and exc.code == "REFERENCE_AMBIGUOUS" and
                        not payload.selected_file_ids and not payload.focused_file_id):
                    raise
                resolved = {"source": "NONE", "file_ids": [], "missing": [], "changed": []}
            if resolved.get("missing"):
                raise ReferenceResolutionError("REFERENCE_FILE_MISSING", details={"missing": resolved["missing"]})
            if resolved.get("changed"):
                raise ReferenceResolutionError("REFERENCE_FILE_CHANGED", details={"changed": resolved["changed"]})
            user_message = conversations.append_message(
                conversation_id, "USER", payload.content.strip(),
                referenced_file_ids=resolved.get("file_ids"),
                reference_source=None if resolved.get("source") == "NONE" else resolved.get("source"),
                reference_role=payload.reference_role,
            )
            progress: list[dict[str, Any]] = []
            result = first_analysis.run(
                conversation_id,
                user_message=payload.content.strip(),
                message_id=user_message["id"],
                acknowledge_privacy=True,
                progress=progress.append,
            )
            result["user_message"] = user_message
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        except ReferenceResolutionError as exc:
            return error_response(409, exc.code, reference_error_message(exc.code), request.state.request_id, exc.details)
        except FirstAnalysisError as exc:
            return error_response(409, exc.code, str(exc), request.state.request_id, exc.details)
        except (BudgetError, ModelError, ModelTransportError, PrivacyError, TaxonomyPlanningError) as exc:
            return error_response(409, getattr(exc, "code", str(exc)), "首次 AI 分析不可用或授权不足。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "首次整理分析无法完成。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/references/resolve")
    def resolve_conversation_references(conversation_id: str, payload: ConversationMessageRequest, request: Request):
        try:
            result = reference_resolver.resolve(
                conversation_id, payload.content,
                selected_file_ids=payload.selected_file_ids,
                focused_file_id=payload.focused_file_id,
                active_category_id=payload.active_category_id,
            )
        except ReferenceResolutionError as exc:
            return error_response(409, exc.code, reference_error_message(exc.code), request.state.request_id, exc.details)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/context")
    def get_conversation_context(conversation_id: str, request: Request):
        try:
            result = conversations.get_context(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话状态不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.patch("/api/v1/conversations/{conversation_id}/context")
    def update_conversation_context(conversation_id: str, payload: ConversationContextUpdateRequest, request: Request,
                                    idempotency_key: str = Header(default="conversation-context")):
        del idempotency_key
        try:
            result = conversations.update_context(conversation_id, payload.expected_revision, payload.changes)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话状态不存在。", request.state.request_id)
        except ValueError as exc:
            status = 409 if str(exc) == "CONTEXT_REVISION_CONFLICT" else 422
            return error_response(status, str(exc), "会话当前状态已变化，请重新读取后再更新。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/plans")
    def list_conversation_plans(conversation_id: str, request: Request):
        try:
            result = conversations.list_plan_versions(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/plans", status_code=201)
    def create_conversation_plan(conversation_id: str, payload: ConversationPlanVersionRequest, request: Request,
                                 idempotency_key: str = Header(default="conversation-plan")):
        del idempotency_key
        try:
            result = plan_versions.create_new_version(conversation_id, **payload.model_dump(mode="python"))
        except KeyError:
            return error_response(404, "CONVERSATION_OR_PLAN_NOT_FOUND", "会话或核心计划不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "方案版本基于过期会话状态或引用不一致。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/plan-versions")
    def list_conversation_plan_versions(conversation_id: str, request: Request, limit: int = Query(20, ge=1, le=100)):
        try:
            result = plan_versions.list(conversation_id)[-limit:]
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/plan-versions/current")
    def get_current_conversation_plan_version(conversation_id: str, request: Request):
        try:
            result = plan_versions.current(conversation_id)
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "当前方案版本不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/plan-versions/{version_id}")
    def get_conversation_plan_version(conversation_id: str, version_id: str, request: Request):
        try:
            result = plan_versions.get(version_id)
            if result["conversation_id"] != conversation_id:
                raise KeyError(version_id)
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "方案版本不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/plan-versions/{version_id}/diff")
    def diff_conversation_plan_version(conversation_id: str, version_id: str, request: Request,
                                       from_version_id: str | None = None):
        try:
            target = plan_versions.get(version_id)
            if target["conversation_id"] != conversation_id:
                raise KeyError(version_id)
            parent_id = from_version_id or target.get("parent_plan_version_id")
            if not parent_id:
                return envelope({"old_plan_version_id": None, "new_plan_version_id": version_id,
                                 "categories_added": [], "categories_removed": [], "category_changes": [],
                                 "file_changes": [], "affected_file_ids": [],
                                 "summary_counts": {"total": 0, "unchanged": 0}}, request.state.request_id)
            result = plan_versions.diff(parent_id, version_id)
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "方案版本不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "方案版本无法比较。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/plan-versions/{version_id}/approve", status_code=200)
    def approve_conversation_plan_version(conversation_id: str, version_id: str,
                                          payload: ConversationPlanVersionApproveRequest, request: Request,
                                          idempotency_key: str = Header(default="conversation-plan-approve")):
        del idempotency_key
        try:
            requested = plan_versions.get(version_id)
            if requested["conversation_id"] != conversation_id:
                raise KeyError(version_id)
            if payload.plan_hash and requested.get("plan_hash") != payload.plan_hash:
                return error_response(409, "PLAN_HASH_MISMATCH", "方案内容摘要已不匹配。", request.state.request_id)
            validation = session_recovery.revalidate_plan(conversation_id, version_id)
            if not validation["valid"]:
                return error_response(409, "PLAN_REVALIDATION_REQUIRED", "方案基于旧的文件状态，需要先同步并重新确认。", request.state.request_id,
                                       {"reason_codes": validation["reason_codes"], "reconciliation": validation["reconciliation"]})
            result = post_execution.approve(conversation_id, version_id, **payload.model_dump(mode="python"))
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "方案版本不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "方案版本无法批准或批准已失效。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/workspace-state")
    def get_conversation_workspace_state(conversation_id: str, request: Request):
        try:
            result = post_execution.workspace.current_state(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/refinements/prepare")
    def prepare_conversation_refinement(conversation_id: str, payload: ConversationRefinementRequest,
                                        request: Request,
                                        idempotency_key: str = Header(default="conversation-refinement")):
        del idempotency_key
        try:
            result = post_execution.prepare_refinement(
                conversation_id, user_message=payload.user_message,
                confirmed_global=payload.confirmed_global,
                explicit_file_ids=payload.referenced_file_ids,
                trigger_message_id=payload.trigger_message_id,
            )
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        except (BudgetError, ModelError, ModelTransportError, PrivacyError) as exc:
            code = getattr(exc, "code", str(exc))
            return error_response(409, code, "本轮 AI 分析不可用或授权不足。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "无法准备本轮整理调整。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/plan-versions/{version_id}/execute")
    def execute_conversation_refinement(conversation_id: str, version_id: str,
                                        payload: ConversationRefinementExecuteRequest, request: Request,
                                        idempotency_key: str = Header(default="conversation-refinement-execute")):
        del idempotency_key
        try:
            validation = session_recovery.revalidate_plan(conversation_id, version_id)
            if not validation["valid"]:
                return error_response(409, "PLAN_REVALIDATION_REQUIRED", "方案执行前发现文件状态变化，需要重新确认。", request.state.request_id,
                                       {"reason_codes": validation["reason_codes"], "reconciliation": validation["reconciliation"]})
            result = post_execution.execute(conversation_id, version_id, **payload.model_dump(mode="python"))
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "方案版本不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "方案已过期、未批准或执行条件发生变化。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/plan-versions/{version_id}/restore", status_code=201)
    def restore_conversation_plan_version(conversation_id: str, version_id: str,
                                          payload: ConversationPlanVersionRestoreRequest, request: Request,
                                          idempotency_key: str = Header(default="conversation-plan-restore")):
        del idempotency_key
        try:
            result = plan_versions.restore(conversation_id, version_id, **payload.model_dump(mode="python"))
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "方案版本不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "旧方案无法安全恢复，请重新生成方案。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/plan-versions/{version_id}/execution-rounds", status_code=201)
    def request_conversation_plan_execution(conversation_id: str, version_id: str,
                                            payload: ConversationPlanVersionExecutionRequest, request: Request,
                                            idempotency_key: str = Header(default="conversation-plan-execution")):
        del idempotency_key
        try:
            result = plan_versions.request_execution(conversation_id, version_id, **payload.model_dump(mode="python"))
        except KeyError:
            return error_response(404, "PLAN_VERSION_NOT_FOUND", "方案版本不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "方案版本未批准、已过期或执行条件发生变化。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/executions")
    def list_conversation_executions(conversation_id: str, request: Request):
        try:
            result = conversations.list_execution_rounds(conversation_id)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/reversible-executions")
    def list_reversible_executions(conversation_id: str, request: Request):
        return envelope(conversational_undo.reversible_executions(conversation_id), request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/undo-plans")
    def list_conversation_undo_plans(conversation_id: str, request: Request):
        return envelope(conversational_undo.list(conversation_id), request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/undo-plans", status_code=201)
    def request_conversation_undo(conversation_id: str, payload: ConversationUndoRequest, request: Request,
                                  idempotency_key: str = Header(default="conversation-undo-preview")):
        del idempotency_key
        try:
            result = conversational_undo.request(conversation_id, **payload.model_dump(mode="python"))
        except KeyError:
            return error_response(404, "UNDO_TARGET_NOT_FOUND", "没有找到可撤销的执行记录。", request.state.request_id)
        except UndoError as exc:
            return error_response(409, exc.code, "当前操作无法安全撤销。", request.state.request_id, exc.details)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/undo-plans/{undo_plan_id}")
    def get_conversation_undo_plan(conversation_id: str, undo_plan_id: str, request: Request):
        try:
            result = conversational_undo.get(undo_plan_id)
            if result["conversation_id"] != conversation_id:
                raise KeyError(undo_plan_id)
        except KeyError:
            return error_response(404, "UNDO_PLAN_NOT_FOUND", "撤销预览不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/undo-plans/{undo_plan_id}/approve")
    def approve_conversation_undo(conversation_id: str, undo_plan_id: str,
                                  payload: ConversationUndoApprovalRequest, request: Request,
                                  idempotency_key: str = Header(default="conversation-undo-approve")):
        del idempotency_key
        try:
            result = conversational_undo.approve(conversation_id, undo_plan_id, payload.plan_hash, payload.authorization)
        except KeyError:
            return error_response(404, "UNDO_PLAN_NOT_FOUND", "撤销预览不存在。", request.state.request_id)
        except UndoError as exc:
            return error_response(409, exc.code, "撤销预览已过期或存在冲突。", request.state.request_id, exc.details)
        except ValueError as exc:
            return error_response(409, str(exc), "撤销计划批准失败。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/undo-plans/{undo_plan_id}/execute", status_code=202)
    def execute_conversation_undo(conversation_id: str, undo_plan_id: str,
                                  payload: ConversationUndoExecuteRequest, request: Request,
                                  idempotency_key: str = Header(default="conversation-undo-execute")):
        del idempotency_key
        try:
            result = conversational_undo.execute(conversation_id, undo_plan_id, payload.plan_hash)
        except KeyError:
            return error_response(404, "UNDO_PLAN_NOT_FOUND", "撤销预览不存在。", request.state.request_id)
        except UndoError as exc:
            return error_response(409, exc.code, "撤销执行被安全检查阻止。", request.state.request_id, exc.details)
        except ValueError as exc:
            return error_response(409, str(exc), "撤销执行条件发生变化。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/undo-plans/{undo_plan_id}/cancel")
    def cancel_conversation_undo(conversation_id: str, undo_plan_id: str, request: Request,
                                 idempotency_key: str = Header(default="conversation-undo-cancel")):
        del idempotency_key
        try:
            result = conversational_undo.cancel(conversation_id, undo_plan_id)
        except KeyError:
            return error_response(404, "UNDO_PLAN_NOT_FOUND", "撤销预览不存在。", request.state.request_id)
        except UndoError as exc:
            return error_response(409, exc.code, "撤销预览当前不能取消。", request.state.request_id, exc.details)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/executions", status_code=201)
    def create_conversation_execution(conversation_id: str, payload: ConversationExecutionRoundRequest, request: Request,
                                      idempotency_key: str = Header(default="conversation-execution")):
        del idempotency_key
        try:
            result = conversations.create_execution_round(conversation_id, payload.plan_version_id, payload.execution_plan_id,
                                                          expected_context_revision=payload.expected_context_revision,
                                                          status=payload.status, summary=payload.summary,
                                                          affected_file_count=payload.affected_file_count)
        except KeyError:
            return error_response(404, "CONVERSATION_OR_PLAN_NOT_FOUND", "会话、方案版本或执行计划不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "执行轮次引用不一致或会话状态已变化。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/conversations/{conversation_id}/files")
    def list_conversation_files(conversation_id: str, request: Request, include_removed: bool = False):
        try:
            result = conversations.list_conversation_files(conversation_id, include_removed=include_removed)
        except KeyError:
            return error_response(404, "CONVERSATION_NOT_FOUND", "会话不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/files", status_code=201)
    def attach_conversation_file(conversation_id: str, payload: ConversationFileRequest, request: Request,
                                 idempotency_key: str = Header(default="conversation-file")):
        del idempotency_key
        try:
            result = conversations.attach_file_to_conversation(conversation_id, payload.file_id)
        except KeyError:
            return error_response(404, "CONVERSATION_OR_FILE_NOT_FOUND", "会话或文件不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/files/{file_id}/verify")
    def verify_conversation_file(conversation_id: str, file_id: str, request: Request,
                                 idempotency_key: str = Header(default="conversation-file-verify")):
        del idempotency_key
        try:
            result = conversations.verify_conversation_file(conversation_id, file_id)
        except KeyError:
            return error_response(404, "CONVERSATION_FILE_NOT_FOUND", "会话文件引用不存在。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.post("/api/v1/conversations/{conversation_id}/tasks")
    def link_conversation_task(conversation_id: str, payload: ConversationTaskLinkRequest, request: Request,
                               idempotency_key: str = Header(default="conversation-task-link")):
        del idempotency_key
        try:
            result = conversations.link_task(conversation_id, payload.task_id, payload.plan_version_id)
        except KeyError:
            return error_response(404, "CONVERSATION_OR_TASK_NOT_FOUND", "会话或任务不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "任务与会话方案版本不匹配。", request.state.request_id)
        return envelope(result, request.state.request_id)

    @app.get("/api/v1/tasks")
    def list_tasks(request: Request, view: str = Query("active", pattern="^(active|deleted|all)$")):
        return envelope({"items": repository.list(view)}, request.state.request_id)

    @app.post("/api/v1/tasks/batch-delete")
    def batch_delete_tasks(payload: TaskBatchRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        if any(coordinator.is_active(task_id) for task_id in payload.task_ids):
            return error_response(409, "TASK_DELETE_BLOCKED", "运行中的任务必须先安全取消并等待 worker 结束。", request.state.request_id)
        try:
            items = repository.soft_delete(payload.task_ids, "user_batch", payload.delete_reason)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "一个或多个任务不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc).split(":", 1)[0], "运行中或待恢复任务不能直接删除。", request.state.request_id)
        return envelope({"items": items, "deleted": len(items)}, request.state.request_id)

    @app.post("/api/v1/tasks/batch-restore")
    def batch_restore_tasks(payload: TaskBatchRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            items = repository.restore(payload.task_ids)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "一个或多个任务不存在。", request.state.request_id)
        return envelope({"items": items, "restored": len(items)}, request.state.request_id)

    @app.post("/api/v1/tasks/batch-permanent-delete")
    def batch_permanently_delete_tasks(payload: TaskBatchRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            repository.permanently_delete_many(payload.task_ids)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "一个或多个任务不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(
                409, str(exc),
                "至少一个任务未进入最近删除，或仍保留计划、操作日志或 Undo 安全依赖；不会删除磁盘文件。",
                request.state.request_id,
            )
        return envelope({"permanently_deleted": len(set(payload.task_ids)), "disk_files_changed": False}, request.state.request_id)

    @app.post("/api/v1/tasks", status_code=201)
    def create_task(payload: CreateTaskRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            classification_request = dict(payload.classification_request)
            if payload.user_instructions:
                classification_request["user_instructions"] = payload.user_instructions
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

    @app.patch("/api/v1/tasks/{task_id}")
    def rename_task(task_id: str, payload: RenameTaskRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            task = repository.rename(task_id, payload.expected_revision, payload.name)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "任务名称或版本已变化。", request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.delete("/api/v1/tasks/{task_id}")
    def delete_task(task_id: str, payload: DeleteTaskRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        if coordinator.is_active(task_id):
            return error_response(409, "TASK_DELETE_BLOCKED", "运行中的任务必须先安全取消并等待 worker 结束。", request.state.request_id)
        try:
            repository.assert_revision(task_id, payload.expected_revision)
            task = repository.soft_delete([task_id], "user", payload.delete_reason)[0]
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc).split(":", 1)[0], "运行中、待恢复或已变化的任务不能直接删除。", request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/restore")
    def restore_task(task_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            repository.assert_revision(task_id, payload.expected_revision)
            task = repository.restore([task_id])[0]
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "任务版本已变化。", request.state.request_id)
        return envelope(task, request.state.request_id)

    @app.delete("/api/v1/tasks/{task_id}/permanent")
    def permanently_delete_task(task_id: str, payload: ExpectedRevisionRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            repository.assert_revision(task_id, payload.expected_revision)
            repository.permanently_delete(task_id)
        except KeyError:
            return error_response(404, "TASK_NOT_FOUND", "任务不存在。", request.state.request_id)
        except ValueError as exc:
            code = str(exc)
            message = "该任务仍保留计划、操作日志或 Undo 安全依赖，不能永久删除；不会删除磁盘文件。"
            return error_response(409, code, message, request.state.request_id)
        return envelope({"permanently_deleted": True, "disk_files_changed": False}, request.state.request_id)

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
        modalities = repository.eligible_modalities(task_id)
        try:
            models.require_capabilities(started_task["model_profile_id"], modalities)
        except ModelError as exc:
            repository.append_event(task_id, "AI_CAPABILITY_MISMATCH", {
                "model_profile_id": started_task["model_profile_id"],
                "code": str(exc),
                "missing_capabilities": getattr(exc, "missing_capabilities", []),
            })
            return error_response(409, str(exc), "当前模型能力不足或尚未验证，请在模型连接页完成探测后重试。", request.state.request_id,
                                  {"missing_capabilities": getattr(exc, "missing_capabilities", [])})
        ai_planner.plan_task(task_id)
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
            if payload.force_refresh:
                from guixu.application.semantic_cache import fingerprint_for_path
                for file_id in payload.file_ids:
                    file = repository.get_file(task_id, file_id)
                    path = Path(file["current_path"])
                    if path.is_file():
                        evidence_cache.force_refresh(file_id, fingerprint_for_path(path))
            outcomes = [parsing.parse(task_id, file_id) for file_id in payload.file_ids]
        except KeyError:
            return error_response(404, "FILE_NOT_FOUND", "任务或文件不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "文件无法按当前状态重新解析。", request.state.request_id)
        return envelope({"command_id": str(uuid.uuid4()), "status": "completed", "profiles": [item.profile.model_dump(mode="json") for item in outcomes]}, request.state.request_id)

    @app.get("/api/v1/cache/status")
    def cache_status(request: Request, file_id: str | None = Query(default=None)):
        return envelope(evidence_cache.get_cache_status(file_id=file_id), request.state.request_id)

    @app.post("/api/v1/cache/cleanup")
    def cache_cleanup(request: Request, older_than_days: int = Query(default=30, ge=0, le=3650)):
        return envelope({"cleared": evidence_cache.cleanup_invalid_cache(older_than_days=older_than_days)}, request.state.request_id)

    @app.post("/api/v1/cache/clear")
    def cache_clear(request: Request, file_id: str | None = Query(default=None)):
        # The API only deletes local evidence rows.  It never touches source
        # files, conversations, plans, executions, journals, or undo records.
        return envelope({"cleared": evidence_cache.clear(file_id=file_id)}, request.state.request_id)

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
        ai_classifier.classify_taxonomy(task_id, taxonomy)
        task = repository.advance_after_classification(task_id)
        repository.append_event(task_id, "AI_CLASSIFICATION_COMPLETED", {"taxonomy_id": taxonomy_id})
        return envelope({"command_id": str(uuid.uuid4()), "status": "completed", "taxonomy": taxonomy,
                         "classification_status": "completed", "task": task}, request.state.request_id)

    @app.put("/api/v1/tasks/{task_id}/taxonomies/{taxonomy_id}")
    def update_taxonomy(task_id: str, taxonomy_id: str, payload: UpdateTaxonomyRequest, request: Request,
                        idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            updated = taxonomies.replace_draft(task_id, taxonomy_id, payload.tree_hash, payload.nodes,
                                               payload.expected_revision)
        except KeyError:
            return error_response(404, "TAXONOMY_NOT_FOUND", "分类树不存在。", request.state.request_id)
        except ValueError as exc:
            return error_response(409, str(exc), "分类树已变化或编辑结果不符合约束。", request.state.request_id)
        repository.append_event(task_id, "TAXONOMY_EDITED", {"taxonomy_id": updated["taxonomy_id"],
                                                               "node_count": len(updated["nodes"])})
        return envelope(updated, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/taxonomies/{taxonomy_id}/classify", status_code=202)
    def retry_taxonomy_classification(task_id: str, taxonomy_id: str, request: Request,
                                      idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            taxonomy = taxonomies.get(task_id, taxonomy_id)
        except KeyError:
            return error_response(404, "TAXONOMY_NOT_FOUND", "分类树不存在。", request.state.request_id)
        if taxonomy["status"] != "approved":
            return error_response(409, "TAXONOMY_NOT_APPROVED", "必须先批准分类树。", request.state.request_id)
        ai_classifier.classify_taxonomy(task_id, taxonomy)
        task = repository.advance_after_classification(task_id)
        repository.append_event(task_id, "AI_CLASSIFICATION_COMPLETED", {"taxonomy_id": taxonomy_id, "retry": True})
        return envelope({"command_id": str(uuid.uuid4()), "status": "completed", "task": task}, request.state.request_id)

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
        return envelope({**asdict(plan), **journal.plan_metadata(plan.plan_id),
                         "results": journal.operation_results(plan.plan_id)}, request.state.request_id)

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
        return envelope({**asdict(plan), **journal.plan_metadata(plan.plan_id),
                         "results": journal.operation_results(plan.plan_id)}, request.state.request_id)

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
        return envelope({"plan_id": payload.plan_id, "plan_hash": payload.plan_hash,
                         **journal.plan_metadata(payload.plan_id)}, request.state.request_id)

    @app.post("/api/v1/tasks/{task_id}/execute", status_code=202)
    def execute_plan(task_id: str, payload: ExecutePlanRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key")):
        del idempotency_key
        try:
            plan = coordinator.execute(task_id, payload.plan_id, payload.plan_hash, payload.expected_revision)
        except (ValueError, KeyError) as exc:
            return error_response(409, str(exc), "计划未批准、已失效或执行条件发生变化。", request.state.request_id)
        return envelope({**asdict(plan), **journal.plan_metadata(plan.plan_id),
                         "results": journal.operation_results(plan.plan_id)}, request.state.request_id)

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
        return envelope({**asdict(plan), **journal.plan_metadata(plan.plan_id)}, request.state.request_id)

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
