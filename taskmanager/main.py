"""Task Manager — entry point, system tray, and signal wiring."""

import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QInputDialog

from .models import Database
from .task_manager import TaskManager
from .capture import CaptureManager
from .archive_viewer import ArchiveViewer
from .settings import SettingsDialog, load_settings, detect_system_theme
from . import constants


def _make_tray_icon():
    """Generate a simple programmatic tray icon (no external file needed)."""
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(constants.ACCENT_COLOR))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 28, 28, 6, 6)
    p.setPen(QColor("#ffffff"))
    p.setFont(QFont("Sans", 16, QFont.Bold))
    p.drawText(px.rect(), Qt.AlignCenter, "T")
    p.end()
    return QIcon(px)


def _resolve_theme(name):
    """Resolve 'system' to an actual theme name."""
    if name == "system":
        return detect_system_theme()
    return name


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("TaskManager")
    app.setQuitOnLastWindowClosed(False)  # keep running in tray

    # Load and apply settings
    settings = load_settings()
    constants.apply_theme(_resolve_theme(settings.get("theme", "light")))
    hotkey = settings.get("hotkey", constants.DEFAULT_HOTKEY)

    db = Database()
    task_mgr = TaskManager(db)
    capture_mgr = CaptureManager(hotkey=hotkey)

    # Wire capture → task creation
    capture_mgr.task_captured.connect(task_mgr.create_task)

    # ── System tray ───────────────────────────────────────────────
    tray = QSystemTrayIcon(_make_tray_icon(), app)
    tray.setToolTip(f"Task Manager — {hotkey} to capture")

    menu = QMenu()

    capture_action = QAction(f"Capture Task ({hotkey})", menu)
    capture_action.triggered.connect(capture_mgr.trigger_capture)
    menu.addAction(capture_action)

    new_action = QAction("New Task…", menu)
    new_action.triggered.connect(lambda: _manual_new_task(task_mgr))
    menu.addAction(new_action)

    menu.addSeparator()

    archive_action = QAction("Archives…", menu)
    archive_action.triggered.connect(lambda: _open_archives(db, task_mgr))
    menu.addAction(archive_action)

    settings_action = QAction("Settings…", menu)

    def open_settings():
        current = load_settings()
        dlg = SettingsDialog(current)
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        def on_changed(new_settings):
            nonlocal hotkey
            # Apply theme
            theme = _resolve_theme(new_settings.get("theme", "light"))
            constants.apply_theme(theme)
            # Update hotkey
            new_hotkey = new_settings.get("hotkey", constants.DEFAULT_HOTKEY)
            if new_hotkey != hotkey:
                hotkey = new_hotkey
                capture_mgr.update_hotkey(hotkey)
                capture_action.setText(f"Capture Task ({hotkey})")
                tray.setToolTip(f"Task Manager — {hotkey} to capture")

        dlg.settings_changed.connect(on_changed)
        dlg.exec()

    settings_action.triggered.connect(open_settings)
    menu.addAction(settings_action)

    menu.addSeparator()

    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(lambda: _quit(app, task_mgr, capture_mgr, db))
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()

    # Restore saved tasks
    task_mgr.load_tasks()

    # Start hotkey listener
    capture_mgr.start()

    # Auto-save periodically (every 30 seconds)
    save_timer = QTimer(app)
    save_timer.timeout.connect(task_mgr.save_all)
    save_timer.start(30_000)

    tray.showMessage(
        "Task Manager",
        f"Running in system tray. Press {hotkey} to capture a task from screen.",
        QSystemTrayIcon.Information,
        3000,
    )

    sys.exit(app.exec())


def _manual_new_task(task_mgr):
    title, ok = QInputDialog.getText(None, "New Task", "Task title:")
    if ok and title.strip():
        task_mgr.create_task(title.strip())


def _open_archives(db, task_mgr):
    viewer = ArchiveViewer(db)

    def on_restore(new_task_id):
        task_data = None
        for t in db.get_all_tasks():
            if t["id"] == new_task_id:
                task_data = t
                break
        if task_data:
            task_mgr.restore_task(task_data)

    viewer.task_restored.connect(on_restore)
    viewer.exec()


def _quit(app, task_mgr, capture_mgr, db):
    task_mgr.close_all()
    capture_mgr.stop()
    db.close()
    app.quit()


if __name__ == "__main__":
    main()
