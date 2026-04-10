# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Task Manager.

Run from the repository root on Windows:
    python -m PyInstaller taskmanager.spec

Tesseract OCR must be installed on the build machine. The spec file
auto-detects its location and bundles the binary + English language data.
"""

import os
import shutil
import sys

block_cipher = None

# ── Locate Tesseract on the build machine ─────────────────────────
# Common install paths on Windows. Override with TESSERACT_PATH env var.
_tess_search = [
    os.environ.get("TESSERACT_PATH", ""),
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tesseract-OCR"),
]

tesseract_dir = None
for p in _tess_search:
    if p and os.path.isfile(os.path.join(p, "tesseract.exe")):
        tesseract_dir = p
        break

tesseract_datas = []
if tesseract_dir:
    # Bundle the tesseract binary
    tesseract_datas.append(
        (os.path.join(tesseract_dir, "tesseract.exe"), "tesseract")
    )
    # Bundle required DLLs from the Tesseract directory
    for f in os.listdir(tesseract_dir):
        if f.lower().endswith(".dll"):
            tesseract_datas.append(
                (os.path.join(tesseract_dir, f), "tesseract")
            )
    # Bundle English trained data
    tessdata = os.path.join(tesseract_dir, "tessdata")
    if os.path.isdir(tessdata):
        eng_data = os.path.join(tessdata, "eng.traineddata")
        if os.path.isfile(eng_data):
            tesseract_datas.append((eng_data, os.path.join("tesseract", "tessdata")))
        # Also include the OSD data if present (for orientation detection)
        osd_data = os.path.join(tessdata, "osd.traineddata")
        if os.path.isfile(osd_data):
            tesseract_datas.append((osd_data, os.path.join("tesseract", "tessdata")))
    print(f"[spec] Bundling Tesseract from: {tesseract_dir}")
else:
    print("[spec] WARNING: Tesseract not found. The .exe will require Tesseract installed on the target machine.")
    print("[spec] Set TESSERACT_PATH=<dir> to specify the Tesseract install directory.")

# ── Analysis ──────────────────────────────────────────────────────

a = Analysis(
    ["taskmanager/main.py"],
    pathex=[],
    binaries=[],
    datas=tesseract_datas,
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pynput._util.win32",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused Qt modules to reduce bundle size
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtQuick",
        "PySide6.QtQml",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TaskManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # No console window — GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # Add an .ico path here for a custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TaskManager",
)
