# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec:  pyinstaller packaging/warpzip.spec --noconfirm
#   dist/WarpZip/WarpZip.exe  (GUI)      dist/WarpZip/wz.exe  (console CLI)
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules
import sys

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
VERSION = "1.0.0"
VT = tuple(int(x) for x in VERSION.split(".")) + (0,)

datas, binaries, hiddenimports = [], [], []
for pkg in ("py7zr", "pyzipper", "zstandard", "Cryptodome", "pyppmd", "pybcj", "inflate64", "brotli", "backports.zstd"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
datas += [(str(SRC / "warpzip" / "assets"), "warpzip/assets")]
if (ROOT / "bin").exists():            # optional 7-Zip engine (7z.exe + 7z.dll) for RAR/ISO/CAB...
    datas += [(str(ROOT / "bin"), "bin")]
datas += [(str(ROOT / "THIRD_PARTY_NOTICES.md"), "."), (str(ROOT / "README.md"), ".")]

excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore",
            "PySide6.QtMultimedia", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtCharts",
            "matplotlib", "numpy", "PIL"]

version = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
    )
    version = VSVersionInfo(
        ffi=FixedFileInfo(filevers=VT, prodvers=VT, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
        kids=[
            StringFileInfo([StringTable("041204B0", [   # Korean / Unicode
                StringStruct("CompanyName", "WarpZip"),
                StringStruct("FileDescription", "WARPZIP - Archive Manager"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "WarpZip"),
                StringStruct("LegalCopyright", "Copyright (c) WarpZip"),
                StringStruct("OriginalFilename", "WarpZip.exe"),
                StringStruct("ProductName", "WARPZIP"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0412, 1200])]),
        ],
    )


common = dict(pathex=[str(SRC)], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
              hookspath=[], runtime_hooks=[], excludes=excludes, noarchive=False)

a_gui = Analysis([str(ROOT / "packaging" / "launcher.py")], **common)
a_cli = Analysis([str(ROOT / "packaging" / "launcher.py")], **common)
MERGE((a_gui, "WarpZip", "WarpZip"), (a_cli, "wz", "wz"))

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)
icon = str(SRC / "warpzip" / "assets" / "app.ico")

exe_gui = EXE(pyz_gui, a_gui.scripts, [], exclude_binaries=True, name="WarpZip", console=False,
              icon=icon, version=version, upx=False, disable_windowed_traceback=False)
exe_cli = EXE(pyz_cli, a_cli.scripts, [], exclude_binaries=True, name="wz", console=True,
              icon=icon, version=version, upx=False)

coll = COLLECT(exe_gui, a_gui.binaries, a_gui.datas,
               exe_cli, a_cli.binaries, a_cli.datas,
               strip=False, upx=False, name="WarpZip")
