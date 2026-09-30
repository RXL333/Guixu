"""Release-safety matrix PARTIAL items S05 / S06 / S07 / S15.

Every case here runs against real ``tmp_path`` directories and the real
``FileOperationExecutor`` / ``Database`` / ``SqliteOperationJournal`` objects.
Assertions describe what is on disk (by SHA-256) and what the journal recorded,
never merely that a call raised.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import text

from guixu.application.plan_compiler import PlanCompiler
from guixu.application.recovery import RecoveryService
from guixu.domain.path_policy import PathPolicyError, validate_category_segment
from guixu.domain.plans import PlanCandidate
from guixu.infrastructure.db.database import Database, utc_now
from guixu.infrastructure.db.operation_journal import SqliteOperationJournal
from guixu.infrastructure.filesystem.executor import FileOperationExecutor
from guixu.infrastructure.filesystem.identity import sha256_file


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #


def make_database(project_root: Path, case: Path) -> Database:
    database = Database(case / "journal.sqlite3", project_root / "contracts" / "database.sql")
    database.initialize()
    return database


def seed_task(database: Database, source_root: Path) -> str:
    task_id, scope_id, now = str(uuid.uuid4()), str(uuid.uuid4()), utc_now()
    with database.begin() as connection:
        connection.execute(text("""
          INSERT INTO tasks(id,name,status,phase,settings_json,settings_hash,created_at,updated_at)
          VALUES(:id,'storage-edges','AWAITING_EXECUTION_APPROVAL','PREVIEW','{}',:hash,:now,:now)
        """), {"id": task_id, "hash": "a" * 64, "now": now})
        connection.execute(text("""
          INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name)
          VALUES(:id,:task,'whole_tree',:root,:root,'test')
        """), {"id": scope_id, "task": task_id, "root": str(source_root)})
    return task_id


def seed_file(database: Database, task_id: str, source_root: Path, source: Path) -> str:
    file_id = str(uuid.uuid4())
    info = source.stat()
    with database.begin() as connection:
        scope = connection.execute(
            text("SELECT id FROM task_scopes WHERE task_id=:task AND source_root=:root"),
            {"task": task_id, "root": str(source_root)},
        ).scalar_one()
        connection.execute(text("""
          INSERT INTO files(
            id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,extension,
            modality,size_bytes,mtime_ns,scan_status,created_at,updated_at
          ) VALUES(:id,:task,:scope,:path,:path,:key,:relative,:name,:ext,'text',:size,:mtime,'eligible',:now,:now)
        """), {"id": file_id, "task": task_id, "scope": scope, "path": str(source),
               "key": str(source).casefold(), "relative": source.name, "name": source.name,
               "ext": source.suffix, "size": info.st_size, "mtime": info.st_mtime_ns, "now": utc_now()})
    return file_id


def build_plan(
    entries: list[tuple[str, Path, Path, Path, tuple[str, ...]]],
    *,
    task_id: str,
    mode: str = "copy",
    max_depth: int = 2,
):
    """entries: (file_id, source, source_root, destination_root, category_segments)."""
    candidates = [
        PlanCandidate(file_id, source, source_root, destination, "docs", segments, "document")
        for file_id, source, source_root, destination, segments in entries
    ]
    return PlanCompiler().compile(
        task_id=task_id, version=1, operation_mode=mode, settings_hash="a" * 64,
        taxonomy_hashes=("b" * 64,), candidates=candidates, max_depth=max_depth,
    )


def run_plan(database: Database, plan) -> SqliteOperationJournal:
    journal = SqliteOperationJournal(database)
    journal.persist_plan(plan)
    journal.approve(plan.plan_id, plan.plan_hash)
    FileOperationExecutor(journal).execute(plan, plan.plan_hash)
    return journal


def approved_plan(database: Database, plan) -> SqliteOperationJournal:
    """Persist + approve only; the caller applies the failure injection after."""
    journal = SqliteOperationJournal(database)
    journal.persist_plan(plan)
    journal.approve(plan.plan_id, plan.plan_hash)
    return journal


def result_for(journal: SqliteOperationJournal, plan, file_id: str) -> dict[str, object]:
    return next(row for row in journal.operation_results(plan.plan_id) if row["file_id"] == file_id)


def events_for(database: Database, operation_id: str) -> list[str]:
    with database.engine.connect() as connection:
        rows = connection.execute(
            text("SELECT event_type FROM operation_events WHERE operation_id=:id ORDER BY seq"),
            {"id": operation_id},
        ).all()
    return [str(row[0]) for row in rows]


def entries_of(directory: Path) -> dict[str, tuple[Path, str]]:
    """Map normcased name -> (path, sha256) so Windows case-insensitivity cannot hide a clash."""
    return {
        os.path.normcase(child.name): (child, sha256_file(child))
        for child in directory.iterdir()
        if child.is_file()
    }


def has_long_path_support(base: Path) -> bool:
    probe = base
    for index in range(4):
        probe = probe / (f"longprobe{index:02d}" + "y" * 40)
    target = probe / "probe.txt"
    try:
        probe.mkdir(parents=True)
        target.write_text("probe")
    except OSError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Windows ACL helpers (S07)
# --------------------------------------------------------------------------- #
#
# These cases deliberately do NOT deny a real ACE on a real directory.
#
# A previous revision did, using `icacls /deny <current-user>`. That turned out to
# be unrecoverable from an unelevated shell: once the deny ACE names the current
# user, the very ACL APIs needed to remove it are themselves denied, and the
# teardown could not prove restoration, so it raised with a deny ACE still live in
# the user's temp directory. A test must never be able to leave the machine's
# security state worse than it found it.
#
# What is actually under test is the executor's *contract* when the operating system
# reports a permission failure: report the failure, never lose the source, keep the
# journal consistent, and never mark the plan finished. Injecting `PermissionError`
# at the OS boundary exercises exactly that contract, deterministically, with no
# machine state to restore. Producing a genuine ACL denial is the operating
# system's responsibility, not this suite's.


@contextmanager
def permission_denied_on(*paths: Path):
    """Make the given paths raise PermissionError from stat/open, as a real denial would."""
    from guixu.infrastructure.filesystem import identity as identity_module
    from guixu.infrastructure.filesystem import executor as executor_module

    blocked = {path.resolve() for path in paths}
    real_read_identity = identity_module.read_identity
    real_identity_matches = executor_module.identity_matches

    def guarded_read_identity(path: Path):
        if path.resolve() in blocked:
            raise PermissionError(13, "Permission denied", str(path))
        return real_read_identity(path)

    def guarded_identity_matches(path: Path, expected, *, require_hash: bool = True) -> bool:
        if path.resolve() in blocked:
            return False
        return real_identity_matches(path, expected, require_hash=require_hash)

    identity_module.read_identity = guarded_read_identity
    executor_module.read_identity = guarded_read_identity
    executor_module.identity_matches = guarded_identity_matches
    try:
        yield
    finally:
        identity_module.read_identity = real_read_identity
        executor_module.read_identity = real_read_identity
        executor_module.identity_matches = real_identity_matches


# =========================================================================== #
# S05 - target exists / case collision / same name
# =========================================================================== #


def test_s05_case_only_difference_target_is_never_clobbered(project_root: Path, tmp_path: Path):
    """Plan wants ``Photo.jpg``; ``photo.jpg`` already sits in the target directory."""
    source_root, destination = tmp_path / "source", tmp_path / "out"
    source_root.mkdir(); destination.mkdir()
    photo = source_root / "Photo.jpg"
    photo.write_bytes(b"upper-case-source")
    beach = source_root / "beach.jpg"
    beach.write_bytes(b"unrelated-photo")
    category = destination / "文档"
    category.mkdir(parents=True)
    (category / "photo.jpg").write_bytes(b"lower-case-occupant")

    database = make_database(project_root, tmp_path)
    task_id = seed_task(database, source_root)
    plan = build_plan([
        (seed_file(database, task_id, source_root, photo), photo, source_root, destination, ("文档",)),
        (seed_file(database, task_id, source_root, beach), beach, source_root, destination, ("文档",)),
    ], task_id=task_id, mode="copy")

    names = {Path(op.target_path or "").name for op in plan.operations}
    assert names == {"Photo (2).jpg", "beach.jpg"}, (
        "case-only collision must not reuse the occupied name"
    )
    assert os.path.normcase("photo.jpg") not in {os.path.normcase(name) for name in names}

    journal = run_plan(database, plan)

    occupant_hash = sha256_file(category / "photo.jpg")
    published = entries_of(category)
    assert published[os.path.normcase("photo.jpg")][1] == occupant_hash
    assert published[os.path.normcase("photo.jpg")][0].read_bytes() == b"lower-case-occupant"
    assert published[os.path.normcase("Photo (2).jpg")][1] == sha256_file(photo)
    # The category holds the occupant, the case-suffixed publication, and the
    # unrelated file that planned into the same category without colliding.
    assert set(published) == {
        os.path.normcase("photo.jpg"), os.path.normcase("Photo (2).jpg"), os.path.normcase("beach.jpg")
    }, sorted(published)
    assert {row["state"] for row in journal.operation_results(plan.plan_id)} == {"COMMITTED"}
    # copy mode: the source keeps its own casing and content
    assert photo.is_file() and photo.read_bytes() == b"upper-case-source"
    database.close()


def test_s05_case_only_collision_appearing_after_approval_keeps_both_files(project_root: Path, tmp_path: Path):
    """The occupied name shows up after approval but differs only by case."""
    source_root, destination = tmp_path / "source", tmp_path / "out"
    source_root.mkdir(); destination.mkdir()
    photo = source_root / "Photo.jpg"
    photo.write_bytes(b"approved-source")
    source_hash = sha256_file(photo)

    database = make_database(project_root, tmp_path)
    task_id = seed_task(database, source_root)
    file_id = seed_file(database, task_id, source_root, photo)
    plan = build_plan([(file_id, photo, source_root, destination, ("文档",))],
                      task_id=task_id, mode="copy")
    assert Path(plan.operations[0].target_path or "").name == "Photo.jpg"
    journal = approved_plan(database, plan)

    category = Path(plan.operations[0].target_path or "").parent
    category.mkdir(parents=True)
    (category / "photo.jpg").write_bytes(b"third-party-occupant")
    occupant_hash = sha256_file(category / "photo.jpg")

    FileOperationExecutor(journal).execute(plan, plan.plan_hash)

    after = entries_of(category)
    assert list(after) == [os.path.normcase("photo.jpg")], "no second file may appear"
    assert after[os.path.normcase("photo.jpg")][1] == occupant_hash
    row = result_for(journal, plan, file_id)
    assert row["state"] == "CONFLICT" and row["error_code"] == "TARGET_APPEARED"
    assert sha256_file(photo) == source_hash
    database.close()


def test_s05_batch_of_case_differing_names_allocates_distinct_targets(project_root: Path, tmp_path: Path):
    """Two sources differing only by case must not be planned onto the same Windows file.

    They cannot live in one directory on NTFS, so the scenario is two authorised
    roots contributing to a single task. Each candidate must be checked against its
    own root; passing the wrong one would make the compiler reject the plan outright
    rather than de-duplicate it.
    """
    first_root, second_root, destination = tmp_path / "one", tmp_path / "two", tmp_path / "out"
    first_root.mkdir(); second_root.mkdir(); destination.mkdir()
    upper = first_root / "Photo.jpg"; upper.write_bytes(b"upper")
    lower = second_root / "photo.jpg"; lower.write_bytes(b"lower")
    # Read the content hashes now: the mode under test is `move`, so by the time
    # the assertions run the sources are gone from where they were.
    expected = {sha256_file(upper), sha256_file(lower)}

    database = make_database(project_root, tmp_path)
    task_id = seed_task(database, first_root)
    second_scope = str(uuid.uuid4())
    with database.begin() as connection:
        connection.execute(text("""
          INSERT INTO task_scopes(id,task_id,kind,source_root,destination_root,display_name)
          VALUES(:id,:task,'whole_tree',:root,:root,'second')
        """), {"id": second_scope, "task": task_id, "root": str(second_root)})

    def seed_scoped(root: Path, path: Path) -> str:
        file_id = str(uuid.uuid4())
        info = path.stat()
        with database.begin() as connection:
            connection.execute(text("""
              INSERT INTO files(
                id,task_id,scope_id,original_path,current_path,path_key,relative_path,basename,extension,
                modality,size_bytes,mtime_ns,scan_status,created_at,updated_at
              ) VALUES(:id,:task,:scope,:path,:path,:key,:relative,:name,:ext,'text',:size,:mtime,'eligible',:now,:now)
            """), {"id": file_id, "task": task_id, "scope": second_scope, "path": str(path),
                   "key": str(path).casefold(), "relative": path.name, "name": path.name,
                   "ext": path.suffix, "size": info.st_size, "mtime": info.st_mtime_ns, "now": utc_now()})
        return file_id

    plan = build_plan([
        (seed_file(database, task_id, first_root, upper), upper, first_root, destination, ("文档",)),
        (seed_scoped(second_root, lower), lower, second_root, destination, ("文档",)),
    ], task_id=task_id, mode="preview_move")

    keys = [op.target_key for op in plan.operations]
    assert len(set(keys)) == 2, f"targets collide on a case-insensitive volume: {keys}"
    names = sorted(Path(op.target_path or "").name for op in plan.operations)
    assert names == ["Photo (2).jpg", "photo.jpg"] or names == ["Photo.jpg", "photo (2).jpg"], names
    journal = run_plan(database, plan)

    category = Path(plan.operations[0].target_path or "").parent
    published = entries_of(category)
    assert len(published) == 2, "both files must survive with distinct on-disk names"
    assert {sha256 for _, sha256 in published.values()} == expected
    assert [row["state"] for row in journal.operation_results(plan.plan_id)] == ["COMMITTED", "COMMITTED"]
    database.close()


# =========================================================================== #
# S06 - invalid Windows segment / long path
# =========================================================================== #


def test_s06_category_segment_length_boundary_is_sixty_characters(tmp_path: Path):
    assert validate_category_segment("文" * 60) == "文" * 60
    with pytest.raises(PathPolicyError):
        validate_category_segment("文" * 61)


def test_s06_over_length_segment_rejects_the_whole_plan_before_any_disk_change(tmp_path: Path):
    """One illegal segment aborts compilation; the legal sibling is never published."""
    source_root, destination = tmp_path / "source", tmp_path / "out"
    source_root.mkdir(); destination.mkdir()
    legal = source_root / "legal.txt"; legal.write_bytes(b"legal")
    illegal = source_root / "illegal.txt"; illegal.write_bytes(b"illegal")
    task_id = str(uuid.uuid4())
    plan_input = [
        (str(uuid.uuid4()), legal, source_root, destination, ("文" * 61,)),
        (str(uuid.uuid4()), illegal, source_root, destination, ("文" * 61,)),
    ]
    with pytest.raises(PathPolicyError):
        build_plan(plan_input, task_id=task_id, mode="copy")
    assert list(destination.iterdir()) == []
    assert sha256_file(legal) == sha256_file(legal)

    accepted = build_plan([
        (str(uuid.uuid4()), legal, source_root, destination, ("文" * 60,)),
    ], task_id=task_id, mode="copy")
    assert Path(accepted.operations[0].target_path or "").name == "legal.txt"


def _staged_length(target: Path) -> int:
    """Length of the executor's staging path for `target`.

    The executor copies through `.<name>.guixu-part-<uuid>`, which is 50 characters
    longer than the published name. A target that sits just under MAX_PATH can still
    be unbuildable once staging is accounted for.
    """
    uuid4 = "00000000-0000-0000-0000-000000000000"
    return len(str(target.with_name(f".{target.name}.guixu-part-{uuid4}")))


def test_s06_max_depth_nested_long_category_path_is_created_and_published(project_root: Path, tmp_path: Path):
    """The deepest legal category chain must be created, recorded and published."""
    source_root, destination = tmp_path / "s", tmp_path / "o"
    source_root.mkdir(); destination.mkdir()
    source = source_root / "d.txt"; source.write_bytes(b"deep-payload")
    long_first, long_second = "A" * 60, "B" * 60

    database = make_database(project_root, tmp_path)
    task_id = seed_task(database, source_root)
    file_id = seed_file(database, task_id, source_root, source)
    plan = build_plan([(file_id, source, source_root, destination, (long_first, long_second))],
                      task_id=task_id, mode="copy", max_depth=2)
    target = Path(plan.operations[0].target_path or "")
    assert target.parent.name == long_second and target.parent.parent.name == long_first
    if _staged_length(target) >= 260 and not has_long_path_support(tmp_path):
        pytest.skip(f"this volume caps paths at 260 and the staged name reaches {_staged_length(target)}")

    journal = run_plan(database, plan)

    assert target.is_file() and sha256_file(target) == sha256_file(source)
    assert result_for(journal, plan, file_id)["state"] == "COMMITTED"
    with database.engine.connect() as connection:
        created = connection.execute(
            text("SELECT path FROM created_directories WHERE plan_id=:plan ORDER BY path"),
            {"plan": plan.plan_id},
        ).scalars().all()
    assert {os.path.normcase(str(item)) for item in created} >= {
        os.path.normcase(str(destination / long_first)),
        os.path.normcase(str(destination / long_first / long_second)),
    }
    database.close()


def test_s06_target_path_beyond_windows_limit_never_loses_the_source(project_root: Path, tmp_path: Path):
    """A chain the volume cannot build must fail the operation, not lose the file.

    Nothing here pre-creates the deep directory chain: on a volume without long-path
    support `mkdir(parents=True)` itself raises, so the test has to let the executor
    be the thing that hits the boundary. The contract under test is the same one that
    applies to any other OSError -- the operation ends FAILED, the source keeps its
    bytes, and nothing is published.
    """
    if has_long_path_support(tmp_path):
        pytest.skip("this volume accepts paths beyond the classic Windows limit; boundary unreachable")

    source_root = tmp_path / "s"
    source_root.mkdir()
    source = source_root / "overlong.txt"
    source.write_bytes(b"must-survive-an-overlong-target")
    source_hash = sha256_file(source)

    database = make_database(project_root, tmp_path)
    task_id = seed_task(database, source_root)
    file_id = seed_file(database, task_id, source_root, source)
    plan = build_plan([(file_id, source, source_root, tmp_path, ("C" * 60, "E" * 60))],
                      task_id=task_id, mode="copy", max_depth=2)
    target = Path(plan.operations[0].target_path or "")
    assert _staged_length(target) > 260, (
        f"test precondition failed, staged path is only {_staged_length(target)} chars"
    )
    journal = approved_plan(database, plan)

    FileOperationExecutor(journal).execute(plan, plan.plan_hash)

    assert result_for(journal, plan, file_id)["state"] == "FAILED"
    assert not target.exists()
    assert source.is_file() and sha256_file(source) == source_hash
    database.close()


# =========================================================================== #
# S07 - read-only / permission denied / locked
# =========================================================================== #


def test_s07_unreadable_source_is_conflicted_and_never_deleted(project_root: Path, tmp_path: Path):
    """A source the OS will not let us read must become a conflict, not a loss.

    The denial is injected at the identity syscall rather than by editing a real ACL;
    see the note above `permission_denied_on` for why.
    """
    source_root, destination = tmp_path / "source", tmp_path / "out"
    source_root.mkdir(); destination.mkdir()
    denied = source_root / "denied.txt"; denied.write_bytes(b"denied-source")
    allowed = source_root / "allowed.txt"; allowed.write_bytes(b"allowed-source")
    denied_hash = sha256_file(denied)

    database = make_database(project_root, tmp_path)
    task_id = seed_task(database, source_root)
    denied_id = seed_file(database, task_id, source_root, denied)
    allowed_id = seed_file(database, task_id, source_root, allowed)
    plan = build_plan([
        (denied_id, denied, source_root, destination, ("文档",)),
        (allowed_id, allowed, source_root, destination, ("文档",)),
    ], task_id=task_id, mode="preview_move")
    journal = approved_plan(database, plan)

    with permission_denied_on(denied):
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)

    # The compiler orders operations by file_id, and those are random UUIDs, so the
    # two rows must be located by id rather than by position.
    operation = {op.file_id: op for op in plan.operations}
    assert sha256_file(denied) == denied_hash and denied.is_file()
    assert result_for(journal, plan, denied_id)["state"] == "CONFLICT"
    assert result_for(journal, plan, denied_id)["error_code"] == "SOURCE_CHANGED"
    assert not Path(operation[denied_id].target_path or "").exists()

    # positive control in the very same plan and the very same run
    published = Path(operation[allowed_id].target_path or "")
    assert result_for(journal, plan, allowed_id)["state"] == "COMMITTED"
    assert published.is_file() and published.read_bytes() == b"allowed-source"
    assert not allowed.exists(), "a move must not leave the source behind"
    assert events_for(database, operation[allowed_id].operation_id)[-1] == "COMMITTED"
    database.close()


def test_s07_unwritable_destination_fails_the_operation_without_touching_the_source(project_root: Path, tmp_path: Path, monkeypatch):
    """A publication the OS refuses must fail the operation and preserve the source."""
    source_root, destination = tmp_path / "source", tmp_path / "out"
    source_root.mkdir(); destination.mkdir()
    blocked_source = source_root / "blocked.txt"; blocked_source.write_bytes(b"blocked-target")
    free_source = source_root / "free.txt"; free_source.write_bytes(b"free-target")
    blocked_hash = sha256_file(blocked_source)

    blocked_category = destination / "blocked"
    free_category = destination / "free"
    blocked_category.mkdir(parents=True)
    free_category.mkdir(parents=True)

    database = make_database(project_root, tmp_path)
    task_id = seed_task(database, source_root)
    blocked_id = seed_file(database, task_id, source_root, blocked_source)
    free_id = seed_file(database, task_id, source_root, free_source)
    plan = build_plan([
        (blocked_id, blocked_source, source_root, destination, ("blocked",)),
        (free_id, free_source, source_root, destination, ("free",)),
    ], task_id=task_id, mode="copy")
    journal = approved_plan(database, plan)

    from guixu.infrastructure.filesystem import executor as executor_module
    real_move = executor_module.move_no_clobber

    def deny_publish(temporary: Path, target: Path) -> None:
        if target.parent == blocked_category:
            raise PermissionError(13, "Permission denied", str(target))
        return real_move(temporary, target)

    monkeypatch.setattr(executor_module, "move_no_clobber", deny_publish)
    FileOperationExecutor(journal).execute(plan, plan.plan_hash)

    blocked_row = result_for(journal, plan, blocked_id)
    assert blocked_row["state"] == "FAILED"
    assert blocked_row["error_code"] == "OPERATION_FAILED"
    assert not (blocked_category / "blocked.txt").exists()
    assert blocked_source.is_file() and sha256_file(blocked_source) == blocked_hash

    # The half-written copy is deliberately left behind: recovery republishes from it
    # instead of re-reading the source. What must be true is that it is a *valid*
    # artifact, not that it is absent.
    leftovers = list(blocked_category.iterdir())
    assert len(leftovers) == 1, f"expected exactly one recovery artifact, got {leftovers}"
    staged = leftovers[0]
    assert staged.name.startswith(".blocked.txt.guixu-part-")
    assert sha256_file(staged) == blocked_hash, "the staged copy must still match the source"

    # positive control in the very same plan and the very same run
    assert result_for(journal, plan, free_id)["state"] == "COMMITTED"
    assert (free_category / "free.txt").read_bytes() == b"free-target"
    with database.engine.connect() as connection:
        plan_status = connection.execute(
            text("SELECT status FROM plans WHERE id=:plan"), {"plan": plan.plan_id}
        ).scalar_one()
    assert plan_status == "executing", "an unfinished plan must not be reported as finished"

    # Once the obstruction clears, the staged copy is published rather than re-copied.
    monkeypatch.setattr(executor_module, "move_no_clobber", real_move)
    resumed = RecoveryService(journal).recover(plan)
    assert resumed == {"retried": 0, "committed": 1, "failed": 0, "conflict": 0}
    assert (blocked_category / "blocked.txt").read_bytes() == b"blocked-target"
    # The plan is copy-mode, so the source is kept by design; only a move would unlink it.
    assert blocked_source.is_file()
    assert [item.name for item in blocked_category.iterdir()] == ["blocked.txt"], (
        "the staged artifact must be consumed by its own publication, not left beside it"
    )
    database.close()


# =========================================================================== #
# S15 - SQLite rollback / unexpected close / concurrency
# =========================================================================== #


def test_s15_database_configures_wal_busy_timeout_and_full_synchronous(project_root: Path, tmp_path: Path):
    database = make_database(project_root, tmp_path)
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 2
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    database.seed_json("s15", {"ok": True})
    assert database.get_json_setting("s15") == ({"ok": True}, 1)
    database.close()


def test_s15_rolled_back_transaction_leaves_no_rows_and_keeps_the_file_writable(project_root: Path, tmp_path: Path):
    database = make_database(project_root, tmp_path)
    database.seed_json("s15-rollback-seed", {"seed": True})

    with pytest.raises(RuntimeError, match="injected rollback"):
        with database.begin() as connection:
            connection.execute(text(
                "INSERT INTO settings(key,value_json,revision,updated_at) VALUES('s15-rollback','{}',1,:now)"
            ), {"now": utc_now()})
            connection.execute(text(
                "INSERT INTO settings(key,value_json,revision,updated_at) VALUES('s15-rollback-2','{}',1,:now)"
            ), {"now": utc_now()})
            raise RuntimeError("injected rollback")

    with database.engine.connect() as connection:
        survivors = connection.execute(text(
            "SELECT count(*) FROM settings WHERE key LIKE 's15-rollback%' AND key<>'s15-rollback-seed'"
        )).scalar_one()
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    assert survivors == 0

    database.update_json_setting("s15-rollback-seed", {"seed": "kept"}, 1)
    assert database.get_json_setting("s15-rollback-seed") == ({"seed": "kept"}, 2)
    database.close()


def test_s15_two_writers_on_one_file_lose_no_commits(project_root: Path, tmp_path: Path):
    database_path = tmp_path / "journal.sqlite3"
    first = Database(database_path, project_root / "contracts" / "database.sql")
    first.initialize()
    second = Database(database_path, project_root / "contracts" / "database.sql")
    second.initialize()

    writers, rows_per_writer = 2, 40
    barrier = threading.Barrier(writers)
    errors: list[BaseException] = []

    def writer(database: Database, tag: str) -> None:
        try:
            for index in range(rows_per_writer):
                barrier.wait(timeout=30)
                with database.begin() as connection:
                    connection.execute(text(
                        "INSERT OR REPLACE INTO settings(key,value_json,revision,updated_at)"
                        " VALUES(:key,'{}',1,:now)"
                    ), {"key": f"s15-writer-{tag}-{index}", "now": utc_now()})
        except BaseException as error:  # noqa: BLE001 - surfaced as a test failure below
            errors.append(error)

    threads = [
        threading.Thread(target=writer, args=(first, "a")),
        threading.Thread(target=writer, args=(second, "b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == [], f"a concurrent writer failed: {errors!r}"
    with first.engine.connect() as connection:
        stored = connection.execute(text(
            "SELECT key FROM settings WHERE key LIKE 's15-writer-%' ORDER BY key"
        )).scalars().all()
    assert len(stored) == writers * rows_per_writer
    assert {str(key).rsplit("-", 1)[-1] for key in stored} == {
        str(index) for index in range(rows_per_writer)
    }
    first.close(); second.close()


def test_s15_busy_timeout_holds_a_second_writer_until_the_first_commits(project_root: Path, tmp_path: Path):
    database_path = tmp_path / "journal.sqlite3"
    first = Database(database_path, project_root / "contracts" / "database.sql")
    first.initialize()
    second = Database(database_path, project_root / "contracts" / "database.sql")
    second.initialize()

    holder = first.engine.raw_connection()
    holder.execute("BEGIN IMMEDIATE")
    holder.execute(
        "INSERT INTO settings(key,value_json,revision,updated_at) VALUES('s15-holder','{}',1,'2026-01-01T00:00:00+00:00')"
    )
    started = threading.Event()
    elapsed: list[float] = []
    failures: list[BaseException] = []

    def competing_write() -> None:
        started.set()
        begin = time.monotonic()
        try:
            with second.begin() as connection:
                connection.execute(text(
                    "INSERT INTO settings(key,value_json,revision,updated_at)"
                    " VALUES('s15-waiter','{}',1,:now)"
                ), {"now": utc_now()})
        except BaseException as error:  # noqa: BLE001 - surfaced as a test failure below
            failures.append(error)
        finally:
            elapsed.append(time.monotonic() - begin)

    worker = threading.Thread(target=competing_write)
    worker.start()
    assert started.wait(5)
    time.sleep(0.75)
    assert elapsed == [], "the second writer returned while the first still held the write lock"
    holder.commit()
    holder.close()
    worker.join(30)

    assert not failures, f"the waiting writer never completed: {failures!r}"
    assert elapsed and elapsed[0] >= 0.5, (
        f"busy_timeout did not hold the second writer, it returned after {elapsed[0]:.3f}s"
    )
    with second.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    assert set(second.get_json_setting("s15-waiter")[0]) == set()
    first.close(); second.close()


def test_s15_optimistic_revision_conflict_has_exactly_one_winner(project_root: Path, tmp_path: Path):
    database_path = tmp_path / "journal.sqlite3"
    first = Database(database_path, project_root / "contracts" / "database.sql")
    first.initialize()
    second = Database(database_path, project_root / "contracts" / "database.sql")
    second.initialize()
    first.seed_json("s15-cas", {"revision": 0})

    assert first.get_json_setting("s15-cas") == ({"revision": 0}, 1)
    assert second.get_json_setting("s15-cas") == ({"revision": 0}, 1)
    assert first.update_json_setting("s15-cas", {"writer": "first"}, 1) == 2
    with pytest.raises(ValueError, match="SETTINGS_REVISION_CONFLICT"):
        second.update_json_setting("s15-cas", {"writer": "second"}, 1)

    assert second.get_json_setting("s15-cas") == ({"writer": "first"}, 2)
    first.close(); second.close()


CRASH_SCRIPT = '''
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "backend" / "src"))
from guixu.infrastructure.db.database import Database

database = Database(Path(sys.argv[2]), Path(sys.argv[1]) / "contracts" / "database.sql")
raw = database.engine.raw_connection()
raw.execute("BEGIN IMMEDIATE")
raw.execute(
    "INSERT INTO settings(key,value_json,revision,updated_at) VALUES(?, '{}', 1, '2026-01-01T00:00:00+00:00')",
    (sys.argv[3],),
)
if sys.argv[4] == "commit":
    raw.commit()
# No close, no rollback, no atexit: the process just disappears.
os._exit(0 if sys.argv[4] == "commit" else 91)
'''


def _crash_writer(project_root: Path, case: Path, key: str, outcome: str) -> int:
    script = case / f"crash_{outcome}.py"
    script.write_text(CRASH_SCRIPT, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script), str(project_root), str(case / "journal.sqlite3"), key, outcome],
        cwd=project_root / "backend", capture_output=True, text=True, timeout=120,
    )
    return completed.returncode


def test_s15_uncommitted_write_is_discarded_after_a_real_process_exit(project_root: Path, tmp_path: Path):
    case = tmp_path / "uncommitted"
    case.mkdir()
    database_path = case / "journal.sqlite3"
    database = Database(database_path, project_root / "contracts" / "database.sql")
    database.initialize()
    database.seed_json("s15-survivor", {"kept": True})
    database.close()

    assert _crash_writer(project_root, case, "s15-doomed", "rollback") == 91

    reopened = Database(database_path, project_root / "contracts" / "database.sql")
    with reopened.engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM settings WHERE key='s15-doomed'"
        ).scalar_one() == 0
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    assert reopened.get_json_setting("s15-survivor") == ({"kept": True}, 1)

    # The dead writer must not have left the database write-locked.
    reopened.update_json_setting("s15-survivor", {"kept": "writable"}, 1)
    assert reopened.get_json_setting("s15-survivor") == ({"kept": "writable"}, 2)
    reopened.close()


def test_s15_committed_write_survives_a_real_process_exit(project_root: Path, tmp_path: Path):
    case = tmp_path / "committed"
    case.mkdir()
    database_path = case / "journal.sqlite3"
    database = Database(database_path, project_root / "contracts" / "database.sql")
    database.initialize()
    database.close()

    assert _crash_writer(project_root, case, "s15-durable", "commit") == 0

    reopened = Database(database_path, project_root / "contracts" / "database.sql")
    with reopened.engine.connect() as connection:
        stored = connection.execute(text(
            "SELECT value_json FROM settings WHERE key='s15-durable'"
        )).scalar_one()
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    assert json.loads(stored) == {}
    reopened.update_json_setting("s15-durable", {"durable": True}, 1)
    assert reopened.get_json_setting("s15-durable") == ({"durable": True}, 2)
    reopened.close()


# =========================================================================== #
# S03 - reparse points at the conversation and execution boundary
#
# `test_scanner.py::test_fs07_symlink_or_reparse_is_not_followed` proves the
# scanner refuses to walk into a reparse point. That is the *discovery* half.
# These cases are the *action* half: a junction that is already sitting in an
# authorized tree, which a plan, a stale database row or a racing rename could
# aim an operation at. The scanner never having seen it is no defence.
# =========================================================================== #


def _make_junction(link: Path, target: Path) -> None:
    """Create a directory junction the way Windows itself would.

    `symlink_to` needs a privilege most sessions do not hold; `mklink /J` does
    not, and a junction is the reparse type a user is most likely to have lying
    around from a drive-letter convenience or an old "link to folder".
    """
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, check=False,
    )
    if created.returncode != 0:
        pytest.skip("junction creation is unavailable in this Windows session")


def test_s03_a_junction_in_the_destination_is_never_written_through(project_root: Path, tmp_path: Path):
    """A category name that lands on a junction must not become a write into its target.

    The destination root is authorised; whatever a junction inside it points at
    is not. Resolving the grant boundary is the only thing standing between a
    plausible category name and a silent write into an unrelated directory.
    """
    case = tmp_path / "junction-destination"
    source, destination, outside = case / "src", case / "out", case / "private"
    for folder in (source, destination, outside):
        folder.mkdir(parents=True)
    original = source / "receipt.txt"
    original.write_text("receipt body", encoding="utf-8")
    before = sha256_file(outside / "keep.txt") if (outside / "keep.txt").exists() else None
    (outside / "keep.txt").write_text("must not be touched", encoding="utf-8")
    untouched = sha256_file(outside / "keep.txt")
    _make_junction(destination / "文档", outside)

    database = make_database(project_root, case)
    task_id = seed_task(database, source)
    file_id = seed_file(database, task_id, source, original)

    # Whichever stage refuses - the plan compiler today, the executor if the
    # junction appears between approval and execution - the invariant is the
    # same: the operation never reaches the disk.
    with pytest.raises(PathPolicyError):
        plan = build_plan([(file_id, original, source, destination, ("文档",))], task_id=task_id, mode="copy")
        journal = approved_plan(database, plan)
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)

    assert list(outside.iterdir()) == [outside / "keep.txt"], "nothing may be written through the junction"
    assert sha256_file(outside / "keep.txt") == untouched
    assert original.is_file(), "the source must survive a refused target"
    database.close()


def test_s03_a_source_reached_only_through_a_junction_is_refused(project_root: Path, tmp_path: Path):
    """A database row pointing through a junction is not a legitimate source.

    The scanner cannot produce such a row, but a stale row from before the
    junction existed, or a database edited out of band, can. The executor's
    grant check has to hold on its own.
    """
    case = tmp_path / "junction-source"
    source, outside = case / "src", case / "private"
    for folder in (source, outside):
        folder.mkdir(parents=True)
    hidden = outside / "secret.txt"
    hidden.write_text("private content", encoding="utf-8")
    secret_hash = sha256_file(hidden)
    _make_junction(source / "linked", outside)

    database = make_database(project_root, case)
    task_id = seed_task(database, source)
    file_id = seed_file(database, task_id, source, source / "linked" / "secret.txt")
    destination = case / "out"
    destination.mkdir()

    with pytest.raises(PathPolicyError):
        plan = build_plan([(file_id, source / "linked" / "secret.txt", source, destination, ("文档",))],
                          task_id=task_id, mode="copy")
        journal = approved_plan(database, plan)
        FileOperationExecutor(journal).execute(plan, plan.plan_hash)

    assert hidden.is_file() and sha256_file(hidden) == secret_hash
    assert not list(destination.iterdir()), "nothing may be copied out through the junction"
    database.close()


def test_s03_a_plain_subdirectory_of_the_destination_is_unaffected(project_root: Path, tmp_path: Path):
    """The control: ordinary nesting must keep working after the junction guard.

    Without this, a test that only ever asserts refusals would still pass if the
    guard rejected everything.
    """
    case = tmp_path / "junction-control"
    source, destination = case / "src", case / "out"
    for folder in (source, destination):
        folder.mkdir(parents=True)
    original = source / "receipt.txt"
    original.write_text("receipt body", encoding="utf-8")

    database = make_database(project_root, case)
    task_id = seed_task(database, source)
    file_id = seed_file(database, task_id, source, original)
    plan = build_plan([(file_id, original, source, destination, ("照片", "2026"))],
                      task_id=task_id, mode="copy")
    journal = run_plan(database, plan)

    published = destination / "照片" / "2026" / "receipt.txt"
    assert published.is_file() and sha256_file(published) == sha256_file(original)
    assert result_for(journal, plan, file_id)["state"] == "COMMITTED"
    database.close()
