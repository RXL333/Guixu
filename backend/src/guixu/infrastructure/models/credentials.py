from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class CredentialError(RuntimeError):
    pass


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID), ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    """Stores API secrets in the current user's Windows Credential Manager."""

    prefix = "Guixu/model/"

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise CredentialError("WINDOWS_CREDENTIAL_MANAGER_UNAVAILABLE")
        self.advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)

    def _target(self, profile_id: str) -> str:
        return self.prefix + profile_id

    def set(self, profile_id: str, secret: str) -> str:
        if not secret or len(secret) > 4096:
            raise CredentialError("SECRET_INVALID")
        blob = secret.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        cred = CREDENTIALW(Type=1, TargetName=self._target(profile_id), CredentialBlobSize=len(blob),
                           CredentialBlob=buffer, Persist=2, UserName="Guixu")
        if not self.advapi.CredWriteW(ctypes.byref(cred), 0):
            raise CredentialError(f"CREDENTIAL_WRITE_FAILED:{ctypes.get_last_error()}")
        return self._target(profile_id)

    def get(self, profile_id: str) -> str | None:
        pointer = ctypes.POINTER(CREDENTIALW)()
        if not self.advapi.CredReadW(self._target(profile_id), 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return None
            raise CredentialError(f"CREDENTIAL_READ_FAILED:{ctypes.get_last_error()}")
        try:
            cred = pointer.contents
            raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return raw.decode("utf-16-le")
        finally:
            self.advapi.CredFree(pointer)

    def delete(self, profile_id: str) -> None:
        if not self.advapi.CredDeleteW(self._target(profile_id), 1, 0) and ctypes.get_last_error() != 1168:
            raise CredentialError(f"CREDENTIAL_DELETE_FAILED:{ctypes.get_last_error()}")

    def has(self, profile_id: str) -> bool:
        return self.get(profile_id) is not None
