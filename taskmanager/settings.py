"""User settings: persistence (JSON) and settings dialog."""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QKeySequenceEdit, QGroupBox, QFormLayout,
)

from . import constants


def _settings_path():
    data_dir = Path.home() / ".local" / "share" / "taskmanager"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / constants.SETTINGS_FILENAME


def load_settings():
    """Load settings from disk, returning defaults for missing keys."""
    defaults = {
        "theme": "light",
        "hotkey": constants.DEFAULT_HOTKEY,
    }
    path = _settings_path()
    if path.exists():
        try:
            with open(path) as f:
                saved = json.load(f)
            defaults.update(saved)
        except (json.JSONDecodeError, IOError):
            pass
    return defaults


def save_settings(settings: dict):
    """Persist settings dict to disk."""
    path = _settings_path()
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)


def detect_system_theme():
    """Try to detect OS dark/light preference. Returns 'dark' or 'light'."""
    try:
        import subprocess
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        )
        if "dark" in result.stdout.lower():
            return "dark"
    except Exception:
        pass
    return "light"


class SettingsDialog(QDialog):
    """Dialog for configuring hotkey and theme."""

    settings_changed = Signal(dict)  # emits the full updated settings dict

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self._settings = dict(current_settings)
        self.setWindowTitle("Task Manager Settings")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Theme ─────────────────────────────────────────────────
        theme_group = QGroupBox("Appearance")
        theme_form = QFormLayout(theme_group)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Light", "Dark", "System (auto-detect)"])
        current_theme = self._settings.get("theme", "light")
        idx_map = {"light": 0, "dark": 1, "system": 2}
        self._theme_combo.setCurrentIndex(idx_map.get(current_theme, 0))
        theme_form.addRow("Theme:", self._theme_combo)

        layout.addWidget(theme_group)

        # ── Hotkey ────────────────────────────────────────────────
        hotkey_group = QGroupBox("Capture Hotkey")
        hotkey_form = QFormLayout(hotkey_group)

        self._hotkey_edit = QKeySequenceEdit()
        # Try to set current hotkey display
        current_hotkey = self._settings.get("hotkey", constants.DEFAULT_HOTKEY)
        qt_seq = _pynput_to_qt_keyseq(current_hotkey)
        if qt_seq:
            self._hotkey_edit.setKeySequence(qt_seq)

        hotkey_hint = QLabel("Click the field above and press your desired key combination.")
        hotkey_hint.setFont(QFont("Sans", 8))
        hotkey_hint.setStyleSheet(f"color: {constants.SUBTITLE_COLOR};")

        hotkey_form.addRow("Shortcut:", self._hotkey_edit)
        hotkey_form.addRow("", hotkey_hint)

        layout.addWidget(hotkey_group)

        # ── Buttons ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {constants.ACCENT_COLOR}; color: #fff;
                border: none; border-radius: 4px; padding: 6px 24px;
            }}
            QPushButton:hover {{ background: {constants.ACCENT_COLOR}cc; }}
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self):
        # Theme
        theme_map = {0: "light", 1: "dark", 2: "system"}
        self._settings["theme"] = theme_map.get(self._theme_combo.currentIndex(), "light")

        # Hotkey
        seq = self._hotkey_edit.keySequence()
        if seq and seq.count() > 0:
            pynput_str = _qt_keyseq_to_pynput(seq)
            if pynput_str:
                self._settings["hotkey"] = pynput_str

        save_settings(self._settings)
        self.settings_changed.emit(self._settings)
        self.accept()


# ── Key sequence conversion helpers ───────────────────────────────

def _pynput_to_qt_keyseq(pynput_str):
    """Best-effort convert pynput hotkey string to QKeySequence for display."""
    mapping = {
        "<ctrl>": "Ctrl", "<shift>": "Shift", "<alt>": "Alt",
        "<cmd>": "Meta", "<super>": "Meta",
    }
    parts = pynput_str.split("+")
    qt_parts = []
    for p in parts:
        p = p.strip()
        if p in mapping:
            qt_parts.append(mapping[p])
        else:
            qt_parts.append(p.upper() if len(p) == 1 else p.capitalize())
    try:
        return QKeySequence.fromString("+".join(qt_parts))
    except Exception:
        return None


def _qt_keyseq_to_pynput(seq):
    """Convert QKeySequence back to pynput hotkey string."""
    text = seq.toString()  # e.g. "Meta+T"
    if not text:
        return None
    mapping = {
        "Ctrl": "<ctrl>", "Shift": "<shift>", "Alt": "<alt>",
        "Meta": "<cmd>",
    }
    parts = text.split("+")
    pynput_parts = []
    for p in parts:
        p = p.strip()
        if p in mapping:
            pynput_parts.append(mapping[p])
        else:
            pynput_parts.append(p.lower())
    return "+".join(pynput_parts)
