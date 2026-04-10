#!/usr/bin/env python3
"""Build a standalone Windows .exe for Task Manager.

Run this on Windows from the repository root:

    python build_exe.py

Prerequisites:
    pip install pyinstaller
    Tesseract OCR installed (https://github.com/UB-Mannheim/tesseract/wiki)

The built application will be in:  dist/TaskManager/TaskManager.exe
"""

import os
import subprocess
import sys


def main():
    # Verify we're at the repo root
    if not os.path.isfile("taskmanager.spec"):
        print("ERROR: Run this script from the repository root (where taskmanager.spec lives).")
        sys.exit(1)

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
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "taskmanager.spec"]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("Build failed.")
        sys.exit(1)

    # Report
    dist_dir = os.path.join("dist", "TaskManager")
    exe_path = os.path.join(dist_dir, "TaskManager.exe")
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print()
        print(f"Build successful!")
        print(f"  Executable: {os.path.abspath(exe_path)}")
        print(f"  Folder:     {os.path.abspath(dist_dir)}")
        print(f"  EXE size:   {size_mb:.1f} MB")
        print()
        print("To distribute: zip the entire dist/TaskManager/ folder.")
        print("End users just unzip and run TaskManager.exe — no Python or Tesseract install needed.")
    else:
        print("Build completed but TaskManager.exe not found in expected location.")
        print("Check the dist/ directory.")


if __name__ == "__main__":
    main()
