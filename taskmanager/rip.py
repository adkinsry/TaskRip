"""Rip a control: pick an on-screen button, capture a re-invokable target,
and later re-trigger the original control.

Two-layer trigger (hybrid), per the approved design:
  1. Windows UI Automation Invoke() on the re-found element (robust, no
     cursor movement, survives the source window moving).
  2. Fallback: a synthesized click at the control's window-anchored
     coordinate, restoring the cursor afterward.

Everything Windows-specific (uiautomation/comtypes) is import-guarded so the
module loads on any platform; the feature simply degrades (UIA path off,
coordinate fallback only where synthetic input is allowed).
"""

import io
import sys

from PySide6.QtCore import Qt, Signal, Slot, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QApplication

from . import constants

# ── Optional dependencies (guarded) ───────────────────────────────
try:
    import uiautomation as _uia
    HAS_UIA = True
except Exception:  # ImportError on non-Windows, or COM init issues
    _uia = None
    HAS_UIA = False

try:
    import mss
    from PIL import Image
    HAS_GRAB = True
except Exception:
    HAS_GRAB = False

try:
    from pynput.mouse import Controller as _MouseController, Button as _MouseButton
    HAS_MOUSE = True
except Exception:
    HAS_MOUSE = False


# ── DPI helpers ───────────────────────────────────────────────────

def _point_logical_to_physical(p: QPoint):
    """Qt logical global point → physical pixels (matches uiautomation/mss)."""
    screen = None
    if QApplication.instance() is not None:
        screen = QApplication.screenAt(p) or QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen is not None else 1.0
    return (round(p.x() * dpr), round(p.y() * dpr))


# ── Selection overlay (single-click control picker) ───────────────

class RipOverlay(QWidget):
    """Full-virtual-desktop dim overlay; a single click picks the control
    under the cursor and emits its global (logical) coordinates."""

    control_picked = Signal(QPoint)  # global logical coordinates
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AcceptTouchEvents)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)

    @Slot()
    def start(self):
        virtual_geom = QRect()
        for screen in QApplication.screens():
            virtual_geom = virtual_geom.united(screen.geometry())
        self.setGeometry(virtual_geom)
        self.setWindowState(Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 70))
        # Instruction banner centred near the top
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setFont(QFont("Sans", 13, QFont.DemiBold))
        text = "Click the control you want to rip   ·   Esc to cancel"
        painter.drawText(self.rect().adjusted(0, 40, 0, 0),
                         Qt.AlignHCenter | Qt.AlignTop, text)
        painter.end()

    def _pick(self, global_pt: QPoint):
        # Hide first so UI Automation / the screenshot sees the real app
        # underneath, not this overlay.
        self.hide()
        self.control_picked.emit(global_pt)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pick(event.globalPosition().toPoint())
        elif event.button() == Qt.RightButton:
            self.hide()
            self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.cancelled.emit()

    def event(self, ev):
        from PySide6.QtCore import QEvent
        if ev.type() == QEvent.TouchEnd:
            pts = ev.points()
            if pts:
                gp = pts[0].globalPosition().toPoint()
                self._pick(gp)
                ev.accept()
                return True
        return super().event(ev)


# ── Capture: build a re-invokable target from a screen point ───────

def capture_target(global_point: QPoint):
    """Return (label, screenshot_png_bytes_or_None, target_dict).

    target_dict = {
        "uia": {name, automation_id, class_name, control_type,
                control_type_name, window_title, window_class} | None,
        "coord": {abs_x, abs_y, rel_x, rel_y, window_title, window_class},
        "bounds": [l, t, r, b] | None,   # physical px, informational
    }
    All coordinates are PHYSICAL pixels.
    """
    px, py = _point_logical_to_physical(global_point)
    label = "control"
    bounds = None
    uia_info = None
    win_left, win_top = None, None

    if HAS_UIA:
        try:
            ctrl = _uia.ControlFromPoint(px, py)
            if ctrl:
                label = _safe(lambda: ctrl.Name) or _safe(lambda: ctrl.ControlTypeName) or "control"
                r = _safe(lambda: ctrl.BoundingRectangle)
                if r is not None:
                    bounds = [r.left, r.top, r.right, r.bottom]
                top = _safe(lambda: ctrl.GetTopLevelControl())
                wtitle = _safe(lambda: top.Name) if top else ""
                wclass = _safe(lambda: top.ClassName) if top else ""
                wr = _safe(lambda: top.BoundingRectangle) if top else None
                if wr is not None:
                    win_left, win_top = wr.left, wr.top
                uia_info = {
                    "name": _safe(lambda: ctrl.Name) or "",
                    "automation_id": _safe(lambda: ctrl.AutomationId) or "",
                    "class_name": _safe(lambda: ctrl.ClassName) or "",
                    "control_type": _safe(lambda: int(ctrl.ControlType)) or 0,
                    "control_type_name": _safe(lambda: ctrl.ControlTypeName) or "",
                    "window_title": wtitle or "",
                    "window_class": wclass or "",
                }
        except Exception as e:
            print(f"[rip] UIA capture failed: {e}", file=sys.stderr)

    coord = {
        "abs_x": px, "abs_y": py,
        "rel_x": (px - win_left) if win_left is not None else px,
        "rel_y": (py - win_top) if win_top is not None else py,
        "window_title": uia_info["window_title"] if uia_info else "",
        "window_class": uia_info["window_class"] if uia_info else "",
    }

    target = {"uia": uia_info, "coord": coord, "bounds": bounds}
    label = (label or "control").strip()[:40] or "control"
    png = _grab_png(bounds, px, py)
    return label, png, target


def _grab_png(bounds, px, py):
    """Screenshot the control's bounds (physical px) as PNG bytes for the
    proxy tile's face. Falls back to a small box around the click point."""
    if not HAS_GRAB:
        return None
    if (bounds and (bounds[2] - bounds[0]) >= 4 and (bounds[3] - bounds[1]) >= 4
            and (bounds[2] - bounds[0]) <= 1400 and (bounds[3] - bounds[1]) <= 1400):
        left, top, right, bottom = bounds
    else:
        w, h = 96, 44
        left, top, right, bottom = px - w // 2, py - h // 2, px + w // 2, py + h // 2
    mon = {"left": int(left), "top": int(top),
           "width": max(1, int(right - left)), "height": max(1, int(bottom - top))}
    try:
        with mss.mss() as sct:
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        max_w = 240
        if img.width > max_w:
            ratio = max_w / img.width
            img = img.resize((max_w, max(1, int(img.height * ratio))))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"[rip] screenshot failed: {e}", file=sys.stderr)
        return None


# ── Invoke: re-trigger the original control ───────────────────────

def invoke_target(target: dict) -> bool:
    """Re-trigger the ripped control. Returns True on success."""
    if not isinstance(target, dict):
        return False

    # 1) UI Automation Invoke (robust, no cursor movement)
    uia_info = target.get("uia")
    if HAS_UIA and uia_info:
        try:
            if _uia_invoke(uia_info):
                return True
        except Exception as e:
            print(f"[rip] UIA invoke failed: {e}", file=sys.stderr)

    # 2) Coordinate-click fallback
    coord = target.get("coord")
    if coord:
        try:
            if _coord_click(coord):
                return True
        except Exception as e:
            print(f"[rip] coordinate click failed: {e}", file=sys.stderr)

    return False


def _uia_invoke(uia_info: dict) -> bool:
    if not HAS_UIA:
        return False
    ctrl = _find_control(uia_info)
    if ctrl is None:
        return False
    # Prefer patterns that fire without moving the cursor.
    for getter, action in (
        ("GetInvokePattern", "Invoke"),
        ("GetTogglePattern", "Toggle"),
        ("GetLegacyIAccessiblePattern", "DoDefaultAction"),
    ):
        fn = getattr(ctrl, getter, None)
        if fn is None:
            continue
        try:
            pat = fn()
        except Exception:
            pat = None
        if not pat:
            continue
        act = getattr(pat, action, None)
        if act is None:
            continue
        try:
            act()
            return True
        except Exception:
            continue
    # Last resort within UIA: a real click on the element (no cursor pre-move).
    try:
        ctrl.Click(simulateMove=False)
        return True
    except Exception:
        return False


def _find_control(uia_info: dict):
    """Re-find the element: locate its top-level window, then search for the
    control by AutomationId / Name / ControlType. Returns a live control or
    None."""
    wtitle = uia_info.get("window_title") or ""
    wclass = uia_info.get("window_class") or ""

    scope = None
    try:
        if wclass and wtitle:
            cand = _uia.WindowControl(searchDepth=1, ClassName=wclass, Name=wtitle)
            scope = cand if cand.Exists(0.5, 0.1) else None
        if scope is None and wtitle:
            cand = _uia.WindowControl(searchDepth=1, Name=wtitle)
            scope = cand if cand.Exists(0.5, 0.1) else None
        if scope is None and wclass:
            cand = _uia.WindowControl(searchDepth=1, ClassName=wclass)
            scope = cand if cand.Exists(0.5, 0.1) else None
    except Exception:
        scope = None
    if scope is None:
        scope = _uia.GetRootControl()

    kwargs = {}
    if uia_info.get("automation_id"):
        kwargs["AutomationId"] = uia_info["automation_id"]
    if uia_info.get("name"):
        kwargs["Name"] = uia_info["name"]
    if uia_info.get("class_name"):
        kwargs["ClassName"] = uia_info["class_name"]
    if uia_info.get("control_type"):
        kwargs["ControlType"] = uia_info["control_type"]
    if not kwargs:
        return None
    try:
        ctrl = scope.Control(searchDepth=0xFFFFFFFF, **kwargs)
        if ctrl.Exists(0.6, 0.1):
            return ctrl
    except Exception:
        pass
    return None


def _coord_click(coord: dict) -> bool:
    if not HAS_MOUSE:
        return False
    x = coord.get("abs_x")
    y = coord.get("abs_y")
    # If we can re-find the source window, anchor by its current top-left so
    # the click survives the window being moved.
    if HAS_UIA and (coord.get("window_title") or coord.get("window_class")):
        win = _refind_window(coord.get("window_title"), coord.get("window_class"))
        if win is not None:
            wr = _safe(lambda: win.BoundingRectangle)
            if wr is not None:
                x = wr.left + coord.get("rel_x", 0)
                y = wr.top + coord.get("rel_y", 0)
    if x is None or y is None:
        return False

    mouse = _MouseController()
    saved = mouse.position
    try:
        mouse.position = (int(x), int(y))
        mouse.press(_MouseButton.left)
        mouse.release(_MouseButton.left)
    finally:
        # Restore the user's cursor so the click is unobtrusive.
        try:
            mouse.position = saved
        except Exception:
            pass
    return True


def _refind_window(wtitle, wclass):
    if not HAS_UIA:
        return None
    try:
        if wclass and wtitle:
            c = _uia.WindowControl(searchDepth=1, ClassName=wclass, Name=wtitle)
            if c.Exists(0.5, 0.1):
                return c
        if wtitle:
            c = _uia.WindowControl(searchDepth=1, Name=wtitle)
            if c.Exists(0.5, 0.1):
                return c
        if wclass:
            c = _uia.WindowControl(searchDepth=1, ClassName=wclass)
            if c.Exists(0.5, 0.1):
                return c
    except Exception:
        pass
    return None


def _safe(fn, default=None):
    """Call a zero-arg lambda, swallowing any UIA/COM error."""
    try:
        return fn()
    except Exception:
        return default
