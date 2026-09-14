from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path

from guixu.domain.plans import SourceIdentity
from guixu.infrastructure.filesystem.identity import identity_matches


def locked_source_chunks(path: Path, expected: SourceIdentity, chunk_size: int):
    """Yield bytes while denying concurrent write/delete access on Windows."""
    if os.name != "nt":
        with path.open("rb") as source:
            while chunk := source.read(chunk_size):
                yield chunk
        return
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    handle = create_file(str(path), 0x80000000, 0x00000001, None, 3, 0x08000000, None)
    if handle == wintypes.HANDLE(-1).value:
        error = ctypes.get_last_error()
        raise OSError(error, os.strerror(error), str(path))
    try:
        current = path.stat()
        if (
            str(current.st_dev) != expected.volume_id
            or str(current.st_ino) != expected.file_id
            or current.st_size != expected.size_bytes
            or current.st_mtime_ns != expected.mtime_ns
        ):
            raise OSError("source identity changed while locked")
        read_file = kernel32.ReadFile
        read_file.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        read_file.restype = wintypes.BOOL
        buffer = ctypes.create_string_buffer(chunk_size)
        count = wintypes.DWORD()
        digest = hashlib.sha256()
        while True:
            if not read_file(handle, buffer, len(buffer), ctypes.byref(count), None):
                error = ctypes.get_last_error()
                raise OSError(error, os.strerror(error), str(path))
            if count.value == 0:
                break
            chunk = buffer.raw[: count.value]
            digest.update(chunk)
            yield chunk
        if digest.hexdigest() != expected.sha256:
            raise OSError("source hash changed while locked")
    finally:
        close_handle(handle)


def _locked_handle_matches(kernel32, handle, path: Path, expected: SourceIdentity) -> bool:
    current = path.stat()
    if (
        str(current.st_dev) != expected.volume_id
        or str(current.st_ino) != expected.file_id
        or current.st_size != expected.size_bytes
        or current.st_mtime_ns != expected.mtime_ns
    ):
        return False
    from ctypes import wintypes
    read_file = kernel32.ReadFile
    read_file.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    read_file.restype = wintypes.BOOL
    digest = hashlib.sha256()
    buffer = ctypes.create_string_buffer(1024 * 1024)
    read_count = wintypes.DWORD()
    while True:
        if not read_file(handle, buffer, len(buffer), ctypes.byref(read_count), None):
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error), str(path))
        if read_count.value == 0:
            break
        digest.update(buffer.raw[: read_count.value])
    return digest.hexdigest() == expected.sha256


def rename_source_no_clobber(source: Path, target: Path, expected: SourceIdentity) -> None:
    """Rename the exact verified Windows file handle without replacement."""
    if os.name != "nt":
        if not identity_matches(source, expected):
            raise OSError("source identity changed")
        os.link(source, target)
        source.unlink()
        return

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    set_information.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    DELETE = 0x00010000
    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    OPEN_EXISTING = 3
    FILE_FLAG_WRITE_THROUGH = 0x80000000
    FILE_RENAME_INFO_CLASS = 3
    handle = create_file(str(source), GENERIC_READ | DELETE, FILE_SHARE_READ, None, OPEN_EXISTING, FILE_FLAG_WRITE_THROUGH, None)
    invalid = wintypes.HANDLE(-1).value
    if handle == invalid:
        error = ctypes.get_last_error()
        raise OSError(error, os.strerror(error), str(source))
    try:
        if not _locked_handle_matches(kernel32, handle, source, expected):
            raise OSError("source identity changed while locked")
        filename = str(target)

        class RenameInfo(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("RootDirectory", wintypes.HANDLE),
                ("FileNameLength", wintypes.DWORD),
                ("FileName", wintypes.WCHAR * (len(filename) + 1)),
            ]

        info = RenameInfo()
        info.Flags = 0  # ReplaceIfExists = FALSE for FileRenameInfo.
        info.RootDirectory = None
        info.FileNameLength = len(filename.encode("utf-16-le"))
        info.FileName = filename
        if not set_information(handle, FILE_RENAME_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.get_last_error()
            if target.exists():
                raise FileExistsError(error, os.strerror(error), str(target))
            raise OSError(error, os.strerror(error), str(source))
    finally:
        close_handle(handle)
