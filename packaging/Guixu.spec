import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


ROOT = Path(SPECPATH).parent.resolve()
BACKEND = ROOT / "backend"


def _version() -> str:
    """The single source of truth is `backend/pyproject.toml`.

    The version used to be typed into this file as well as the packaging
    script, and the two drifted apart: a release tagged 0.9.0 shipped an
    artifact whose folder and archive were both still called `Guixu-0.1.0`.
    Nothing caught it, because the build genuinely succeeds - it just labels
    the output with a stale number. Reading the one declared version removes
    the second copy that can drift.
    """
    declared = (BACKEND / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', declared, re.MULTILINE)
    if not match:
        raise RuntimeError("backend/pyproject.toml does not declare a version")
    return match.group(1)


datas = [
    (str(ROOT / "contracts"), "contracts"),
    (str(ROOT / "seed"), "seed"),
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "README.md"), "docs"),
    (str(ROOT / "docs" / "product" / "workflows.md"), "docs"),
    (str(ROOT / "docs" / "product" / "limitations.md"), "docs"),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "docs"),
    (str(ROOT / "CHANGELOG.md"), "docs"),
]
datas += collect_data_files("rapidocr")

a = Analysis(
    [str(BACKEND / "src" / "guixu" / "__main__.py")],
    pathex=[str(BACKEND / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "clr",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "hypothesis"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Guixu",
    icon=str(ROOT / "packaging" / "assets" / "guixu.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="x86_64",
    uac_admin=False,
    uac_uiaccess=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=f"Guixu-{_version()}",
)
