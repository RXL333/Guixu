from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
import stat
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import text

from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.parsers.ocr import RAPIDOCR_VERSION, rapidocr_status


MAX_COMPONENT_FILES = 2_000
MAX_COMPONENT_BYTES = 4 * 1024 * 1024 * 1024
SCRIPT_SUFFIXES = {".bat", ".cmd", ".ps1", ".py", ".js", ".vbs", ".wsf"}


class ComponentError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentStatus:
    id: str
    component_type: str
    version: str | None
    status: str
    message: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    candidate = PurePosixPath(value.replace("\\", "/"))
    if candidate.is_absolute() or not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ComponentError("COMPONENT_PATH_INVALID")
    if candidate.suffix.lower() in SCRIPT_SUFFIXES:
        raise ComponentError("COMPONENT_SCRIPT_REJECTED")
    return candidate


class ComponentManager:
    def __init__(self, database: Database, install_root: Path) -> None:
        self.database = database
        self.install_root = install_root
        install_root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[ComponentStatus]:
        stored = self._stored()
        result = []
        for kind in ("ffmpeg", "ocr", "asr"):
            row = stored.get(kind)
            if row:
                result.append(ComponentStatus(row["id"], kind, row["version"], row["status"], self._message(row["status"])))
            else:
                result.append(self._detect_builtin(kind))
        return result

    def import_directory(self, source: Path, component_type: str, expected_manifest_sha256: str) -> ComponentStatus:
        if component_type not in {"ffmpeg", "ocr", "asr"}:
            raise ComponentError("COMPONENT_TYPE_INVALID")
        manifest_path = source / "manifest.json"
        if not manifest_path.is_file() or _sha256(manifest_path) != expected_manifest_sha256:
            raise ComponentError("COMPONENT_MANIFEST_HASH_MISMATCH")
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ComponentError("COMPONENT_MANIFEST_INVALID") from exc
        required = {"component_id", "version", "platform", "arch", "relative_files", "license_source", "entry_paths"}
        if not required.issubset(manifest) or not isinstance(manifest["relative_files"], list):
            raise ComponentError("COMPONENT_MANIFEST_INVALID")
        if manifest.get("component_type", component_type) != component_type:
            raise ComponentError("COMPONENT_TYPE_MISMATCH")
        files = manifest["relative_files"]
        if not 0 < len(files) <= MAX_COMPONENT_FILES:
            raise ComponentError("COMPONENT_FILE_LIMIT")
        checked: list[tuple[Path, PurePosixPath]] = []
        total = 0
        for item in files:
            if not isinstance(item, dict) or not {"path", "sha256"}.issubset(item):
                raise ComponentError("COMPONENT_MANIFEST_INVALID")
            relative = _safe_relative(str(item["path"]))
            source_file = source.joinpath(*relative.parts)
            try:
                attrs = source_file.lstat()
            except OSError as exc:
                raise ComponentError("COMPONENT_FILE_MISSING") from exc
            if stat.S_ISLNK(attrs.st_mode) or not stat.S_ISREG(attrs.st_mode) or (os.name == "nt" and getattr(attrs, "st_file_attributes", 0) & 0x400):
                raise ComponentError("COMPONENT_REPARSE_BLOCKED")
            total += attrs.st_size
            if total > MAX_COMPONENT_BYTES:
                raise ComponentError("COMPONENT_SIZE_LIMIT")
            if _sha256(source_file) != str(item["sha256"]).lower():
                raise ComponentError("COMPONENT_FILE_HASH_MISMATCH")
            checked.append((source_file, relative))
        for entry in manifest["entry_paths"]:
            relative = _safe_relative(str(entry))
            if not any(relative == item[1] for item in checked):
                raise ComponentError("COMPONENT_ENTRY_INVALID")
        component_id = str(manifest["component_id"])
        destination = self.install_root / component_type / component_id
        if destination.exists():
            raise ComponentError("COMPONENT_ALREADY_EXISTS")
        destination.mkdir(parents=True)
        try:
            for source_file, relative in checked:
                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_file, target)
                if _sha256(target) != _sha256(source_file):
                    raise ComponentError("COMPONENT_COPY_VERIFY_FAILED")
            shutil.copyfile(manifest_path, destination / "manifest.json")
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        record_id = str(uuid.uuid4())
        with self.database.begin() as connection:
            connection.execute(text("UPDATE components SET status='disabled' WHERE component_type=:kind AND status='ready'"), {"kind": component_type})
            connection.execute(text("""
                INSERT INTO components(id,component_type,version,status,install_path,manifest_json,manifest_sha256,last_verified_at)
                VALUES(:id,:kind,:version,'ready',:path,:manifest,:digest,:verified)
            """), {"id": record_id, "kind": component_type, "version": str(manifest["version"]), "path": str(destination), "manifest": encoded, "digest": expected_manifest_sha256, "verified": utc_now()})
        return ComponentStatus(record_id, component_type, str(manifest["version"]), "ready", "已校验并导入本地组件。")

    def _stored(self) -> dict[str, dict[str, Any]]:
        with self.database.engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM components WHERE status='ready' ORDER BY last_verified_at DESC")).mappings()
            return {row["component_type"]: dict(row) for row in rows}

    @staticmethod
    def _message(status: str) -> str:
        return {"ready": "本地组件已校验。", "invalid": "组件校验失败。", "disabled": "组件已禁用。"}.get(status, "组件不可用。")

    @staticmethod
    def _detect_builtin(kind: str) -> ComponentStatus:
        if kind == "ffmpeg":
            probe, encoder = shutil.which("ffprobe"), shutil.which("ffmpeg")
            if probe and encoder:
                return ComponentStatus("system-ffmpeg", kind, None, "ready", "已发现系统 ffmpeg/ffprobe；版本将在调用时验证。")
        elif kind == "ocr":
            ready, reason = rapidocr_status()
            if ready:
                return ComponentStatus("python-rapidocr", kind, RAPIDOCR_VERSION, "ready", "RapidOCR CPU 运行时与三个 SHA-256 已校验本地模型可用。")
            if reason in {"OCR_VERSION_UNVERIFIED", "OCR_RESOURCE_HASH_MISMATCH"}:
                return ComponentStatus("python-rapidocr", kind, None, "invalid", reason)
        elif kind == "asr":
            try:
                version = importlib.metadata.version("faster-whisper")
                return ComponentStatus("python-faster-whisper", kind, version, "disabled", "运行时已安装，但未配置已校验的本地模型目录。")
            except importlib.metadata.PackageNotFoundError:
                pass
        return ComponentStatus(f"missing-{kind}", kind, None, "missing", "组件未安装；相关能力将明确降级。")


def status_dict(status: ComponentStatus) -> dict[str, Any]:
    return asdict(status)
