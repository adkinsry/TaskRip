#!/usr/bin/env python3
"""Build a standalone Windows .exe for TaskRip.

Run this on Windows from the repository root:

    python build_exe.py

Prerequisites:
    pip install -r requirements.txt
    pip install pyinstaller
    Tesseract OCR installed (https://github.com/UB-Mannheim/tesseract/wiki)

The built application will be in:  dist/TaskRip/TaskRip.exe

IMPORTANT: After a successful build, run the exe from dist/TaskRip/, NOT
from build/. The build/ directory contains intermediate artifacts that
will fail with "Failed to load Python DLL" if executed directly.
"""

import os
import subprocess
import sys


SPEC_FILE = "taskmanager.spec"
APP_NAME = "TaskRip"            # must match `name=` in taskmanager.spec
DIST_DIR = os.path.join("dist", APP_NAME)
EXE_PATH = os.path.join(DIST_DIR, f"{APP_NAME}.exe")


def main():
    # Verify we're at the repo root
    if not os.path.isfile(SPEC_FILE):
        print(f"ERROR: Run this script from the repository root (where {SPEC_FILE} lives).")
        sys.exit(1)

    # Python version guard — PyInstaller and PySide6 typically lag the
    # very latest CPython release by several months. Warn loudly if the
    # user is on an unsupported-cutting-edge version.
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 14):
        print("=" * 70)
        print(f"WARNING: You are using Python {major}.{minor}.")
        print("PySide6 and PyInstaller may not fully support this version yet.")
        print("If the build fails or the resulting .exe can't load the Python")
        print("DLL, install Python 3.12 or 3.13 and rebuild.")
        print("=" * 70)
        print()

    # Check PyInstaller is available
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Check app dependencies
    missing = []
    for pkg in ["PySide6", "pytesseract", "PIL", "pynput", "mss"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    # Check Tesseract
    tess_path = os.environ.get("TESSERACT_PATH", "")
    if not tess_path:
        for candidate in [
            r"C:\Program Files\Tesseract-OCR",
            r"C:\Program Files (x86)\Tesseract-OCR",
        ]:
            if os.path.isfile(os.path.join(candidate, "tesseract.exe")):
                tess_path = candidate
                break

    if tess_path:
        print(f"Tesseract found: {tess_path}")
    else:
        print("WARNING: Tesseract not found on this machine.")
        print("The .exe will build but OCR won't work unless Tesseract is installed on the target machine.")
        print("Set TESSERACT_PATH=<dir> or install Tesseract to a default location.")
        print()

    # Run PyInstaller
    print("Building with PyInstaller...")
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", SPEC_FILE]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("Build failed.")
        sys.exit(1)

    # Report
    if os.path.isfile(EXE_PATH):
        size_mb = os.path.getsize(EXE_PATH) / (1024 * 1024)
        abs_exe = os.path.abspath(EXE_PATH)
        abs_dir = os.path.abspath(DIST_DIR)
        print()
        print("=" * 70)
        print("BUILD SUCCESSFUL")
        print("=" * 70)
        print()
        print(f"  Run this EXE:  {abs_exe}")
        print(f"  From folder:   {abs_dir}")
        print(f"  EXE size:      {size_mb:.1f} MB")
        print()
        print("  DO NOT run the exe under build/ — that's an intermediate")
        print("  PyInstaller artifact and will fail with a Python DLL error.")
        print()
        print(f"  To distribute: zip the entire dist/{APP_NAME}/ folder.")
        print("  End users just unzip and run the .exe — no Python or")
        print("  Tesseract install needed on the target machine.")
        print("=" * 70)
    else:
        print(f"Build completed but {APP_NAME}.exe not found at {EXE_PATH}.")
        print("Check the dist/ directory.")
        sys.exit(1)


if __name__ == "__main__":
    main()
