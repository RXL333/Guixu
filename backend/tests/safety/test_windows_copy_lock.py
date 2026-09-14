from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from guixu.infrastructure.filesystem.identity import read_identity
from guixu.infrastructure.filesystem.windows_handles import locked_source_chunks


@pytest.mark.skipif(os.name != "nt", reason="Windows share-mode semantics")
def test_locked_copy_reader_denies_concurrent_writer(tmp_path: Path):
    source = tmp_path / "source.bin"; source.write_bytes(b"x" * 262144)
    identity = read_identity(source)
    write_blocked = threading.Event()
    iterator = locked_source_chunks(source, identity, 65536)
    first = next(iterator)
    assert first
    def try_write():
        try:
            source.write_bytes(b"changed")
        except PermissionError:
            write_blocked.set()
    worker = threading.Thread(target=try_write)
    worker.start(); worker.join(timeout=5)
    remaining = b"".join(iterator)
    assert write_blocked.is_set()
    assert len(first) + len(remaining) == identity.size_bytes
