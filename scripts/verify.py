from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RANGES: dict[str, list[list[str]] | None] = {
    "unit": [["uv", "run", "pytest", "tests/unit", "tests/contract"]],
    "safety": [["uv", "run", "pytest", "tests/safety", "tests/integration"]],
    "parsers": [["uv", "run", "--all-extras", "pytest", "tests/parsers", "tests/integration/test_api.py"]],
    "classification": [["uv", "run", "--all-extras", "pytest", "tests/classification", "tests/integration/test_api.py"]],
    "models": [["uv", "run", "--all-extras", "pytest", "tests/models", "tests/integration/test_api.py"]],
    "reliability": [["uv", "run", "--all-extras", "pytest", "tests/reliability", "tests/integration/test_safe_operations_api.py"]],
    "quality": [["uv", "run", "--all-extras", "pytest", "tests/security", "tests/contract", "tests/integration/test_desktop_security.py"]],
    "ui": [
        ["npm", "run", "typecheck"],
        ["npm", "run", "test", "--", "--run"],
        ["npm", "run", "build"],
    ],
}

if os.name == "nt":
    for commands in RANGES.values():
        if commands:
            for command in commands:
                if command[0] == "npm":
                    command[0] = "npm.cmd"


def run(command: list[str], cwd: Path) -> int:
    print(f"\n[{cwd.name}] {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=cwd, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Guixu verification scopes")
    parser.add_argument("scope", choices=[*RANGES, "all"])
    args = parser.parse_args()
    scopes = list(RANGES) if args.scope == "all" else [args.scope]
    exit_code = 0
    for scope in scopes:
        commands = RANGES[scope]
        if commands is None:
            print(f"[{scope}] NOT_IMPLEMENTED")
            if args.scope == scope:
                exit_code = max(exit_code, 2)
            continue
        cwd = ROOT / ("backend" if scope in {"unit", "safety", "parsers", "classification", "models", "reliability", "quality"} else "frontend")
        for command in commands:
            exit_code = max(exit_code, run(command, cwd))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
