# Task Manager

A screen-capture-to-task organizer with modular, snapping windows. Capture text from anything on your screen with a hotkey, organize tasks visually, and archive them when done.

Built with PySide6 (Qt for Python) — runs on Linux and ports to Windows with zero code changes.

## Features

- **Screen capture to task** — Press Super+T (configurable), select a region on any monitor, and OCR extracts the text into a new task window
- **Minimal task windows** — Thin 1px-bordered, frameless cards. No sticky-note aesthetics, just clean flat UI
- **Modular snapping** — Drag windows near each other and they snap together along edges (20px threshold). All sizes are multiples of a 40px grid unit, so windows always tile cleanly
- **Scroll-wheel resize** — Hold left click on the title bar and scroll to resize in fixed grid increments
- **Animated archival** — Click the checkmark to archive a task. It shrinks and flies away, and remaining windows slide to fill the gap
- **Archive browser** — Search, sort (8 modes), restore, or permanently delete archived tasks
- **Subtask checkboxes** — Each task can have multiple subtasks with toggle state
- **Inline editing** — Double-click a title to rename it
- **Persistence** — Tasks and positions are saved to SQLite and restored on launch
- **Themes** — Light (default), Dark, or System (auto-detect). Configurable in Settings
- **Customizable hotkey** — Change the capture shortcut in Settings without restarting

## Requirements

- Python 3.10+
- Tesseract OCR engine

## Install

```bash
# From the repository root:
pip install -r requirements.txt
sudo apt install tesseract-ocr        # Linux (Debian/Ubuntu)
# or: brew install tesseract           # macOS
# or: download installer from https://github.com/UB-Mannheim/tesseract/wiki  # Windows
```

## Run

```bash
./run.sh
# or directly:
python3 -m taskmanager.main
```

The app runs in the system tray. Right-click the tray icon for the menu (Capture, New Task, Archives, Settings, Quit).

## Usage

1. **Capture a task** — Press Super+T. A translucent overlay appears. Click and drag to select a screen region. The OCR'd text becomes a new task.
2. **Drag to organize** — Arrange windows by priority or due date (top-to-bottom, left-to-right). Windows snap to each other automatically.
3. **Resize** — Hold left click on the title bar, then scroll up/down to shrink/grow in 40px steps.
4. **Complete a task** — Click the checkmark button. The window animates to the archive and others slide to fill the gap.
5. **Browse archives** — Right-click tray > Archives. Search, sort, restore, or delete old tasks.

## Architecture

```
taskmanager/
├── main.py              # Entry point, system tray, signal wiring
├── constants.py         # Grid (40px), snap (20px), themes, defaults
├── models.py            # SQLite: tasks + archived_tasks tables
├── task_window.py       # Frameless draggable task card widget
├── task_manager.py      # Window orchestration, snapping, cascade
├── capture.py           # Global hotkey, selection overlay, OCR
├── animations.py        # Archive fly-away, slide fill, fade-in
├── archive_viewer.py    # Archive browser dialog
└── settings.py          # JSON settings persistence + dialog
```

## Configuration

Settings are stored at `~/.local/share/taskmanager/settings.json`. The database lives alongside it as `taskmanager.db`.

| Setting | Default | Options |
|---------|---------|---------|
| Theme | `light` | `light`, `dark`, `system` |
| Hotkey | Super+T | Any modifier+key combo via the Settings dialog |

## Building a standalone Windows .exe

You can package the entire app — Python runtime, all dependencies, and Tesseract OCR — into a single folder with a `TaskRip.exe`. End users just unzip and double-click. No installs needed.

### Prerequisites (on the Windows build machine)

1. **Python 3.10+** with pip
2. **Tesseract OCR** — install from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) (default path: `C:\Program Files\Tesseract-OCR`)
3. **App dependencies + PyInstaller:**
   ```
   pip install -r requirements.txt
   pip install pyinstaller
   ```

### Build

From the repository root:

```
python build_exe.py
```

Or manually:

```
python -m PyInstaller --clean --noconfirm taskmanager.spec
```

The output lands in `dist/TaskRip/`. The main executable is `dist/TaskRip/TaskRip.exe`.

**Important:** run the `.exe` from `dist/TaskRip/` — **not** from `build/`. PyInstaller leaves intermediate artifacts under `build/taskmanager/` that look similar but are missing the bundled Python DLL and will fail with `Failed to load Python DLL ... python3XX.dll`.

### Distribute

Zip the entire `dist/TaskRip/` folder and share it. The recipient unzips, runs `TaskRip.exe`, and everything works — Python, Qt, Tesseract, and all dependencies are bundled inside.

### Notes

- The build must run **on Windows** (PyInstaller creates executables for the OS it runs on)
- Use Python **3.12 or 3.13** to build. Python 3.14 is too new — PySide6 and PyInstaller don't ship matching wheels yet, and the resulting bundle will fail to load the Python DLL at startup
- If Tesseract is not found during the build, the .exe still works but OCR requires a separate Tesseract install on the target machine. Set `TESSERACT_PATH=C:\...\Tesseract-OCR` if auto-detection fails
- To add a custom icon, place an `.ico` file in the repo and set `icon="path/to/icon.ico"` in `taskmanager.spec`
- The default hotkey Super+T conflicts with Win+T on Windows — users should change it in Settings on first launch

## Cross-platform

The app uses only cross-platform libraries (PySide6, pynput, mss, pytesseract). To run on Windows without building an .exe, install the same pip packages plus the Tesseract Windows installer and run `python -m taskmanager.main`.
