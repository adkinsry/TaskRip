"""Hotkey listener + screen region selection overlay + OCR pipeline."""

import os
import sys

from PySide6.QtCore import Qt, Signal, Slot, QRect, QPoint, QObject, QEvent
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget, QApplication

from . import constants

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
    # When running from a PyInstaller bundle, use the bundled tesseract binary
    # and point Tesseract at the bundled language data. Without TESSDATA_PREFIX
    # the bundled tesseract.exe cannot find eng.traineddata and OCR fails with
    # "Failed loading language 'eng'".
    _bundle_dir = getattr(sys, "_MEIPASS", None)
    if _bundle_dir:
        _bundled_tess = os.path.join(_bundle_dir, "tesseract", "tesseract.exe")
        if os.path.isfile(_bundled_tess):
            pytesseract.pytesseract.tesseract_cmd = _bundled_tess
        _bundled_tessdata = os.path.join(_bundle_dir, "tesseract", "tessdata")
        if os.path.isdir(_bundled_tessdata):
            os.environ["TESSDATA_PREFIX"] = _bundled_tessdata
except ImportError:
    HAS_OCR = False

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from pynput import keyboard
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False


class SelectionOverlay(QWidget):
    """Full-screen translucent overlay for rubber-band region selection."""

    region_selected = Signal(QRect)  # screen-coordinates rectangle
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        # A plain frameless top-level window (NOT Qt.Tool): tool windows do
        # not reliably take keyboard/mouse focus on Windows, which left the
        # overlay visible but inert ("does nothing"). A normal window
        # activates and receives input.
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)

        self._origin = QPoint()
        self._current = QPoint()
        self._selecting = False
        self._touch_id = None

    @Slot()
    def start(self):
        """Show the overlay covering all screens and grab input."""
        # Cover the virtual desktop (all monitors). Use show(), NOT
        # showFullScreen() — fullscreen clamps to one monitor and breaks
        # multi-display region selection.
        virtual_geom = QRect()
        for screen in QApplication.screens():
            virtual_geom = virtual_geom.united(screen.geometry())
        self._selecting = False
        self._origin = QPoint()
        self._current = QPoint()
        self.setGeometry(virtual_geom)
        self.setWindowState(Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        # Explicitly take focus so mouse drags and the Escape key register
        # even when another app was foreground when the hotkey fired.
        self.setFocus(Qt.OtherFocusReason)

    def paintEvent(self, event):
        painter = QPainter(self)
        dim = QColor(0, 0, 0, 80)
        full = self.rect()

        if self._selecting:
            # Dim everything OUTSIDE the selection by painting four bands
            # around it, leaving the selection itself unpainted (fully
            # transparent) so the live screen shows through. This avoids
            # CompositionMode_Clear, which renders unreliably (often opaque
            # black) on the Windows compositor.
            sel = QRect(self._origin, self._current).normalized().intersected(full)
            # top band
            painter.fillRect(full.left(), full.top(),
                             full.width(), sel.top() - full.top(), dim)
            # bottom band
            painter.fillRect(full.left(), sel.bottom() + 1,
                             full.width(), full.bottom() - sel.bottom(), dim)
            # left band (selection height only)
            painter.fillRect(full.left(), sel.top(),
                             sel.left() - full.left(), sel.height(), dim)
            # right band (selection height only)
            painter.fillRect(sel.right() + 1, sel.top(),
                             full.right() - sel.right(), sel.height(), dim)
            # Accent border around the selection
            pen = QPen(QColor(constants.ACCENT_COLOR), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(sel)
        else:
            painter.fillRect(full, dim)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self._selecting = True

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._selecting:
            self._selecting = False
            rect = QRect(self._origin, self._current).normalized()
            self.hide()
            if rect.width() > 10 and rect.height() > 10:
                # Convert to global screen coordinates
                global_rect = QRect(
                    self.mapToGlobal(rect.topLeft()),
                    rect.size(),
                )
                self.region_selected.emit(global_rect)
            else:
                self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._selecting = False
            self.hide()
            self.cancelled.emit()

    # ── Touch input (region selection via finger) ─────────────────

    def event(self, event):
        t = event.type()
        if t in (QEvent.TouchBegin, QEvent.TouchUpdate,
                 QEvent.TouchEnd, QEvent.TouchCancel):
            return self._touch_event(event)
        return super().event(event)

    def _touch_event(self, event):
        points = event.points()
        if not points:
            return False
        point = points[0]
        t = event.type()

        if t == QEvent.TouchBegin:
            self._touch_id = point.id()
            self._origin = point.position().toPoint()
            self._current = self._origin
            self._selecting = True
            event.accept()
            return True

        if t == QEvent.TouchUpdate:
            if point.id() == self._touch_id and self._selecting:
                self._current = point.position().toPoint()
                self.update()
                event.accept()
                return True

        if t == QEvent.TouchEnd:
            if point.id() == self._touch_id and self._selecting:
                self._selecting = False
                self._touch_id = None
                rect = QRect(self._origin, self._current).normalized()
                self.hide()
                if rect.width() > 10 and rect.height() > 10:
                    global_rect = QRect(
                        self.mapToGlobal(rect.topLeft()),
                        rect.size(),
                    )
                    self.region_selected.emit(global_rect)
                else:
                    self.cancelled.emit()
                event.accept()
                return True

        if t == QEvent.TouchCancel:
            self._selecting = False
            self._touch_id = None
            self.hide()
            self.cancelled.emit()
            return True

        return False


class CaptureManager(QObject):
    """Manages global hotkey and screen-to-text capture pipeline."""

    task_captured = Signal(str, list)  # (title, subtasks)
    hotkey_failed = Signal(str)        # human-readable reason
    # Emitted from the pynput listener thread; connected with a queued
    # connection so SelectionOverlay.start() runs on the Qt main thread.
    _hotkey_pressed = Signal()

    def __init__(self, hotkey=None, parent=None):
        super().__init__(parent)
        self._overlay = SelectionOverlay()
        self._overlay.region_selected.connect(self._on_region_selected)
        self._hotkey_pressed.connect(self._overlay.start, Qt.QueuedConnection)
        self._hotkey_listener = None
        self._hotkey = hotkey or constants.DEFAULT_HOTKEY

    def start(self):
        """Begin listening for the global hotkey."""
        self._start_listener(self._hotkey)

    def update_hotkey(self, new_hotkey):
        """Change the hotkey at runtime."""
        self.stop()
        self._hotkey = new_hotkey
        self._start_listener(new_hotkey)

    def _start_listener(self, hotkey_str):
        if not HAS_PYNPUT:
            msg = "pynput not available — capture hotkey disabled"
            print(f"[capture] {msg}")
            self.hotkey_failed.emit(msg)
            return False
        # Defensively tear down any existing listener so repeated calls don't
        # leak threads.
        self.stop()
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys({
                hotkey_str: self._on_hotkey,
            })
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            return True
        except Exception as e:
            msg = f"Couldn't register hotkey '{hotkey_str}': {e}"
            print(f"[capture] {msg}", file=sys.stderr)
            self.hotkey_failed.emit(msg)
            return False

    def stop(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None

    def trigger_capture(self):
        """Programmatic trigger (from menu, etc.) — runs on main thread."""
        self._overlay.start()

    def _on_hotkey(self):
        """Called when the global hotkey is pressed (from pynput thread)."""
        # Emitting a signal is thread-safe; the connection is queued so
        # start() runs on the main (GUI) thread.
        self._hotkey_pressed.emit()

    def _on_region_selected(self, rect: QRect):
        """Capture the screen region and run OCR."""
        text = self._capture_and_ocr(rect)
        if text.strip():
            lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
            title = lines[0] if lines else "Captured task"
            subtasks = lines[1:] if len(lines) > 1 else []
            self.task_captured.emit(title, subtasks)

    def _physical_monitor(self, rect: QRect):
        """Map a logical (Qt) global rect to a physical-pixel mss monitor dict.

        Qt reports logical coordinates; mss screenshots in physical pixels.
        On a scaled display (e.g. Windows at 150%) the two differ by the
        screen's device-pixel ratio, so without this conversion mss grabs an
        offset, wrong-sized region — the root cause of OCR reading the wrong
        area. This handles the common single-monitor and uniform-scaling
        multi-monitor cases correctly.
        """
        app = QApplication.instance()
        screen = None
        if app is not None:
            screen = QApplication.screenAt(rect.center()) or QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0

        mon = {
            "left": round(rect.x() * dpr),
            "top": round(rect.y() * dpr),
            "width": max(1, round(rect.width() * dpr)),
            "height": max(1, round(rect.height() * dpr)),
        }
        return mon

    def _capture_and_ocr(self, rect: QRect):
        """Screenshot the given screen rect and run Tesseract OCR."""
        if not HAS_MSS or not HAS_OCR:
            print("[capture] OCR unavailable — install pytesseract, Pillow, and mss", file=sys.stderr)
            return ""

        try:
            with mss.mss() as sct:
                monitor = self._physical_monitor(rect)
                # Clamp to the full virtual-screen bounds so an off-screen or
                # partially out-of-bounds selection can't make mss raise.
                virtual = sct.monitors[0]
                left = max(virtual["left"], monitor["left"])
                top = max(virtual["top"], monitor["top"])
                right = min(virtual["left"] + virtual["width"], monitor["left"] + monitor["width"])
                bottom = min(virtual["top"] + virtual["height"], monitor["top"] + monitor["height"])
                if right - left < 1 or bottom - top < 1:
                    print("[capture] selection outside screen bounds", file=sys.stderr)
                    return ""
                monitor = {"left": left, "top": top,
                           "width": right - left, "height": bottom - top}
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                text = pytesseract.image_to_string(img)
                return text
        except Exception as e:
            print(f"[capture] OCR error: {e}", file=sys.stderr)
            return ""
