from __future__ import annotations

import hashlib
import importlib.metadata
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "artifacts" / "release"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def python_packages() -> list[dict[str, object]]:
    lock = tomllib.loads((ROOT / "backend" / "uv.lock").read_text("utf-8"))
    result = []
    for package in lock.get("package", []):
        name, version = package["name"], package.get("version", "workspace")
        try:
            metadata = importlib.metadata.metadata(name)
            license_name = metadata.get("License-Expression") or metadata.get("License") or "UNKNOWN"
        except importlib.metadata.PackageNotFoundError:
            license_name = "NOT_INSTALLED_BUILD_LOCK_ENTRY"
        result.append({"name": name, "version": version, "license": license_name})
    return sorted(result, key=lambda item: str(item["name"]))


def node_packages() -> list[dict[str, object]]:
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text("utf-8"))
    result = []
    for path, package in lock.get("packages", {}).items():
        if not path or "version" not in package:
            continue
        result.append({
            "name": path.rsplit("node_modules/", 1)[-1],
            "version": package["version"],
            "license": package.get("license", "UNKNOWN"),
            "dev": bool(package.get("dev", False)),
        })
    return sorted(result, key=lambda item: (str(item["name"]), str(item["version"])))


def main() -> int:
    RELEASE.mkdir(parents=True, exist_ok=True)
    sbom = {
        "format": "Guixu dependency inventory 1",
        "generated_at": datetime.now(UTC).isoformat(),
        "application": {"name": "Guixu", "version": "0.1.0"},
        "python_lock": python_packages(),
        "node_lock": node_packages(),
        "notes": ["License fields come from installed metadata or lock files and require human release review."],
    }
    (RELEASE / "SBOM.json").write_text(json.dumps(sbom, ensure_ascii=False, indent=2), "utf-8")
    candidates = [path for path in RELEASE.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt"]
    onedir = RELEASE / "Guixu-0.1.0"
    if onedir.is_dir():
        candidates.extend(path for path in onedir.rglob("*") if path.is_file())
    lines = [f"{digest(path)}  {path.relative_to(RELEASE).as_posix()}" for path in sorted(candidates)]
    (RELEASE / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
