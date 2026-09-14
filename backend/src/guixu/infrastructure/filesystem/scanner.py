from __future__ import annotations

import fnmatch
import os
import stat
import uuid
from dataclasses import replace
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from guixu.domain.files import ScannedFile, detect_modality
from guixu.domain.settings import TaskSettings


PROJECT_MARKERS = {".git", ".venv", "node_modules", "package.json", "pyproject.toml"}
SYSTEM_NAMES = {"$recycle.bin", "system volume information", "windows", "program files", "program files (x86)"}


@dataclass(frozen=True)
class ScanScope:
    scope_id: str
    kind: str
    source_root: Path
    destination_root: Path
    display_name: str


@dataclass(frozen=True)
class ScanResult:
    scopes: list[ScanScope]
    files: list[ScannedFile]
    warnings: list[str]


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(os.name == "nt" and getattr(info, "st_file_attributes", 0) & 0x400)


def _is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    try:
        return bool(os.name == "nt" and getattr(path.stat(), "st_file_attributes", 0) & 0x2)
    except OSError:
        return False


def _project_directory(path: Path) -> bool:
    try:
        names = {child.name.lower() for child in path.iterdir()}
    except OSError:
        return False
    return any(marker.lower() in names for marker in PROJECT_MARKERS)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


class Scanner:
    def scan(self, root: Path, settings: TaskSettings, output_root: Path | None = None,
             excluded_roots: tuple[Path, ...] = ()) -> ScanResult:
        root = root.resolve(strict=True)
        warnings: list[str] = []
        output_roots = tuple(path.resolve(strict=False) for path in ((output_root,) if output_root else ()) + excluded_roots)
        scopes = self._build_scopes(root, settings, output_roots, warnings)
        files: list[ScannedFile] = []
        for scope in scopes:
            files.extend(self._scan_scope(scope, root, settings, output_roots, warnings))
        files = self._assign_companion_groups(files, warnings)
        files.sort(key=lambda item: (item.scope_id, item.relative_path.casefold(), item.relative_path))
        return ScanResult(scopes, files, warnings)

    def _assign_companion_groups(self, files: list[ScannedFile], warnings: list[str]) -> list[ScannedFile]:
        buckets: dict[tuple[str, str, str], list[int]] = {}
        for index, item in enumerate(files):
            key = (item.scope_id, str(Path(item.relative_path).parent).casefold(), item.path.stem.casefold())
            buckets.setdefault(key, []).append(index)
        result = list(files)
        pairs = [({".jpg", ".jpeg"}, {".xmp"}), ({".mp4", ".mkv", ".mov"}, {".srt", ".ass"}), ({".mp3", ".wav", ".flac", ".m4a"}, {".lrc"})]
        for key, indexes in buckets.items():
            suffixes = [files[index].path.suffix.lower() for index in indexes]
            matches = []
            for main_set, sidecar_set in pairs:
                mains = [index for index in indexes if files[index].path.suffix.lower() in main_set]
                sides = [index for index in indexes if files[index].path.suffix.lower() in sidecar_set]
                if mains or sides:
                    matches.append((mains, sides))
            if not matches:
                continue
            mains, sides = matches[0]
            if len(mains) == 1 and len(sides) == 1:
                group_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "|".join(key)))
                for index in (mains[0], sides[0]):
                    result[index] = replace(result[index], companion_group_id=group_id, scan_status="eligible", exclusion_code=None)
            else:
                warnings.append(f"COMPANION_AMBIGUOUS:{key[1]}/{key[2]}")
        return result

    def _build_scopes(
        self, root: Path, settings: TaskSettings, output_roots: tuple[Path, ...], warnings: list[str]
    ) -> list[ScanScope]:
        mode = settings.scan_mode
        if mode == "current_only":
            return [ScanScope("current", "current_only", root, root, root.name)]
        if mode == "recursive":
            return [ScanScope("whole", "whole_tree", root, root, root.name)]
        scopes = [ScanScope("root-loose", "root_loose", root, root, "根目录文件")]
        for child in sorted(root.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
            if child.is_dir() and not _is_reparse(child):
                reason = self._excluded_directory(child, settings, output_roots)
                if reason:
                    warnings.append(f"{reason}:{child.relative_to(root)}")
                    continue
                scopes.append(ScanScope(f"child:{child.name}", "protected_child", child, child, child.name))
        return scopes

    def _scan_scope(
        self,
        scope: ScanScope,
        selected_root: Path,
        settings: TaskSettings,
        output_roots: tuple[Path, ...],
        warnings: list[str],
    ) -> Iterable[ScannedFile]:
        recursive = scope.kind in {"whole_tree", "protected_child"}
        for current, dirnames, filenames in os.walk(scope.source_root, topdown=True, followlinks=False):
            current_path = Path(current)
            if scope.kind == "root_loose" and current_path != selected_root:
                dirnames[:] = []
                continue
            if not recursive:
                dirnames[:] = []
            kept_dirs: list[str] = []
            for dirname in dirnames:
                candidate = current_path / dirname
                reason = self._excluded_directory(candidate, settings, output_roots)
                if reason:
                    warnings.append(f"{reason}:{candidate.relative_to(selected_root)}")
                else:
                    kept_dirs.append(dirname)
            dirnames[:] = kept_dirs
            for filename in filenames:
                candidate = current_path / filename
                excluded = self._excluded_file(candidate, settings, output_roots)
                try:
                    info = candidate.stat()
                except OSError:
                    continue
                relative = str(candidate.relative_to(scope.source_root))
                modality = detect_modality(candidate)
                if settings.extension_allowlist and candidate.suffix.lower() not in settings.extension_allowlist:
                    excluded = excluded or "EXTENSION_NOT_ALLOWED"
                if modality not in settings.allowed_modalities:
                    excluded = excluded or "UNSUPPORTED_FORMAT"
                yield ScannedFile(
                    scope_id=scope.scope_id,
                    path=candidate,
                    relative_path=relative,
                    modality=modality,
                    size_bytes=info.st_size,
                    mtime_ns=info.st_mtime_ns,
                    scan_status="excluded" if excluded else "eligible",
                    exclusion_code=excluded,
                )

    def _excluded_directory(self, path: Path, settings: TaskSettings, output_roots: tuple[Path, ...]) -> str | None:
        if _is_reparse(path):
            return "REPARSE_POINT_BLOCKED"
        if any(_inside(path, output_root) for output_root in output_roots):
            return "OUTPUT_EXCLUDED"
        if path.name.casefold() in SYSTEM_NAMES:
            return "SYSTEM_DIRECTORY"
        if not settings.include_hidden and _is_hidden(path):
            return "HIDDEN_EXCLUDED"
        if settings.skip_project_directories and _project_directory(path):
            return "PROJECT_DIRECTORY"
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in settings.exclusions):
            return "USER_EXCLUSION"
        return None

    def _excluded_file(self, path: Path, settings: TaskSettings, output_roots: tuple[Path, ...]) -> str | None:
        if _is_reparse(path):
            return "REPARSE_POINT_BLOCKED"
        if any(_inside(path, output_root) for output_root in output_roots):
            return "OUTPUT_EXCLUDED"
        if not settings.include_hidden and _is_hidden(path):
            return "HIDDEN_EXCLUDED"
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in settings.exclusions):
            return "USER_EXCLUSION"
        return None
