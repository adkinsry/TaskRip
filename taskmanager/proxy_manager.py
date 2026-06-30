"""Orchestrates ripped-control proxy tiles: the rip flow, persistence,
lifecycle, and re-invocation. Mirrors TaskManager's structure.
"""

from PySide6.QtCore import QObject, Signal, Slot, QPoint, QTimer
from PySide6.QtWidgets import QApplication

from . import constants
from .models import Database
from .proxy_window import ProxyTile
from .rip import RipOverlay, capture_target, invoke_target, HAS_UIA


class ProxyManager(QObject):
    """Creates, tracks, persists, and fires button-proxy tiles."""

    # Surface problems to the UI (e.g. tray): (title, message)
    notify = Signal(str, str)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._tiles: list[ProxyTile] = []
        self._overlay = RipOverlay()
        self._overlay.control_picked.connect(self._on_control_picked)

    # ── Lifecycle ─────────────────────────────────────────────────

    def load_proxies(self):
        for row in self.db.get_all_proxies():
            tile = self._make_tile(row)
            tile.move(row.get("x", 200), row.get("y", 200))
            tile.show()

    def save_all(self):
        for tile in self._tiles:
            x, y = tile.get_position()
            self.db.update_proxy(tile.proxy_id, x=x, y=y)

    def close_all(self):
        self.save_all()
        for tile in self._tiles:
            tile.close()
        self._tiles.clear()

    # ── Rip flow ──────────────────────────────────────────────────

    @Slot()
    def trigger_rip(self):
        """Show the picker overlay (runs on the GUI thread)."""
        self._overlay.start()

    def _on_control_picked(self, point: QPoint):
        # Delay capture slightly so the overlay is fully gone before UI
        # Automation / the screenshot inspects the point.
        QTimer.singleShot(140, lambda p=point: self._capture_and_create(p))

    def _capture_and_create(self, point: QPoint):
        try:
            label, png, target = capture_target(point)
        except Exception as e:
            self.notify.emit("Rip failed", f"Couldn't read the control: {e}")
            return

        if target.get("uia") is None and not HAS_UIA:
            # No accessibility available and we only have raw coordinates.
            # Still allow it, but warn the proxy will be position-fragile.
            self.notify.emit(
                "Ripped (coordinate-only)",
                "Accessibility wasn't available, so this proxy clicks a fixed "
                "screen spot and may break if the source window moves.",
            )

        pos = self._placement_near(point)
        proxy_id = self.db.add_proxy(
            label=label,
            target=target,
            screenshot=png,
            source_window_title=(target.get("coord", {}) or {}).get("window_title", ""),
            source_window_class=(target.get("coord", {}) or {}).get("window_class", ""),
            x=pos.x(), y=pos.y(),
        )
        row = {"id": proxy_id, "label": label, "screenshot": png,
               "target": target, "x": pos.x(), "y": pos.y()}
        tile = self._make_tile(row)
        tile.move(pos)
        tile.show()
        tile.raise_()

    # ── Tile creation / wiring ────────────────────────────────────

    def _make_tile(self, row):
        tile = ProxyTile(
            proxy_id=row["id"],
            label=row.get("label", ""),
            png_bytes=row.get("screenshot"),
        )
        tile.setProperty("_target", row.get("target", {}))
        tile.triggered.connect(self._on_triggered)
        tile.moved.connect(self._on_moved)
        tile.remove_requested.connect(self._on_remove)
        self._tiles.append(tile)
        return tile

    def _on_triggered(self, proxy_id):
        tile = self._find(proxy_id)
        if tile is None:
            return
        target = tile.property("_target") or {}
        ok = False
        try:
            ok = invoke_target(target)
        except Exception:
            ok = False
        if not ok:
            tile.flash_stale()

    def _on_moved(self, proxy_id):
        tile = self._find(proxy_id)
        if tile is None:
            return
        x, y = tile.get_position()
        self.db.update_proxy(proxy_id, x=x, y=y)

    def _on_remove(self, proxy_id):
        tile = self._find(proxy_id)
        if tile is None:
            return
        self.db.delete_proxy(proxy_id)
        self._tiles.remove(tile)
        tile.close()
        tile.deleteLater()

    # ── Helpers ───────────────────────────────────────────────────

    def _find(self, proxy_id):
        for t in self._tiles:
            if t.proxy_id == proxy_id:
                return t
        return None

    def _placement_near(self, point: QPoint):
        """Place the new tile a little down-right of the rip point, clamped to
        the screen so it's always visible."""
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        geom = screen.availableGeometry() if screen else None
        x = point.x() + 12
        y = point.y() + 12
        if geom is not None:
            x = max(geom.left(), min(x, geom.right() - 80))
            y = max(geom.top(), min(y, geom.bottom() - 48))
        return QPoint(x, y)
