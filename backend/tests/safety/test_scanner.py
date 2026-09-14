from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from guixu.domain.settings import TaskSettings
from guixu.infrastructure.filesystem.scanner import Scanner


def write_fixture(root: Path, relative: str, content: bytes = b"sample") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def manifest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    write_fixture(tmp_path, "root.txt")
    write_fixture(tmp_path, "学习/网络/a.pdf")
    write_fixture(tmp_path, "工作/b.docx")
    write_fixture(tmp_path, "unsupported.exe")
    return tmp_path


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("current_only", {"root.txt", "unsupported.exe"}),
        ("recursive", {"root.txt", "unsupported.exe", "学习/网络/a.pdf", "工作/b.docx"}),
        ("preserve_top_level", {"root.txt", "unsupported.exe", "网络/a.pdf", "b.docx"}),
    ],
)
def test_fs01_three_scan_modes(sample_tree: Path, mode: str, expected: set[str]):
    result = Scanner().scan(sample_tree, TaskSettings(scan_mode=mode, operation_mode="report_only"))
    assert {item.relative_path.replace("\\", "/") for item in result.files} == expected


def test_fs02_preserve_top_level_creates_separate_protected_scopes(sample_tree: Path):
    result = Scanner().scan(sample_tree, TaskSettings(scan_mode="preserve_top_level", operation_mode="report_only"))
    scopes = {scope.display_name: scope.kind for scope in result.scopes}
    assert scopes == {"根目录文件": "root_loose", "学习": "protected_child", "工作": "protected_child"}
    file_scopes = {item.path.name: item.scope_id for item in result.files}
    assert file_scopes["a.pdf"] != file_scopes["b.docx"]


def test_fs03_root_loose_does_not_enter_child_scopes(sample_tree: Path):
    result = Scanner().scan(sample_tree, TaskSettings(scan_mode="preserve_top_level", operation_mode="report_only"))
    loose = [item.path.name for item in result.files if item.scope_id == "root-loose"]
    assert loose == ["root.txt", "unsupported.exe"]


def test_fs04_depth_validation_is_relative_setting():
    for depth in (1, 2, 3):
        assert TaskSettings(max_depth=depth).max_depth == depth
    with pytest.raises(Exception):
        TaskSettings(max_depth=4)


def test_fs05_output_tree_is_excluded(tmp_path: Path):
    write_fixture(tmp_path, "source.txt")
    output = tmp_path / "归档结果"
    write_fixture(output, "nested.txt")
    result = Scanner().scan(tmp_path, TaskSettings(scan_mode="recursive", operation_mode="report_only"), output)
    assert [item.path.name for item in result.files] == ["source.txt"]
    assert any(warning.startswith("OUTPUT_EXCLUDED") for warning in result.warnings)


def test_fs05_previously_recorded_output_tree_is_excluded(tmp_path: Path):
    write_fixture(tmp_path, "source.txt")
    previous_output = tmp_path / "上次归档"
    write_fixture(previous_output, "nested.txt")
    result = Scanner().scan(
        tmp_path,
        TaskSettings(scan_mode="recursive", operation_mode="report_only"),
        excluded_roots=(previous_output,),
    )
    assert [item.path.name for item in result.files] == ["source.txt"]
    assert any(warning.startswith("OUTPUT_EXCLUDED") for warning in result.warnings)


def test_fs06_unicode_case_and_reserved_like_names(tmp_path: Path):
    write_fixture(tmp_path, "中文资料.TXT")
    write_fixture(tmp_path, "name_with_CON_token.md")
    result = Scanner().scan(tmp_path, TaskSettings(scan_mode="current_only", operation_mode="report_only"))
    assert {item.path.name for item in result.files} == {"中文资料.TXT", "name_with_CON_token.md"}
    assert {item.modality for item in result.files} == {"text"}


def test_fs07_symlink_or_reparse_is_not_followed(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    write_fixture(outside, "private.txt")
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("symlink creation is unavailable")
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True,
            check=False,
        )
        if created.returncode != 0:
            pytest.skip("symlink and junction creation are unavailable in this Windows session")
    result = Scanner().scan(tmp_path, TaskSettings(scan_mode="recursive", operation_mode="report_only"))
    assert not any(item.path.name == "private.txt" for item in result.files)
    assert any("REPARSE_POINT_BLOCKED" in warning for warning in result.warnings)


def test_fs08_project_directories_are_skipped(tmp_path: Path):
    write_fixture(tmp_path, "ordinary.txt")
    write_fixture(tmp_path, "project/package.json")
    write_fixture(tmp_path, "project/assets/image.png")
    result = Scanner().scan(tmp_path, TaskSettings(scan_mode="recursive", operation_mode="report_only"))
    assert [item.path.name for item in result.files] == ["ordinary.txt"]
    assert any(warning.startswith("PROJECT_DIRECTORY") for warning in result.warnings)


def test_op01_report_only_does_not_change_disk(sample_tree: Path):
    before = manifest(sample_tree)
    Scanner().scan(sample_tree, TaskSettings(scan_mode="recursive", operation_mode="report_only"))
    assert manifest(sample_tree) == before
    assert not any(path.is_dir() and path.name.startswith("归序") for path in sample_tree.iterdir())


def test_fs14_unique_companion_pairs_are_grouped_and_ambiguous_pairs_are_not(tmp_path: Path):
    write_fixture(tmp_path, "video/trip.mp4")
    write_fixture(tmp_path, "video/trip.srt")
    write_fixture(tmp_path, "audio/lesson.mp3")
    write_fixture(tmp_path, "audio/lesson.lrc")
    write_fixture(tmp_path, "images/photo.jpg")
    write_fixture(tmp_path, "images/photo.xmp")
    write_fixture(tmp_path, "ambiguous/clip.mp4")
    write_fixture(tmp_path, "ambiguous/clip.srt")
    write_fixture(tmp_path, "ambiguous/clip.ass")
    result = Scanner().scan(tmp_path, TaskSettings(scan_mode="recursive", operation_mode="report_only"))
    grouped = {item.path.name: item.companion_group_id for item in result.files}
    assert grouped["trip.mp4"] == grouped["trip.srt"] and grouped["trip.mp4"]
    assert grouped["lesson.mp3"] == grouped["lesson.lrc"] and grouped["lesson.mp3"]
    assert grouped["photo.jpg"] == grouped["photo.xmp"] and grouped["photo.jpg"]
    assert grouped["clip.mp4"] is None and grouped["clip.srt"] is None and grouped["clip.ass"] is None
    assert any(warning.startswith("COMPANION_AMBIGUOUS") for warning in result.warnings)
