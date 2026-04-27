"""Individual task window — frameless, thin-bordered, draggable, snap-aware.

Supports both mouse and touch input:
- Mouse: drag title bar to move, double-click title to edit, scroll-wheel
  to resize (while holding left button on title bar).
- Touch: single-finger drag on title bar to move, long-press title bar to
  edit title, two-finger pinch anywhere on the window to resize.
"""

from PySide6.QtCore import Qt, Signal, QPoint, QEvent, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QScrollArea, QFrame, QSizePolicy,
)

from . import constants

LONG_PRESS_MS = 600
LONG_PRESS_MOVE_THRESHOLD = 10


class TaskWindow(QWidget):
    """A minimal, frameless task card that can be dragged, resized, and snapped."""

    task_completed = Signal(int)   # task_id
    task_changed = Signal(int)     # task_id (content or geometry changed)
    drag_started = Signal(object)  # self
    drag_finished = Signal(object) # self

    def __init__(self, task_id, title="", subtasks=None, width_units=None,
                 height_units=None, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self._title_text = title
        self._subtasks = subtasks or []
        self._width_units = width_units or constants.DEFAULT_WIDTH_UNITS
        self._height_units = height_units or constants.DEFAULT_HEIGHT_UNITS

        self._dragging = False
        self._drag_offset = QPoint()
        self._resize_mode = False  # True while left-button held on title bar
        self._focused = False

        # Touch state
        self._touch_id = None
        self._touch_dragging = False
        self._touch_start_global = QPoint()
        self._pinch_start_w = self._width_units
        self._pinch_start_h = self._height_units

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.setMouseTracking(True)
        self.grabGesture(Qt.PinchGesture)

        # Long-press timer (touch alternative to double-click for title edit)
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.setInterval(LONG_PRESS_MS)
        self._long_press_timer.timeout.connect(self._on_long_press)

        self._apply_grid_size()
        self._build_ui()

    # ── Size helpers ──────────────────────────────────────────────

    def _apply_grid_size(self):
        w = self._width_units * constants.GRID_UNIT
        h = self._height_units * constants.GRID_UNIT
        self.setFixedSize(w, h)

    def width_units(self):
        return self._width_units

    def height_units(self):
        return self._height_units

    def resize_by_units(self, dw, dh):
        new_w = max(constants.MIN_WIDTH_UNITS, min(constants.MAX_WIDTH_UNITS, self._width_units + dw))
        new_h = max(constants.MIN_HEIGHT_UNITS, min(constants.MAX_HEIGHT_UNITS, self._height_units + dh))
        if new_w != self._width_units or new_h != self._height_units:
            self._width_units = new_w
            self._height_units = new_h
            self._apply_grid_size()
            self.task_changed.emit(self.task_id)

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        # Container inside the border
        container = QFrame(self)
        container.setStyleSheet(f"background: {constants.BG_COLOR}; border: none;")
        inner = QVBoxLayout(container)
        inner.setContentsMargins(6, 0, 6, 6)
        inner.setSpacing(4)

        # ── Title bar ─────────────────────────────────────────────
        title_bar = QFrame()
        title_bar.setFixedHeight(constants.TITLE_BAR_HEIGHT)
        title_bar.setStyleSheet(
            f"background: {constants.TITLE_BG}; border: none; border-radius: 0px;"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(4, 2, 2, 2)
        tb_layout.setSpacing(4)

        self._title_label = QLabel(self._title_text or "New task")
        self._title_label.setFont(QFont("Sans", 9, QFont.DemiBold))
        self._title_label.setStyleSheet(f"color: {constants.TEXT_COLOR};")
        self._title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb_layout.addWidget(self._title_label)

        # Title inline editor (hidden by default)
        self._title_edit = QLineEdit()
        self._title_edit.setFont(QFont("Sans", 9, QFont.DemiBold))
        self._title_edit.setStyleSheet(
            f"color: {constants.TEXT_COLOR}; background: {constants.INPUT_BG}; border: 1px solid {constants.ACCENT_COLOR}; padding: 0 2px;"
        )
        self._title_edit.hide()
        self._title_edit.returnPressed.connect(self._finish_title_edit)
        tb_layout.addWidget(self._title_edit)

        # Done button (24x24 for reasonable touch target within the 28px title bar)
        self._done_btn = QPushButton("✓")
        self._done_btn.setFixedSize(24, 24)
        self._done_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._done_btn.setToolTip("Mark complete and archive")
        self._done_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {constants.SUBTITLE_COLOR};
                border: 1px solid {constants.BORDER_COLOR}; border-radius: 3px;
                font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: {constants.DONE_BUTTON_COLOR}; color: #fff;
                border-color: {constants.DONE_BUTTON_HOVER};
            }}
        """)
        self._done_btn.clicked.connect(lambda: self.task_completed.emit(self.task_id))
        tb_layout.addWidget(self._done_btn)

        inner.addWidget(title_bar)

        # ── Subtasks scroll area ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self._subtask_container = QWidget()
        self._subtask_layout = QVBoxLayout(self._subtask_container)
        self._subtask_layout.setContentsMargins(2, 2, 2, 2)
        self._subtask_layout.setSpacing(2)
        self._subtask_layout.addStretch()

        scroll.setWidget(self._subtask_container)
        inner.addWidget(scroll)

        root.addWidget(container)
        self._populate_subtasks()

    def _populate_subtasks(self):
        # Clear existing (except the stretch at end)
        while self._subtask_layout.count() > 1:
            item = self._subtask_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, sub in enumerate(self._subtasks):
            text = sub if isinstance(sub, str) else sub.get("text", "")
            checked = False if isinstance(sub, str) else sub.get("done", False)
            cb = QCheckBox(text)
            cb.setChecked(checked)
            cb.setFont(QFont("Sans", 8))
            cb.setStyleSheet(f"color: {constants.TEXT_COLOR}; background: transparent;")
            cb.stateChanged.connect(lambda state, idx=i: self._subtask_toggled(idx, state))
            self._subtask_layout.insertWidget(i, cb)

    def _subtask_toggled(self, idx, state):
        if idx < len(self._subtasks):
            if isinstance(self._subtasks[idx], str):
                self._subtasks[idx] = {"text": self._subtasks[idx], "done": bool(state)}
            else:
                self._subtasks[idx]["done"] = bool(state)
            self.task_changed.emit(self.task_id)

    # ── Title editing ─────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        # Double-click on title area → edit title
        if event.position().y() < constants.TITLE_BAR_HEIGHT:
            self._start_title_edit()
        super().mouseDoubleClickEvent(event)

    def _start_title_edit(self):
        self._title_label.hide()
        self._title_edit.setText(self._title_text)
        self._title_edit.show()
        self._title_edit.setFocus()
        self._title_edit.selectAll()

    def _finish_title_edit(self):
        self._title_text = self._title_edit.text().strip() or "New task"
        self._title_label.setText(self._title_text)
        self._title_edit.hide()
        self._title_label.show()
        self.task_changed.emit(self.task_id)

    # ── Mouse drag ───────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < constants.TITLE_BAR_HEIGHT:
            self._dragging = True
            self._resize_mode = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.raise_()
            self.drag_started.emit(self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._resize_mode = False
            self.drag_finished.emit(self)
        super().mouseReleaseEvent(event)

    # ── Scroll-wheel resize (only when left button held on title bar) ─

    def wheelEvent(self, event):
        if self._resize_mode:
            delta = event.angleDelta().y()
            if delta > 0:
                self.resize_by_units(0, -1)  # scroll up → shrink height
            elif delta < 0:
                self.resize_by_units(0, 1)   # scroll down → grow height
            event.accept()
        else:
            super().wheelEvent(event)

    # ── Touch + gesture handling ──────────────────────────────────

    def event(self, event):
        t = event.type()
        if t == QEvent.Gesture:
            return self._gesture_event(event)
        if t in (QEvent.TouchBegin, QEvent.TouchUpdate,
                 QEvent.TouchEnd, QEvent.TouchCancel):
            return self._touch_event(event)
        return super().event(event)

    def _touch_event(self, event):
        points = event.points()
        if not points:
            return False

        # Multi-touch → let the gesture recogniser handle it
        if len(points) > 1:
            return False

        point = points[0]
        t = event.type()

        if t == QEvent.TouchBegin:
            local_y = point.position().y()
            if local_y < constants.TITLE_BAR_HEIGHT:
                self._touch_id = point.id()
                self._touch_dragging = True
                self._touch_start_global = point.globalPosition().toPoint()
                self._drag_offset = self._touch_start_global - self.pos()
                self.raise_()
                self.drag_started.emit(self)
                self._long_press_timer.start()
                event.accept()
                return True
            # Touch outside title bar → let Qt synthesise mouse events
            # so child widgets (checkboxes, done button) work normally.
            return False

        if t == QEvent.TouchUpdate:
            if self._touch_dragging and point.id() == self._touch_id:
                global_pos = point.globalPosition().toPoint()
                moved = (global_pos - self._touch_start_global).manhattanLength()
                if moved > LONG_PRESS_MOVE_THRESHOLD:
                    self._long_press_timer.stop()
                self.move(global_pos - self._drag_offset)
                event.accept()
                return True

        if t == QEvent.TouchEnd:
            if self._touch_dragging and point.id() == self._touch_id:
                self._touch_dragging = False
                self._touch_id = None
                self._long_press_timer.stop()
                self.drag_finished.emit(self)
                event.accept()
                return True

        if t == QEvent.TouchCancel:
            self._touch_dragging = False
            self._touch_id = None
            self._long_press_timer.stop()
            return True

        return False

    def _gesture_event(self, event):
        pinch = event.gesture(Qt.PinchGesture)
        if pinch:
            if pinch.state() == Qt.GestureStarted:
                self._pinch_start_w = self._width_units
                self._pinch_start_h = self._height_units
            elif pinch.state() == Qt.GestureUpdated:
                factor = pinch.totalScaleFactor()
                target_w = round(self._pinch_start_w * factor)
                target_h = round(self._pinch_start_h * factor)
                dw = target_w - self._width_units
                dh = target_h - self._height_units
                if dw != 0 or dh != 0:
                    self.resize_by_units(dw, dh)
            event.accept()
            return True
        return super().event(event)

    def _on_long_press(self):
        """Long-press on title bar → edit title (touch alternative to double-click)."""
        self._touch_dragging = False
        self._touch_id = None
        self._start_title_edit()

    # ── Focus styling ─────────────────────────────────────────────

    def focusInEvent(self, event):
        self._focused = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._focused = False
        self.update()
        if self._title_edit.isVisible():
            self._finish_title_edit()
        super().focusOutEvent(event)

    # ── Paint thin border ─────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        color = constants.BORDER_COLOR_FOCUSED if self._focused else constants.BORDER_COLOR
        pen = QPen(QColor(color), 1)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.end()

    # ── Data accessors ────────────────────────────────────────────

    def get_data(self):
        return {
            "id": self.task_id,
            "title": self._title_text,
            "subtasks": self._subtasks,
            "x": self.x(),
            "y": self.y(),
            "width_units": self._width_units,
            "height_units": self._height_units,
        }

    def set_title(self, text):
        self._title_text = text
        self._title_label.setText(text)

    def set_subtasks(self, subtasks):
        self._subtasks = subtasks
        self._populate_subtasks()
