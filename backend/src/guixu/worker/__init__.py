from __future__ import annotations

import argparse
import json
from pathlib import Path

from guixu.infrastructure.parsers.registry import ParserRegistry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    job = json.loads(Path(args.job).read_text("utf-8"))
    outcome = ParserRegistry().parse(Path(job["path"]), job["file_id"], job["preset"], Path(job["artifact_dir"]))
    Path(args.output).write_text(outcome.model_dump_json(), "utf-8")
    return 0

