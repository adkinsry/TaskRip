"""Floating proxy tile for a ripped control.

A small, frameless, always-on-top widget that shows a thumbnail of the
original control. A tap/click re-fires the original; dragging the tile moves
it. Mirrors TaskWindow's frame/drag/border conventions.
"""

from PySide6.QtCore import Qt, Signal, QPoint, QEvent, QSize
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QFont, QCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from . import constants

# Distance (px) the pointer must move before a press becomes a drag rather
# than a trigger. Below this, releasing fires the control.
DRAG_THRESHOLD = 6

TILE_MIN_W = 56
TILE_MIN_H = 36
TILE_MAX_W = 240
TILE_MAX_H = 160


class ProxyTile(QWidget):
    """A draggable floating button proxy."""

    triggered = Signal(int)         # proxy_id — fire the original control
    moved = Signal(int)             # proxy_id — geometry changed
    remove_requested = Signal(int)  # proxy_id — user deleted the tile

    def __init__(self, proxy_id, label="", png_bytes=None, parent=None):
        super().__init__(parent)
        self.proxy_id = proxy_id
        self._label = label or "control"
        self._stale = False

        self._press_pos = None
        self._dragging = False
        self._drag_offset = QPoint()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip(f"{self._label} — click to activate, drag to move")

        self._pixmap = self._load_pixmap(png_bytes)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────

    def _load_pixmap(self, png_bytes):
        if not png_bytes:
            return None
        pm = QPixmap()
        if pm.loadFromData(png_bytes):
            return pm
        return None

    def _tile_size(self):
        if self._pixmap is not None and not self._pixmap.isNull():
            w = min(TILE_MAX_W, max(TILE_MIN_W, self._pixmap.width() + 8))
            h = min(TILE_MAX_H, max(TILE_MIN_H, self._pixmap.height() + 8))
            return QSize(w, h)
        return QSize(TILE_MIN_W * 2, TILE_MIN_H)

    def _build_ui(self):
        size = self._tile_size()
        self.setFixedSize(size)

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        if self._pixmap is not None and not self._pixmap.isNull():
            self._face = QLabel()
            scaled = self._pixmap
            if scaled.width() > TILE_MAX_W - 8 or scaled.height() > TILE_MAX_H - 8:
                scaled = scaled.scaled(TILE_MAX_W - 8, TILE_MAX_H - 8,
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._face.setPixmap(scaled)
            self._face.setAlignment(Qt.AlignCenter)
        else:
            self._face = QLabel(self._label)
            self._face.setAlignment(Qt.AlignCenter)
            self._face.setFont(QFont("Sans", 9, QFont.DemiBold))
            self._face.setStyleSheet(f"color: {constants.TEXT_COLOR};")
        self._face.setAttribute(Qt.WA_TransparentForMouseEvents)
        root.addWidget(self._face)

        # Small remove (✕) button, top-right, shown on hover via stylesheet
        self._remove_btn = QPushButton("✕", self)
        self._remove_btn.setFixedSize(16, 16)
        self._remove_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._remove_btn.setToolTip("Remove this proxy")
        self._remove_btn.setStyleSheet(
            "QPushButton { background: rgba(0,0,0,0.45); color: #fff;"
            " border: none; border-radius: 8px; font-size: 10px; }"
            " QPushButton:hover { background: #e53935; }"
        )
        self._remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.proxy_id))
        self._remove_btn.move(size.width() - 18, 2)

    # ── Stale state ───────────────────────────────────────────────

    def set_stale(self, stale: bool):
        if stale != self._stale:
            self._stale = stale
            tip = (f"{self._label} — couldn't reach the original control; "
                   f"remove and re-rip it") if stale else \
                  f"{self._label} — click to activate, drag to move"
            self.setToolTip(tip)
            self.update()

    def flash_stale(self):
        """Mark stale (called when an invoke fails)."""
        self.set_stale(True)

    # ── Border paint ──────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(constants.BG_COLOR))
        color = "#e53935" if self._stale else constants.BORDER_COLOR
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(QColor(color), 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.end()

    # ── Mouse: click-vs-drag ──────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._dragging = False
            self._drag_offset = self._press_pos - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and event.buttons() & Qt.LeftButton:
            gp = event.globalPosition().toPoint()
            if not self._dragging:
                if (gp - self._press_pos).manhattanLength() > DRAG_THRESHOLD:
                    self._dragging = True
                    self.raise_()
            if self._dragging:
                self.move(gp - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._press_pos is not None:
            was_drag = self._dragging
            self._press_pos = None
            self._dragging = False
            if was_drag:
                self.moved.emit(self.proxy_id)
            else:
                # Clear stale on a fresh attempt so the user gets feedback.
                self.set_stale(False)
                self.triggered.emit(self.proxy_id)
        super().mouseReleaseEvent(event)

    # ── Touch: tap = trigger, drag = move ─────────────────────────

    def event(self, ev):
        t = ev.type()
        if t in (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd):
            return self._touch_event(ev)
        return super().event(ev)

    def _touch_event(self, ev):
        pts = ev.points()
        if not pts:
            return False
        p = pts[0]
        if ev.type() == QEvent.TouchBegin:
            self._press_pos = p.globalPosition().toPoint()
            self._dragging = False
            self._drag_offset = self._press_pos - self.pos()
            ev.accept()
            return True
        if ev.type() == QEvent.TouchUpdate and self._press_pos is not None:
            gp = p.globalPosition().toPoint()
            if not self._dragging and (gp - self._press_pos).manhattanLength() > DRAG_THRESHOLD:
                self._dragging = True
                self.raise_()
            if self._dragging:
                self.move(gp - self._drag_offset)
            ev.accept()
            return True
        if ev.type() == QEvent.TouchEnd and self._press_pos is not None:
            was_drag = self._dragging
            self._press_pos = None
            self._dragging = False
            if was_drag:
                self.moved.emit(self.proxy_id)
            else:
                self.set_stale(False)
                self.triggered.emit(self.proxy_id)
            ev.accept()
            return True
        return False

    # ── Data ──────────────────────────────────────────────────────

    def get_position(self):
        return self.x(), self.y()
