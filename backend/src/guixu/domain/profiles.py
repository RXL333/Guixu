from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer


class EvidenceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int | None = Field(default=None, ge=1)
    slide: int | None = Field(default=None, ge=1)
    sheet: str | None = Field(default=None, max_length=100)
    rows: list[int] | None = Field(default=None, max_length=2)
    paragraph: int | None = Field(default=None, ge=1)
    start_sec: float | None = Field(default=None, ge=0)
    end_sec: float | None = Field(default=None, ge=0)
    frame_id: str | None = Field(default=None, max_length=80)
    field: str | None = Field(default=None, max_length=80)

    @model_serializer(mode="wrap")
    def omit_absent_fields(self, serializer):
        return {key: value for key, value in serializer(self).items() if value is not None}


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["metadata", "extracted_text", "ocr", "visual_caption", "transcript", "subtitle", "user_context"]
    text: str = Field(max_length=12_000)
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)
    quality: Literal["high", "medium", "low"]
    origin: str = Field(min_length=1, max_length=100)


class SampledInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)


class Coverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["metadata_only", "sampled", "full"]
    total_pages: int | None = Field(default=None, ge=0)
    sampled_pages: list[int] = Field(default_factory=list)
    total_duration_sec: float | None = Field(default=None, ge=0)
    sampled_intervals: list[SampledInterval] = Field(default_factory=list)
    truncated: bool = False


class FileProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    file_id: str
    modality: Literal["image", "text", "document", "audio", "video", "other"]
    document_kind: Literal["pdf", "docx", "pptx", "xlsx"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_summary: str = Field(default="", max_length=2000)
    summary_origin: Literal["deterministic", "model", "none"] = "none"
    evidence: list[Evidence] = Field(default_factory=list, max_length=300)
    coverage: Coverage
    warnings: list[str] = Field(default_factory=list, max_length=40)
    capabilities_used: list[str] = Field(default_factory=list)
    parser_version: str


class ParseOutcome(BaseModel):
    status: Literal["ready", "partial", "failed", "unsupported"]
    profile: FileProfile
    cache_artifacts: list[str] = Field(default_factory=list)
