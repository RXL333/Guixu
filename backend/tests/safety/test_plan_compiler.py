from __future__ import annotations

import os
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from guixu.application.plan_compiler import PlanCompiler, verify_plan_hash
from guixu.domain.path_policy import PathPolicyError, validate_category_segment
from guixu.domain.plans import PlanCandidate


def candidate(source: Path, destination: Path, file_id: str | None = None, segments=("文档",)) -> PlanCandidate:
    return PlanCandidate(
        file_id=file_id or str(uuid.uuid4()),
        source_path=source,
        source_root=source.parent,
        destination_root=destination,
        category_id="category-documents",
        category_segments=segments,
        modality="document",
    )


def compile_plan(items: list[PlanCandidate], mode="copy"):
    return PlanCompiler().compile(
        task_id=str(uuid.uuid4()), version=1, operation_mode=mode,
        settings_hash="a" * 64, taxonomy_hashes=("b" * 64,), candidates=items, max_depth=2,
    )


@pytest.mark.parametrize("name", ["", ".", "..", "CON", "aux.txt", "尾点.", "尾空格 ", "a/b", "a:b", "x" * 61])
def test_fs06_rejects_invalid_windows_category_names(name: str):
    with pytest.raises(PathPolicyError):
        validate_category_segment(name)


def test_fs09_existing_name_gets_stable_suffix(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "target"
    source.mkdir(); (destination / "文档").mkdir(parents=True)
    original = source / "report.pdf"; original.write_bytes(b"new")
    (destination / "文档" / "report.pdf").write_bytes(b"existing")
    plan = compile_plan([candidate(original, destination)])
    assert Path(plan.operations[0].target_path or "").name == "report (2).pdf"
    assert verify_plan_hash(plan)


def test_fs10_batch_collision_is_deterministic_by_file_id(tmp_path: Path):
    first_root = tmp_path / "one"; second_root = tmp_path / "two"; destination = tmp_path / "out"
    first_root.mkdir(); second_root.mkdir(); destination.mkdir()
    first = first_root / "same.txt"; second = second_root / "same.txt"
    first.write_text("one"); second.write_text("two")
    low = "00000000-0000-0000-0000-000000000001"
    high = "00000000-0000-0000-0000-000000000002"
    plan = compile_plan([candidate(second, destination, high), candidate(first, destination, low)])
    assert [Path(op.target_path or "").name for op in plan.operations] == ["same.txt", "same (2).txt"]


def test_fs12_source_change_invalidates_frozen_hash(tmp_path: Path):
    source = tmp_path / "a.txt"; destination = tmp_path / "out"; destination.mkdir()
    source.write_text("before")
    plan = compile_plan([candidate(source, destination)])
    source.write_text("after")
    assert plan.operations[0].expected_sha256 != __import__("hashlib").sha256(source.read_bytes()).hexdigest()


def test_fs13_unsupported_format_stays_in_place(tmp_path: Path):
    source = tmp_path / "tool.exe"; destination = tmp_path / "out"; destination.mkdir(); source.write_bytes(b"MZ")
    item = replace(candidate(source, destination), modality="other")
    plan = compile_plan([item])
    assert plan.operations[0].action == "skip"
    assert plan.operations[0].target_path is None


def test_plan_hash_detects_any_approved_target_change(tmp_path: Path):
    source = tmp_path / "a.txt"; destination = tmp_path / "out"; destination.mkdir(); source.write_text("data")
    plan = compile_plan([candidate(source, destination)])
    tampered_operation = replace(plan.operations[0], target_path=str(destination / "elsewhere.txt"))
    tampered = replace(plan, operations=(tampered_operation,))
    assert not verify_plan_hash(tampered)


def test_hardlink_is_blocked_when_supported(tmp_path: Path):
    source = tmp_path / "a.txt"; alias = tmp_path / "alias.txt"; destination = tmp_path / "out"
    destination.mkdir(); source.write_text("data")
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("hard links unavailable")
    plan = compile_plan([candidate(source, destination)])
    assert plan.operations[0].action == "skip"
    assert plan.operations[0].reason == "HARDLINK_BLOCKED"


@pytest.mark.skipif(os.name != "nt", reason="NTFS alternate streams are Windows-specific")
def test_fs16_alternate_data_stream_is_blocked(tmp_path: Path):
    source = tmp_path / "a.txt"; destination = tmp_path / "out"; destination.mkdir(); source.write_text("data")
    stream = Path(f"{source}:secret")
    try:
        stream.write_text("hidden")
    except OSError:
        pytest.skip("test volume does not support alternate data streams")
    plan = compile_plan([candidate(source, destination)])
    assert plan.operations[0].action == "skip"
    assert plan.operations[0].reason == "ALTERNATE_DATA_STREAM_BLOCKED"


def test_fs14_companion_group_uses_one_collision_suffix(tmp_path: Path):
    source = tmp_path / "source"; destination = tmp_path / "out"; source.mkdir(); (destination / "视频").mkdir(parents=True)
    video = source / "trip.mp4"; subtitle = source / "trip.srt"; video.write_bytes(b"video"); subtitle.write_text("subtitle")
    (destination / "视频" / "trip.mp4").write_bytes(b"existing")
    group_id = str(uuid.uuid4())
    items = [
        replace(candidate(video, destination, "00000000-0000-0000-0000-000000000001", ("视频",)), modality="video", companion_group_id=group_id),
        replace(candidate(subtitle, destination, "00000000-0000-0000-0000-000000000002", ("视频",)), modality="video", companion_group_id=group_id),
    ]
    plan = compile_plan(items)
    assert [Path(item.target_path or "").name for item in plan.operations] == ["trip (2).mp4", "trip (2).srt"]
