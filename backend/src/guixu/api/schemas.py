from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from guixu.domain.settings import TaskSettings


class RegisterGrantRequest(BaseModel):
    path: str
    purpose: str = "source"


class CreateTaskRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    source_grant: str
    output_grant: str | None = None
    settings: TaskSettings
    classification_request: dict[str, Any] = Field(default_factory=dict)
    model_profile_id: str | None = None
    user_instructions: str = Field(default="", max_length=10_000)


class TaskMutationRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class RenameTaskRequest(TaskMutationRequest):
    name: str = Field(min_length=1, max_length=80)


class DeleteTaskRequest(TaskMutationRequest):
    delete_reason: str | None = Field(default=None, max_length=500)


class TaskBatchRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=500)
    delete_reason: str | None = Field(default=None, max_length=500)


class CreateConversationRequest(BaseModel):
    title: str = Field(default="未命名整理", min_length=1, max_length=160)
    model_profile_id: str | None = None
    # The API accepts a grant reference, never an arbitrary filesystem path.
    scope_grant: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class ConversationPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: str | None = Field(default=None, pattern="^(ACTIVE|ARCHIVED)$")


class ConversationMessageRequest(BaseModel):
    role: str = Field(pattern="^(USER|ASSISTANT|SYSTEM_EVENT)$")
    content: str = Field(min_length=1, max_length=100_000)
    message_type: str = Field(default="TEXT", pattern="^(TEXT|STATUS|PLAN_PROPOSAL|EXECUTION_RESULT|ERROR|SYSTEM_EVENT)$")
    metadata: dict[str, Any] = Field(default_factory=dict)
    referenced_plan_version_id: str | None = None
    referenced_execution_round_id: str | None = None
    selected_file_ids: list[str] = Field(default_factory=list, max_length=10_000)
    focused_file_id: str | None = None
    active_category_id: str | None = None
    expected_context_revision: int | None = Field(default=None, ge=1)
    reference_role: str = Field(default="SUBJECT", pattern="^(SUBJECT|RESULT|CONTEXT)$")


class ConversationContextUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    changes: dict[str, Any] = Field(default_factory=dict)


class ConversationPlanVersionRequest(BaseModel):
    expected_context_revision: int | None = Field(default=None, ge=1)
    basis_context_revision: int | None = Field(default=None, ge=1)
    basis_file_state_revision: int | None = Field(default=None, ge=1)
    parent_plan_version_id: str | None = None
    source: str = Field(default="USER_REQUEST", pattern="^(USER_REQUEST|SYSTEM|LEGACY)$")
    status: str = Field(default="DRAFT", pattern="^(DRAFT|PROPOSED|APPROVED|EXECUTED|SUPERSEDED|CANCELLED)$")
    taxonomy_id: str | None = None
    taxonomy_snapshot: dict[str, Any] = Field(default_factory=dict)
    plan_id: str | None = None
    plan_hash: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    summary: str = Field(default="", max_length=10_000)
    change_summary: dict[str, Any] = Field(default_factory=dict)
    affected_file_count: int = Field(default=0, ge=0)
    kept_file_count: int = Field(default=0, ge=0)
    conflict_count: int = Field(default=0, ge=0)
    created_by_message_id: str | None = None
    restored_from_version_id: str | None = None


class ConversationPlanVersionApproveRequest(BaseModel):
    expected_context_revision: int | None = Field(default=None, ge=1)
    plan_hash: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    authorization: dict[str, Any] = Field(default_factory=dict)


class ConversationPlanVersionRestoreRequest(BaseModel):
    expected_context_revision: int | None = Field(default=None, ge=1)
    expected_current_plan_version_id: str | None = None


class ConversationPlanVersionExecutionRequest(BaseModel):
    expected_context_revision: int | None = Field(default=None, ge=1)
    plan_hash: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    status: str = Field(default="PENDING", pattern="^(PENDING|RUNNING)$")
    summary: dict[str, Any] = Field(default_factory=dict)
    affected_file_count: int = Field(default=0, ge=0)


class ConversationRefinementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_message: str = Field(min_length=1, max_length=12_000)
    confirmed_global: bool = False
    referenced_file_ids: list[str] = Field(default_factory=list, max_length=10_000)
    trigger_message_id: str | None = None


class ConversationRefinementExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_context_revision: int | None = Field(default=None, ge=1)
    plan_hash: str | None = Field(default=None, min_length=64, max_length=64)


class ConversationExecutionRoundRequest(BaseModel):
    expected_context_revision: int | None = Field(default=None, ge=1)
    plan_version_id: str
    execution_plan_id: str
    status: str = Field(default="PENDING", pattern="^(PENDING|RUNNING|COMPLETED|FAILED|CANCELLED|RECOVERY_REQUIRED)$")
    summary: dict[str, Any] = Field(default_factory=dict)
    affected_file_count: int = Field(default=0, ge=0)


class ConversationFileRequest(BaseModel):
    file_id: str


class ConversationTaskLinkRequest(BaseModel):
    task_id: str
    plan_version_id: str | None = None


class ConversationRecoveryRequest(BaseModel):
    trigger: str = Field(default="MANUAL", pattern="^(STARTUP|OPEN|BEFORE_OPERATION|MANUAL)$")


class ConversationRelinkScopeRequest(BaseModel):
    scope_grant: str = Field(min_length=1)


class ConversationUndoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_message: str = Field(default="", max_length=12_000)
    execution_round_id: str | None = None
    referenced_file_ids: list[str] = Field(default_factory=list, max_length=10_000)


class ConversationUndoApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_hash: str = Field(pattern="^[0-9a-f]{64}$")
    authorization: dict[str, Any] = Field(default_factory=dict)


class ConversationUndoExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_hash: str = Field(pattern="^[0-9a-f]{64}$")


class StartTaskRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class ApprovePlanRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    plan_id: str
    plan_hash: str = Field(pattern="^[0-9a-f]{64}$")


class ExecutePlanRequest(ApprovePlanRequest):
    pass


class ComponentImportRequest(BaseModel):
    component_grant: str
    component_type: str = Field(pattern="^(ffmpeg|ocr|asr)$")
    expected_manifest_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class ReanalyzeRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    file_ids: list[str] = Field(min_length=1, max_length=500)
    force_refresh: bool = False


class ApproveTaxonomyRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    tree_hash: str = Field(pattern="^[0-9a-f]{64}$")


class UpdateTaxonomyRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    tree_hash: str = Field(pattern="^[0-9a-f]{64}$")
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=200)


class ReviewItemRequest(BaseModel):
    file_id: str
    taxonomy_id: str
    category_id: str | None
    decision: str = Field(pattern="^(accept|change|skip|quarantine)$")
    note: str = Field(default="", max_length=1000)


class BulkReviewRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    items: list[ReviewItemRequest] = Field(min_length=1, max_length=500)


class ModelOptionsRequest(BaseModel):
    model_config = {"extra": "forbid"}
    thinking_mode: str = Field(default="disabled", pattern="^(disabled|enabled|server_default)$")
    timeout_seconds: int = Field(default=60, ge=5, le=600)
    max_concurrency: int = Field(default=1, ge=1, le=4)
    batch_size: int = Field(default=20, ge=1, le=50)


class ModelInputRequest(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(pattern="^(deepseek|qwen_local)$")
    runtime: str = Field(pattern="^(deepseek|openai_compatible|ollama|lmstudio|vllm|llamacpp)$")
    base_url: str
    model_id: str = Field(min_length=1, max_length=200)
    trust_scope: str = Field(pattern="^(cloud|loopback|trusted_lan)$")
    options: ModelOptionsRequest = Field(default_factory=ModelOptionsRequest)
    enabled: bool = True


class ModelPatchRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    changes: dict[str, Any]


class ModelSecretRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    secret: str | None = Field(max_length=4096)


class ExpectedRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class ExportReportRequest(BaseModel):
    export_grant: str
    format: str = Field(pattern="^(json|csv)$")
    filename: str | None = Field(default=None, min_length=1, max_length=180)


class ConsentBudgetRequest(BaseModel):
    model_config = {"extra": "forbid"}
    max_calls: int = Field(default=500, ge=1, le=100_000)
    max_input_tokens: int = Field(default=1_000_000, ge=1)
    max_output_tokens: int = Field(default=200_000, ge=1)
    max_cost_micros: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern="^(CNY|USD)$")


class ConsentRequest(BaseModel):
    model_config = {"extra": "forbid"}
    expected_revision: int = Field(ge=1)
    provider_profile_id: str
    scope_hash: str = Field(pattern="^[0-9a-f]{64}$")
    data_types: list[str]
    budget: ConsentBudgetRequest
    acknowledge_content_disclosure: bool
