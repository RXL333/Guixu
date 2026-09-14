from __future__ import annotations

import msvcrt
from pathlib import Path
from typing import BinaryIO


class SingleInstance:
    def __init__(self, lock_path: Path) -> None:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: BinaryIO = lock_path.open("a+b")

    def acquire(self) -> None:
        self._handle.seek(0)
        try:
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self._handle.close()
            raise RuntimeError("Guixu is already running") from exc

    def release(self) -> None:
        try:
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._handle.close()

