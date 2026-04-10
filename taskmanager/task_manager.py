"""Orchestrates all task windows — snapping, layout, archival cascading."""

from PySide6.QtCore import QObject, Signal, QPoint
from PySide6.QtWidgets import QApplication

from . import constants
from .models import Database
from .task_window import TaskWindow
from .animations import animate_archive, animate_slide, animate_appear


class TaskManager(QObject):
    """Creates, tracks, snaps, and animates task windows."""

    archive_requested = Signal()  # emitted so main can flash the tray icon / button

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._windows: list[TaskWindow] = []
        self._active_anims = []  # prevent GC of running animations

    # ── Lifecycle ─────────────────────────────────────────────────

    def load_tasks(self):
        """Restore all saved tasks from the database."""
        for task in self.db.get_all_tasks():
            win = self._make_window(task)
            win.move(task["x"], task["y"])
            win.show()
            animate_appear(win)

    def save_all(self):
        """Persist every window's current geometry back to the database."""
        for win in self._windows:
            data = win.get_data()
            self.db.update_task(
                data["id"],
                title=data["title"],
                subtasks=data["subtasks"],
                x=data["x"], y=data["y"],
                width_units=data["width_units"],
                height_units=data["height_units"],
            )

    # ── Task creation ─────────────────────────────────────────────

    def create_task(self, title, subtasks=None):
        """Create a new task window from captured text (or manually)."""
        pos = self._next_open_position()
        task_id = self.db.add_task(
            title=title, subtasks=subtasks,
            x=pos.x(), y=pos.y(),
        )
        task_data = {
            "id": task_id,
            "title": title,
            "subtasks": subtasks or [],
            "width_units": constants.DEFAULT_WIDTH_UNITS,
            "height_units": constants.DEFAULT_HEIGHT_UNITS,
        }
        win = self._make_window(task_data)
        win.move(pos)
        win.show()
        animate_appear(win)
        return win

    def restore_task(self, task_data):
        """Restore an archived task as a visible window (public API for main.py)."""
        win = self._make_window(task_data)
        win.move(task_data.get("x", 100), task_data.get("y", 100))
        win.show()
        animate_appear(win)
        return win

    def _make_window(self, task_data):
        win = TaskWindow(
            task_id=task_data["id"],
            title=task_data.get("title", ""),
            subtasks=task_data.get("subtasks", []),
            width_units=task_data.get("width_units"),
            height_units=task_data.get("height_units"),
        )
        win.task_completed.connect(self._on_task_completed)
        win.task_changed.connect(self._on_task_changed)
        win.drag_finished.connect(self._on_drag_finished)
        self._windows.append(win)
        return win

    # ── Positioning ───────────────────────────────────────────────

    def _next_open_position(self):
        """Find the next available grid-aligned position that doesn't overlap."""
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
        else:
            from PySide6.QtCore import QRect
            geom = QRect(0, 0, 1920, 1080)

        step_x = constants.DEFAULT_WIDTH_UNITS * constants.GRID_UNIT
        step_y = constants.DEFAULT_HEIGHT_UNITS * constants.GRID_UNIT
        margin = 10

        x, y = margin, margin
        while y + step_y < geom.height():
            while x + step_x < geom.width():
                candidate = QPoint(x, y)
                if not self._overlaps_any(candidate, step_x, step_y):
                    return candidate
                x += step_x + margin
            x = margin
            y += step_y + margin

        # Fallback: stack with offset
        n = len(self._windows)
        return QPoint(margin + (n * 20) % 200, margin + (n * 20) % 200)

    def _overlaps_any(self, pos, w, h):
        from PySide6.QtCore import QRect
        candidate = QRect(pos.x(), pos.y(), w, h)
        for win in self._windows:
            if not win.isVisible():
                continue
            existing = QRect(win.x(), win.y(), win.width(), win.height())
            if candidate.intersects(existing):
                return True
        return False

    # ── Snapping ──────────────────────────────────────────────────

    def find_snap_position(self, window):
        """Snap window edges to nearby windows' edges."""
        px, py = window.x(), window.y()
        pw, ph = window.width(), window.height()
        snap_x, snap_y = px, py
        best_dx, best_dy = constants.SNAP_THRESHOLD + 1, constants.SNAP_THRESHOLD + 1

        for other in self._windows:
            if other is window or not other.isVisible():
                continue
            ox, oy = other.x(), other.y()
            ow, oh = other.width(), other.height()

            # Horizontal edge pairs: left↔right, right↔left, left↔left, right↔right
            pairs_x = [
                (px, ox + ow),          # my left → their right
                (px + pw, ox),          # my right → their left
                (px, ox),              # my left → their left
                (px + pw, ox + ow),    # my right → their right
            ]
            for my_edge, their_edge in pairs_x:
                d = abs(my_edge - their_edge)
                if d < best_dx:
                    best_dx = d
                    snap_x = px + (their_edge - my_edge)

            # Vertical edge pairs: top↔bottom, bottom↔top, top↔top, bottom↔bottom
            pairs_y = [
                (py, oy + oh),
                (py + ph, oy),
                (py, oy),
                (py + ph, oy + oh),
            ]
            for my_edge, their_edge in pairs_y:
                d = abs(my_edge - their_edge)
                if d < best_dy:
                    best_dy = d
                    snap_y = py + (their_edge - my_edge)

        result_x = snap_x if best_dx <= constants.SNAP_THRESHOLD else px
        result_y = snap_y if best_dy <= constants.SNAP_THRESHOLD else py
        return QPoint(result_x, result_y)

    # ── Event handlers ────────────────────────────────────────────

    def _on_drag_finished(self, window):
        snapped = self.find_snap_position(window)
        if snapped != window.pos():
            window.move(snapped)
        self._on_task_changed(window.task_id)

    def _on_task_changed(self, task_id):
        for win in self._windows:
            if win.task_id == task_id:
                data = win.get_data()
                self.db.update_task(
                    task_id,
                    title=data["title"], subtasks=data["subtasks"],
                    x=data["x"], y=data["y"],
                    width_units=data["width_units"],
                    height_units=data["height_units"],
                )
                break

    def _on_task_completed(self, task_id):
        """Archive the task with a fly-away animation, then cascade remaining."""
        target_win = None
        target_idx = -1
        for i, win in enumerate(self._windows):
            if win.task_id == task_id:
                target_win = win
                target_idx = i
                break
        if not target_win:
            return

        # Capture original position BEFORE the animation moves the window
        original_pos = target_win.pos()

        # Determine archive animation target (top-right of screen)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            archive_target = QPoint(geom.right() - 50, geom.top() + 10)
        else:
            archive_target = QPoint(1870, 10)

        # Remove from our list immediately (prevents snapping to it)
        self._windows.pop(target_idx)

        def after_archive():
            self.db.archive_task(task_id)
            target_win.hide()
            target_win.deleteLater()
            self._cascade_fill(target_idx, original_pos)
            self.archive_requested.emit()

        anim = animate_archive(target_win, archive_target, after_archive)
        self._active_anims.append(anim)
        anim.finished.connect(lambda a=anim: self._active_anims.remove(a) if a in self._active_anims else None)

    def _cascade_fill(self, removed_idx, removed_pos):
        """Slide subsequent windows up/left to fill the gap left by an archived task."""
        if removed_idx >= len(self._windows):
            return

        # Simple cascade: move each subsequent window to the position of the one before it
        positions = [removed_pos]
        for i in range(removed_idx, len(self._windows)):
            win = self._windows[i]
            positions.append(win.pos())
            anim = animate_slide(win, positions[i - removed_idx])
            self._active_anims.append(anim)
            anim.finished.connect(
                lambda a=anim: self._active_anims.remove(a) if a in self._active_anims else None
            )

    # ── Cleanup ───────────────────────────────────────────────────

    def close_all(self):
        self.save_all()
        for win in self._windows:
            win.close()
        self._windows.clear()
