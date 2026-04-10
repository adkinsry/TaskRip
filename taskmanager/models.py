"""SQLite database layer for task persistence and archival."""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path

from . import constants


def _db_path():
    data_dir = Path.home() / ".local" / "share" / "taskmanager"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / constants.DB_FILENAME)


class Database:
    def __init__(self, path=None):
        self._path = path or _db_path()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                subtasks TEXT NOT NULL DEFAULT '[]',
                x INTEGER NOT NULL DEFAULT 100,
                y INTEGER NOT NULL DEFAULT 100,
                width_units INTEGER NOT NULL DEFAULT 6,
                height_units INTEGER NOT NULL DEFAULT 4,
                priority INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS archived_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                subtasks TEXT NOT NULL DEFAULT '[]',
                priority INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                archived_at TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # ── Active tasks ──────────────────────────────────────────────

    def add_task(self, title, subtasks=None, x=100, y=100,
                 width_units=None, height_units=None, priority=0):
        w = width_units or constants.DEFAULT_WIDTH_UNITS
        h = height_units or constants.DEFAULT_HEIGHT_UNITS
        subs = json.dumps(subtasks or [])
        now = datetime.now().isoformat()
        cur = self._conn.execute(
            "INSERT INTO tasks (title, subtasks, x, y, width_units, height_units, priority, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (title, subs, x, y, w, h, priority, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_task(self, task_id, **fields):
        allowed = {"title", "subtasks", "x", "y", "width_units", "height_units", "priority"}
        parts, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "subtasks":
                v = json.dumps(v)
            parts.append(f"{k} = ?")
            vals.append(v)
        if not parts:
            return
        vals.append(task_id)
        self._conn.execute(
            f"UPDATE tasks SET {', '.join(parts)} WHERE id = ?", vals
        )
        self._conn.commit()

    def get_all_tasks(self):
        rows = self._conn.execute(
            "SELECT * FROM tasks ORDER BY priority DESC, created_at ASC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_task(self, task_id):
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    # ── Archival ──────────────────────────────────────────────────

    def archive_task(self, task_id):
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO archived_tasks (title, subtasks, priority, created_at, archived_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (row["title"], row["subtasks"], row["priority"], row["created_at"], now),
        )
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    def get_archived_tasks(self, filter_text=None, sort_by="archived_at", ascending=False):
        valid_sorts = {"archived_at", "created_at", "title", "priority"}
        if sort_by not in valid_sorts:
            sort_by = "archived_at"
        direction = "ASC" if ascending else "DESC"

        if filter_text:
            rows = self._conn.execute(
                f"SELECT * FROM archived_tasks WHERE title LIKE ? OR subtasks LIKE ?"
                f" ORDER BY {sort_by} {direction}",
                (f"%{filter_text}%", f"%{filter_text}%"),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT * FROM archived_tasks ORDER BY {sort_by} {direction}"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def restore_task(self, archive_id, x=100, y=100):
        row = self._conn.execute(
            "SELECT * FROM archived_tasks WHERE id = ?", (archive_id,)
        ).fetchone()
        if not row:
            return None
        task_id = self.add_task(
            title=row["title"],
            subtasks=json.loads(row["subtasks"]),
            x=x, y=y,
            priority=row["priority"],
        )
        self._conn.execute("DELETE FROM archived_tasks WHERE id = ?", (archive_id,))
        self._conn.commit()
        return task_id

    def delete_archived(self, archive_id):
        self._conn.execute("DELETE FROM archived_tasks WHERE id = ?", (archive_id,))
        self._conn.commit()

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row):
        d = dict(row)
        if "subtasks" in d and isinstance(d["subtasks"], str):
            d["subtasks"] = json.loads(d["subtasks"])
        return d

    def close(self):
        self._conn.close()
