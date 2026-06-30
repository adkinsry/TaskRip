"""Orchestrates all task windows — snapping, layout, archival cascading."""

from PySide6.QtCore import QObject, Signal, QPoint, QRect
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

    def reload_for_theme(self):
        """Persist, then rebuild every window so it picks up the current
        theme colors (stylesheets are applied at construction time)."""
        self.save_all()
        for win in self._windows:
            win.close()
            win.deleteLater()
        self._windows.clear()
        self.load_tasks()

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
        win.task_deleted.connect(self._on_task_deleted)
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
        """Snap window edges to nearby windows' edges.

        An X-axis snap is only considered against windows the dragged window
        is vertically near (and vice-versa), so a distant window can't drag
        an axis to align with it. A final guard cancels any snap that would
        land the window substantially on top of another.
        """
        px, py = window.x(), window.y()
        pw, ph = window.width(), window.height()
        T = constants.SNAP_THRESHOLD
        snap_x, snap_y = px, py
        best_dx, best_dy = T + 1, T + 1

        def near(a0, a1, b0, b1):
            # Ranges [a0,a1] and [b0,b1] overlap or sit within T of each other.
            return a0 <= b1 + T and b0 <= a1 + T

        for other in self._windows:
            if other is window or not other.isVisible():
                continue
            ox, oy = other.x(), other.y()
            ow, oh = other.width(), other.height()

            # X snaps only when the two windows are vertically near.
            if near(py, py + ph, oy, oy + oh):
                for my_edge, their_edge in (
                    (px, ox + ow),        # my left  → their right  (adjacency)
                    (px + pw, ox),        # my right → their left   (adjacency)
                    (px, ox),             # my left  → their left   (alignment)
                    (px + pw, ox + ow),   # my right → their right  (alignment)
                ):
                    d = abs(my_edge - their_edge)
                    if d < best_dx:
                        best_dx = d
                        snap_x = px + (their_edge - my_edge)

            # Y snaps only when the two windows are horizontally near.
            if near(px, px + pw, ox, ox + ow):
                for my_edge, their_edge in (
                    (py, oy + oh),
                    (py + ph, oy),
                    (py, oy),
                    (py + ph, oy + oh),
                ):
                    d = abs(my_edge - their_edge)
                    if d < best_dy:
                        best_dy = d
                        snap_y = py + (their_edge - my_edge)

        rx = snap_x if best_dx <= T else px
        ry = snap_y if best_dy <= T else py

        # Never snap a window onto another. Edge-adjacency snaps barely touch
        # (overlap ≈ 0); only an alignment-on-both-axes collision overlaps
        # heavily — in that case keep where the user dropped it.
        cand = QRect(rx, ry, pw, ph)
        for other in self._windows:
            if other is window or not other.isVisible():
                continue
            inter = cand.intersected(
                QRect(other.x(), other.y(), other.width(), other.height())
            )
            if inter.width() > 2 and inter.height() > 2:
                area = inter.width() * inter.height()
                smaller = min(pw * ph, other.width() * other.height())
                if smaller > 0 and area > 0.30 * smaller:
                    return QPoint(px, py)
        return QPoint(rx, ry)

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

    def _on_task_deleted(self, task_id):
        """Permanently discard an active task (no archival) after confirming."""
        target = None
        for win in self._windows:
            if win.task_id == task_id:
                target = win
                break
        if target is None:
            return
        from PySide6.QtWidgets import QMessageBox
        resp = QMessageBox.question(
            target, "Delete task",
            "Delete this task? It will NOT be saved to the archive.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        removed_rect = QRect(target.x(), target.y(),
                             target.width(), target.height())
        self._windows.remove(target)
        target.close()
        target.deleteLater()
        self.db.delete_task(task_id)
        self._cascade_fill(removed_rect)

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

        # Capture the archived window's rectangle BEFORE the animation
        # shrinks/moves it — the cascade needs its real geometry.
        removed_rect = QRect(target_win.x(), target_win.y(),
                             target_win.width(), target_win.height())

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
            # Compute the cascade from CURRENT state, not a stale index.
            self._cascade_fill(removed_rect)
            self.archive_requested.emit()

        anim = animate_archive(target_win, archive_target, after_archive)
        self._active_anims.append(anim)
        anim.finished.connect(lambda a=anim: self._active_anims.remove(a) if a in self._active_anims else None)

    def _cascade_fill(self, removed_rect):
        """Close the vertical gap left by an archived window: windows in the
        same column (horizontally overlapping it) that sit at or below the gap
        slide up by the gap height. Windows in other columns are untouched, so
        a deliberately-arranged layout is preserved.
        """
        rl, rt = removed_rect.x(), removed_rect.y()
        rr = rl + removed_rect.width()
        rh = removed_rect.height()

        affected = []
        for win in self._windows:
            if not win.isVisible():
                continue
            wl, wr = win.x(), win.x() + win.width()
            x_overlaps = wl < rr and wr > rl
            if x_overlaps and win.y() >= rt:
                affected.append(win)
        if not affected:
            return

        affected.sort(key=lambda w: w.y())
        # Shift the whole below-group up by the first window's offset from the
        # gap top, which closes a flush column exactly and pulls a loose one
        # tidily upward without overshooting.
        delta = affected[0].y() - rt
        if delta <= 0:
            return
        for win in affected:
            target = QPoint(win.x(), max(rt, win.y() - delta))
            anim = animate_slide(win, target)
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
