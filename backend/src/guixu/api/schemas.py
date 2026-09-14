from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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
    template_key: str | None = None
    template_version: int | None = Field(default=None, ge=1)
    user_instructions: str = Field(default="", max_length=10_000)
    rule_ids: list[str] = Field(default_factory=list)
    fixed_tree: dict[str, Any] | None = None


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


class DuplicateTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    template_key: str | None = None


class TemplateImportRequest(BaseModel):
    templates: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class RuleInputRequest(BaseModel):
    name: str
    priority: int = Field(ge=0)
    enabled: bool = True
    scope: dict[str, Any] = Field(default_factory=dict)
    condition: dict[str, Any]
    action: dict[str, Any]


class RuleTestRequest(BaseModel):
    task_id: str
    file_ids: list[str] = Field(max_length=500)
    draft_rule: RuleInputRequest


class ApproveTaxonomyRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    tree_hash: str = Field(pattern="^[0-9a-f]{64}$")


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
