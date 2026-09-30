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


BACKEND_SCOPES = {"unit", "safety", "parsers", "classification", "models", "reliability", "quality"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Guixu verification scopes")
    # Several scopes at once so that CI can run the backend scopes in a job that has
    # no Node toolchain, without having to shell out once per scope. A single scope
    # and `all` both keep working exactly as before.
    parser.add_argument("scope", choices=[*RANGES, "all"], nargs="+")
    args = parser.parse_args()
    selected = [scope for argument in args.scope for scope in (list(RANGES) if argument == "all" else [argument])]
    exit_code = 0
    for scope in selected:
        commands = RANGES[scope]
        if commands is None:
            print(f"[{scope}] NOT_IMPLEMENTED")
            exit_code = max(exit_code, 2)
            continue
        cwd = ROOT / ("backend" if scope in BACKEND_SCOPES else "frontend")
        for command in commands:
            exit_code = max(exit_code, run(command, cwd))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
