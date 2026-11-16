# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the packaged game: one folder dist/Hardwood/ with a windowed Hardwood.exe.
# Build with: python scripts/build_exe.py  (runs npm run build, PyInstaller, then the smoke test)
#
# Bundled read-only data only, and no real-player data: the fictional league, the schema-only template DB
# (tests/test_release_data.py checks it is empty) and the fictional filler players. Never bundled: mods/
# (Real Names 2002 stays out, D1), saves/, the real-player DBs (nba_sim_modern.db, nba_sim_2002.db),
# data/nba_sim.db (the active DB lives in Documents/Hardwood), scratch/.
from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("frontend/dist", "frontend/dist"),
    ("data/leagues/fictional_2002", "data/leagues/fictional_2002"),
    ("data/nba_sim_template.db", "data"),
    ("data/filler_players.json", "data"),
]

hiddenimports = ["server", "main"]
# tournament/ and utils/ are dead stubs (their __init__ imports modules that no longer exist).
for package in ("core", "trades", "offseason"):
    hiddenimports += collect_submodules(package)

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tests", "scripts", "scratch", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Hardwood",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/hardwood.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Hardwood",
)
