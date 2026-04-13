"""Archive browser dialog with filtering, sorting, and restore/delete actions."""

from datetime import datetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QScrollArea, QWidget, QFrame,
    QSizePolicy,
)

from . import constants
from .models import Database


class ArchiveCard(QFrame):
    """Single archived task card inside the archive viewer."""

    restore_clicked = Signal(int)  # archive_id
    delete_clicked = Signal(int)   # archive_id

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._id = data["id"]
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(f"""
            ArchiveCard {{
                background: {constants.BG_COLOR};
                border: 1px solid {constants.BORDER_COLOR};
                border-radius: 4px;
                padding: 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel(data.get("title", "Untitled"))
        title.setFont(QFont("Sans", 10, QFont.DemiBold))
        title.setStyleSheet(f"color: {constants.TEXT_COLOR}; border: none;")
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_row.addWidget(title)

        restore_btn = QPushButton("Restore")
        restore_btn.setFixedHeight(24)
        restore_btn.setCursor(Qt.PointingHandCursor)
        restore_btn.setStyleSheet(f"""
            QPushButton {{
                background: {constants.ACCENT_COLOR}; color: #fff;
                border: none; border-radius: 3px; padding: 2px 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {constants.ACCENT_COLOR}cc; }}
        """)
        restore_btn.clicked.connect(lambda: self.restore_clicked.emit(self._id))
        title_row.addWidget(restore_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setFixedHeight(24)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #e53935; color: #fff;
                border: none; border-radius: 3px; padding: 2px 10px;
                font-size: 11px;
            }
            QPushButton:hover { background: #c62828; }
        """)
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self._id))
        title_row.addWidget(delete_btn)

        layout.addLayout(title_row)

        # Subtasks preview
        subtasks = data.get("subtasks", [])
        if subtasks:
            preview_items = subtasks[:4]
            for sub in preview_items:
                text = sub if isinstance(sub, str) else sub.get("text", "")
                done = False if isinstance(sub, str) else sub.get("done", False)
                prefix = "✓ " if done else "○ "
                lbl = QLabel(prefix + text)
                lbl.setFont(QFont("Sans", 8))
                lbl.setStyleSheet(f"color: {constants.SUBTITLE_COLOR}; border: none;")
                layout.addWidget(lbl)
            if len(subtasks) > 4:
                more = QLabel(f"  … +{len(subtasks) - 4} more")
                more.setFont(QFont("Sans", 8))
                more.setStyleSheet(f"color: {constants.SUBTITLE_COLOR}; border: none;")
                layout.addWidget(more)

        # Dates
        dates_row = QHBoxLayout()
        created = _format_date(data.get("created_at", ""))
        archived = _format_date(data.get("archived_at", ""))
        date_lbl = QLabel(f"Created: {created}  •  Archived: {archived}")
        date_lbl.setFont(QFont("Sans", 7))
        date_lbl.setStyleSheet(f"color: {constants.SUBTITLE_COLOR}; border: none;")
        dates_row.addWidget(date_lbl)
        dates_row.addStretch()
        layout.addLayout(dates_row)


class ArchiveViewer(QDialog):
    """Modal dialog for browsing, filtering, sorting, restoring archived tasks."""

    task_restored = Signal(int)  # newly-created active task_id

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Task Archives")
        self.setMinimumSize(constants.ARCHIVE_WINDOW_WIDTH, constants.ARCHIVE_WINDOW_HEIGHT)
        self.setStyleSheet(f"background: {constants.ARCHIVE_HEADER_BG};")
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header
        header = QLabel("Archived Tasks")
        header.setFont(QFont("Sans", 14, QFont.Bold))
        header.setStyleSheet(f"color: {constants.TEXT_COLOR};")
        root.addWidget(header)

        # Toolbar: search + sort
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by title or content…")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {constants.BORDER_COLOR};
                border-radius: 4px; padding: 4px 8px;
                background: {constants.INPUT_BG}; color: {constants.TEXT_COLOR};
            }}
        """)
        self._search.textChanged.connect(self._refresh)
        toolbar.addWidget(self._search)

        sort_label = QLabel("Sort:")
        sort_label.setStyleSheet(f"color: {constants.SUBTITLE_COLOR};")
        toolbar.addWidget(sort_label)

        self._sort_combo = QComboBox()
        self._sort_combo.addItems([
            "Archived (newest)", "Archived (oldest)",
            "Created (newest)", "Created (oldest)",
            "Title (A→Z)", "Title (Z→A)",
            "Priority (high→low)", "Priority (low→high)",
        ])
        self._sort_combo.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {constants.BORDER_COLOR};
                border-radius: 4px; padding: 3px 8px;
                background: {constants.INPUT_BG}; color: {constants.TEXT_COLOR};
            }}
        """)
        self._sort_combo.currentIndexChanged.connect(self._refresh)
        toolbar.addWidget(self._sort_combo)

        root.addLayout(toolbar)

        # Scrollable list of archive cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("border: none;")

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll)

        # Footer
        footer = QHBoxLayout()
        self._count_label = QLabel("0 archived tasks")
        self._count_label.setFont(QFont("Sans", 8))
        self._count_label.setStyleSheet(f"color: {constants.SUBTITLE_COLOR};")
        footer.addWidget(self._count_label)
        footer.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {constants.BORDER_COLOR}; color: {constants.TEXT_COLOR};
                border: none; border-radius: 4px; padding: 6px 20px;
            }}
            QPushButton:hover {{ background: {constants.SUBTITLE_COLOR}; }}
        """)
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _refresh(self):
        # Clear list
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Parse sort option
        sort_map = {
            0: ("archived_at", False), 1: ("archived_at", True),
            2: ("created_at", False),  3: ("created_at", True),
            4: ("title", True),        5: ("title", False),
            6: ("priority", False),    7: ("priority", True),
        }
        idx = self._sort_combo.currentIndex()
        sort_by, ascending = sort_map.get(idx, ("archived_at", False))

        filter_text = self._search.text().strip() or None
        tasks = self.db.get_archived_tasks(
            filter_text=filter_text, sort_by=sort_by, ascending=ascending,
        )

        for i, task in enumerate(tasks):
            card = ArchiveCard(task)
            card.restore_clicked.connect(self._on_restore)
            card.delete_clicked.connect(self._on_delete)
            self._list_layout.insertWidget(i, card)

        self._count_label.setText(f"{len(tasks)} archived task{'s' if len(tasks) != 1 else ''}")

    def _on_restore(self, archive_id):
        new_id = self.db.restore_task(archive_id)
        if new_id:
            self.task_restored.emit(new_id)
        self._refresh()

    def _on_delete(self, archive_id):
        self.db.delete_archived(archive_id)
        self._refresh()


def _format_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %Y %H:%M")
    except (ValueError, TypeError):
        return iso_str or "—"
