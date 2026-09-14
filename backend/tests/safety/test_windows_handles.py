from __future__ import annotations

import os
from pathlib import Path

import pytest

from guixu.infrastructure.filesystem.identity import read_identity
from guixu.infrastructure.filesystem.windows_handles import rename_source_no_clobber


@pytest.mark.skipif(os.name != "nt", reason="Windows handle rename")
def test_same_volume_rename_uses_verified_handle_and_never_replaces(tmp_path: Path):
    source = tmp_path / "source.txt"; target = tmp_path / "target.txt"
    source.write_text("source")
    identity = read_identity(source)
    rename_source_no_clobber(source, target, identity)
    assert not source.exists() and target.read_text() == "source"
    replacement = tmp_path / "replacement.txt"; replacement.write_text("new")
    replacement_identity = read_identity(replacement)
    with pytest.raises(FileExistsError):
        rename_source_no_clobber(replacement, target, replacement_identity)
    assert replacement.read_text() == "new" and target.read_text() == "source"


@pytest.mark.skipif(os.name != "nt", reason="Windows handle rename")
def test_handle_rename_rejects_stale_identity(tmp_path: Path):
    source = tmp_path / "source.txt"; target = tmp_path / "target.txt"
    source.write_text("before"); identity = read_identity(source); source.write_text("after")
    with pytest.raises(OSError, match="identity changed"):
        rename_source_no_clobber(source, target, identity)
    assert source.read_text() == "after" and not target.exists()
