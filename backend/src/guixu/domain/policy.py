from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError


class PolicyError(ValueError):
    pass


class PolicyValidator:
    def __init__(self, schema_path: Path) -> None:
        self.validator = Draft202012Validator(json.loads(schema_path.read_text("utf-8")))

    def validate(self, output: dict[str, Any]) -> dict[str, Any]:
        try:
            self.validator.validate(output)
        except ValidationError as exc:
            raise PolicyError("POLICY_SCHEMA_INVALID") from exc
        if output["unknown_policy"] != "abstain":
            raise PolicyError("POLICY_UNKNOWN_MUST_ABSTAIN")
        return output
