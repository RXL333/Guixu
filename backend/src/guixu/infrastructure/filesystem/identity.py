from __future__ import annotations

import hashlib
import ctypes
import os
from pathlib import Path

from guixu.domain.plans import SourceIdentity


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_identity(path: Path) -> SourceIdentity:
    info = path.stat()
    return SourceIdentity(
        volume_id=str(info.st_dev),
        file_id=str(info.st_ino),
        size_bytes=info.st_size,
        mtime_ns=info.st_mtime_ns,
        sha256=sha256_file(path),
        link_count=info.st_nlink,
    )


def identity_matches(path: Path, expected: SourceIdentity, *, require_hash: bool = True) -> bool:
    try:
        current = read_identity(path)
    except OSError:
        return False
    return (
        current.volume_id == expected.volume_id
        and current.file_id == expected.file_id
        and current.size_bytes == expected.size_bytes
        and current.mtime_ns == expected.mtime_ns
        and (not require_hash or current.sha256 == expected.sha256)
    )


def unsafe_file_feature(path: Path) -> str | None:
    info = path.stat()
    attributes = getattr(info, "st_file_attributes", 0)
    if attributes & (0x1000 | 0x40000 | 0x400000):
        return "CLOUD_PLACEHOLDER_BLOCKED"
    if info.st_nlink > 1:
        return "HARDLINK_BLOCKED"
    if os.name == "nt" and _has_alternate_data_stream(path):
        return "ALTERNATE_DATA_STREAM_BLOCKED"
    return None


def _has_alternate_data_stream(path: Path) -> bool:
    class StreamData(ctypes.Structure):
        _fields_ = [("StreamSize", ctypes.c_longlong), ("cStreamName", ctypes.c_wchar * 296)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.POINTER(StreamData), ctypes.c_uint]
    find_first.restype = ctypes.c_void_p
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [ctypes.c_void_p, ctypes.POINTER(StreamData)]
    find_next.restype = ctypes.c_int
    data = StreamData()
    handle = find_first(str(path), 0, ctypes.byref(data), 0)
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        return False
    try:
        while True:
            if data.cStreamName and data.cStreamName != "::$DATA":
                return True
            if not find_next(handle, ctypes.byref(data)):
                return False
    finally:
        kernel32.FindClose(ctypes.c_void_p(handle))
