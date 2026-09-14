from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from guixu.domain.settings import TaskSettings, load_default_settings


def test_defaults_are_loaded_from_seed(project_root):
    expected = json.loads((project_root / "seed" / "default-settings.json").read_text("utf-8"))
    assert load_default_settings(project_root).model_dump(mode="json") == expected


def test_rules_only_rejects_auto_plan():
    with pytest.raises(ValidationError, match="rules_only requires"):
        TaskSettings(classification_mode="rules_only", classification_source="auto_plan")

