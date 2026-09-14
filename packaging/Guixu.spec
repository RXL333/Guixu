from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


ROOT = Path(SPECPATH).parent.resolve()
BACKEND = ROOT / "backend"

datas = [
    (str(ROOT / "contracts"), "contracts"),
    (str(ROOT / "seed"), "seed"),
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    (str(ROOT / "README.md"), "docs"),
    (str(ROOT / "docs" / "USER_GUIDE.md"), "docs"),
    (str(ROOT / "KNOWN_LIMITATIONS.md"), "docs"),
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
    name="Guixu-0.1.0",
)
