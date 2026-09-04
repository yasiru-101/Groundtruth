# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a single-file Groundtruth desktop executable.

Build:
    pyinstaller groundtruth.spec --clean

The resulting dist/groundtruth.exe contains the Python runtime, the backend,
the built React SPA, and the demo snapshot. The user places a .env file next
to the executable (or fills in the Settings UI) to supply tokens.
"""

from pathlib import Path

project_root = Path(SPECPATH).resolve()
src_root = project_root / "src"
static_dir = src_root / "groundtruth" / "api" / "static"
demo_dir = project_root / "demo"
policy_file = project_root / "scoring_policy.yaml"

entry_script = src_root / "groundtruth" / "api" / "__main__.py"

# Files embedded in the executable and extracted to sys._MEIPASS at runtime.
datas = [
    (str(static_dir), "static"),
    (str(demo_dir / "artifacts"), "demo/artifacts"),
    (str(demo_dir / "fixtures"), "demo/fixtures"),
    (str(policy_file), "."),
]

# Submodules that may be imported dynamically or missed by dependency scanning.
hiddenimports = [
    "groundtruth.__main__",
    "groundtruth.api.app",
    "groundtruth.api.settings",
    "groundtruth.config",
    "groundtruth.connections",
    "groundtruth.connections.store",
    "groundtruth.connections.overlay",
    "groundtruth.connections.urls",
    "groundtruth.safety.secrets",
    "groundtruth.api.routers.agents",
    "groundtruth.api.routers.auth",
    "groundtruth.api.routers.board",
    "groundtruth.api.routers.connections",
    "groundtruth.api.routers.discrepancies",
    "groundtruth.api.routers.integrity",
    "groundtruth.api.routers.jobs",
    "groundtruth.api.routers.meta",
    "groundtruth.api.routers.runs",
    "groundtruth.api.routers.score",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
]

a = Analysis(
    [str(entry_script)],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="groundtruth",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
