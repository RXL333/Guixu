"""S02 - what may be authorized as a source or destination root.

`AGENTS.md` requires that the app never touches personal or system directories
outside an explicit grant. A grant is the one door into the filesystem, so what it
refuses is the whole of that boundary.

The typed-grant API takes any string the caller sends, and a file organizer given
a root will eventually move things inside it. Before this file existed,
`C:\\Windows`, `C:\\Program Files`, `C:\\ProgramData` and `C:\\Users\\Public` were
all accepted without complaint, as was a drive root. There was no system-path
check anywhere in the grant path - which is precisely the "system path" half of
S02, and it was entirely uncovered.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from guixu.infrastructure.filesystem.grants import GrantError, canonicalize_directory


PROTECTED_SUBTREES = [
    pytest.param("C:/Windows", id="windows-root"),
    pytest.param("C:/Windows/System32", id="windows-system32"),
    pytest.param("C:/WINDOWS/System32/config", id="windows-uppercase-variant"),
    pytest.param("C:/Program Files", id="program-files"),
    pytest.param("C:/Program Files (x86)", id="program-files-x86"),
    pytest.param("C:/ProgramData", id="program-data"),
    pytest.param("C:/Users", id="users-container"),
    pytest.param("C:/Users/Public", id="users-public"),
    pytest.param("C:/$Recycle.Bin", id="recycle-bin"),
    pytest.param("C:/System Volume Information", id="system-volume-information"),
]

PROTECTED_ROOTS_ONLY = [
    pytest.param("C:/", id="c-drive-root"),
    pytest.param("D:/", id="d-drive-root"),
]


@pytest.mark.skipif(os.name != "nt", reason="the protected set is Windows-specific")
@pytest.mark.parametrize("path", PROTECTED_SUBTREES)
def test_s02_system_locations_cannot_be_authorized(tmp_path: Path, path: str):
    """Pointing the organizer at the OS must fail at the grant, not at the first move."""
    with pytest.raises(GrantError) as failure:
        canonicalize_directory(path)
    assert str(failure.value) in {"PROTECTED_LOCATION_BLOCKED", "PATH_INVALID"}


@pytest.mark.skipif(os.name != "nt", reason="the protected set is Windows-specific")
@pytest.mark.parametrize("path", PROTECTED_ROOTS_ONLY)
def test_s02_a_drive_root_cannot_be_authorized(path: str):
    """A whole volume is never a filing cabinet, even though it is a real directory."""
    with pytest.raises(GrantError) as failure:
        canonicalize_directory(path)
    assert str(failure.value) == "PROTECTED_LOCATION_BLOCKED"


@pytest.mark.skipif(os.name != "nt", reason="the protected set is Windows-specific")
def test_s02_the_user_profile_root_is_blocked_but_its_folders_are_not(tmp_path: Path):
    """The distinction that keeps the rule from becoming useless.

    Blocking the whole profile subtree would take Documents, Downloads, Pictures
    and every project folder with it - which is the product. Only the profile
    root itself is refused, because that is the one path that puts `AppData`,
    `.ssh` and profile-root configuration in reach of a category rename.
    """
    profile = os.environ.get("USERPROFILE")
    if not profile:
        pytest.skip("USERPROFILE is not set in this session")
    with pytest.raises(GrantError) as failure:
        canonicalize_directory(profile)
    assert str(failure.value) == "PROTECTED_LOCATION_BLOCKED"

    allowed = tmp_path / "Downloads" / "2024" / "receipts"
    allowed.mkdir(parents=True)
    assert canonicalize_directory(allowed) == allowed.resolve()


@pytest.mark.skipif(os.name != "nt", reason="the protected set is Windows-specific")
def test_s02_a_similar_looking_sibling_folder_is_not_mistaken_for_a_system_one(tmp_path: Path):
    """`WindowsOld` must not be caught by a string-prefix match against `Windows`."""
    sibling = tmp_path / "WindowsOld"
    (sibling / "project").mkdir(parents=True)
    assert canonicalize_directory(sibling) == sibling.resolve()
    assert canonicalize_directory(sibling / "project") == (sibling / "project").resolve()


def test_s02_an_ordinary_folder_still_resolves_normally(tmp_path: Path):
    """The guard must not narrow what the product is for."""
    folder = tmp_path / "照片" / "2026"
    folder.mkdir(parents=True)
    assert canonicalize_directory(folder) == folder.resolve()
