from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PrivacySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_extracted_text: bool = True
    allow_derivative_images: bool = True
    allow_video_frames: bool = True
    allow_asr_text: bool = True
    allow_basename: bool = False
    allow_precise_location: bool = False
    allow_original_images: bool = False


class TaskBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_calls: int = Field(default=500, ge=1, le=100_000)
    max_input_tokens: int = Field(default=1_000_000, ge=1)
    max_output_tokens: int = Field(default=200_000, ge=1)
    max_cost_micros: int | None = Field(default=None, ge=0)
    currency: Literal["CNY", "USD"] | None = None


class TaskSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_mode: Literal["current_only", "recursive", "preserve_top_level"] = "preserve_top_level"
    operation_mode: Literal["preview_move", "direct_move", "copy", "report_only"] = "preview_move"
    organization_strategy: Literal["modality_first", "topic_first", "hybrid"] = "hybrid"
    classification_source: Literal["template", "fixed_categories", "auto_plan"] = "auto_plan"
    classification_mode: Literal["rules_first", "ai_first", "rules_only"] = "rules_first"
    max_depth: int = Field(default=2, ge=1, le=3)
    max_siblings: int = Field(default=12, ge=2, le=20)
    max_nodes_per_scope: int = Field(default=80, ge=2, le=200)
    max_new_directories: int = Field(default=200, ge=10, le=1000)
    analysis_preset: Literal["fast", "standard", "deep"] = "standard"
    uncertain_action: Literal["keep_in_place", "quarantine_after_review"] = "keep_in_place"
    collision_policy: Literal["keep_both", "skip"] = "keep_both"
    include_hidden: bool = False
    allow_file_rename: Literal[False] = False
    skip_project_directories: Literal[True] = True
    allowed_modalities: list[Literal["image", "text", "document", "audio", "video"]] = Field(
        default_factory=lambda: ["image", "text", "document", "audio", "video"], min_length=1
    )
    extension_allowlist: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list, max_length=100)
    large_file_warning_bytes: int = Field(default=2_147_483_648, ge=1_048_576)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    task_budget: TaskBudget = Field(default_factory=TaskBudget)

    @model_validator(mode="after")
    def validate_modes(self) -> "TaskSettings":
        if self.classification_mode == "rules_only" and self.classification_source == "auto_plan":
            raise ValueError("rules_only requires template or fixed_categories")
        normalized = []
        for suffix in self.extension_allowlist:
            if not suffix.startswith(".") or not suffix[1:].isalnum() or len(suffix) > 13:
                raise ValueError(f"invalid extension_allowlist entry: {suffix}")
            normalized.append(suffix.lower())
        if len(set(normalized)) != len(normalized):
            raise ValueError("extension_allowlist must contain unique values")
        self.extension_allowlist = normalized
        return self


def load_default_settings(project_root: Path) -> TaskSettings:
    payload = json.loads((project_root / "seed" / "default-settings.json").read_text("utf-8"))
    return TaskSettings.model_validate(payload)

