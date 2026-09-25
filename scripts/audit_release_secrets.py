"""Scan a Windows release directory or portable ZIP for common secret signatures.

This is a release hygiene check, not a proof that arbitrary unknown credentials
cannot exist. It deliberately reports match categories and paths, never values.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


SECRET_PATTERNS = {
    "deepseek_key_like": re.compile(rb"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "github_token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "aws_access_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "private_key_pem": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "bearer_credential": re.compile(
        rb"(?i)authorization[\"'= :]{1,24}bearer[\s\"'=]+[A-Za-z0-9._~+/=-]{24,}"
    ),
    "inline_api_credential": re.compile(
        rb"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)"
        rb"[\"'\s:=]{1,16}[\"']?[A-Za-z0-9._~+/=-]{24,}"
    ),
}

DEV_PATH_SEGMENTS = {"node_modules", "tests", "maps"}
ENV_FILENAMES = {".env", ".env.local", ".env.development", ".env.production"}


def is_dev_asset(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return any(part.lower() in DEV_PATH_SEGMENTS for part in path.parts) or path.name.lower() in ENV_FILENAMES


def scan_directory(root: Path) -> tuple[int, int, list[dict[str, str]], list[str]]:
    entries = [path for path in root.rglob("*") if path.is_file()]
    findings: list[dict[str, str]] = []
    forbidden: list[str] = []
    scanned_bytes = 0
    for path in entries:
        relative = path.relative_to(root).as_posix()
        if is_dev_asset(relative):
            forbidden.append(relative)
        content = path.read_bytes()
        scanned_bytes += len(content)
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                findings.append({"path": relative, "pattern": label})
    return len(entries), scanned_bytes, findings, forbidden


def scan_zip(archive: Path) -> tuple[int, int, list[dict[str, str]], list[str]]:
    findings: list[dict[str, str]] = []
    forbidden: list[str] = []
    scanned_bytes = 0
    with ZipFile(archive) as bundle:
        entries = [entry for entry in bundle.infolist() if not entry.is_dir()]
        for entry in entries:
            if is_dev_asset(entry.filename):
                forbidden.append(entry.filename)
            content = bundle.read(entry)
            scanned_bytes += len(content)
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(content):
                    findings.append({"path": entry.filename, "pattern": label})
    return len(entries), scanned_bytes, findings, forbidden


def scan(path: Path) -> dict[str, object]:
    if path.is_dir():
        count, size, findings, forbidden = scan_directory(path)
    elif path.is_file() and path.suffix.lower() == ".zip":
        count, size, findings, forbidden = scan_zip(path)
    else:
        raise ValueError(f"Expected a release directory or .zip file: {path}")
    return {
        "path": str(path),
        "entries_scanned": count,
        "uncompressed_bytes_scanned": size,
        "dev_asset_paths": forbidden,
        "secret_signature_hits": findings,
        "result": "clean_by_known_signatures" if not findings and not forbidden else "findings",
        "limitations": "Known signatures only; not exhaustive for arbitrary credentials.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Release directories and/or portable ZIP files")
    args = parser.parse_args()
    results = []
    failed = False
    for path in args.paths:
        try:
            result = scan(path)
            failed |= result["result"] != "clean_by_known_signatures"
        except (OSError, BadZipFile, ValueError) as error:
            failed = True
            result = {"path": str(path), "result": "scan_error", "error_type": type(error).__name__}
        results.append(result)
    print(json.dumps({"scanner": "guixu-release-secret-signatures-v1", "results": results}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
