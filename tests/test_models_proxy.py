"""Non-GUI unit tests for the button-proxy persistence layer.

Runs anywhere (stdlib only) — models.py has no Qt/third-party imports, so
this is the CI-friendly check for the rip feature's storage.
"""

import os
import tempfile
import unittest

from taskmanager.models import Database


class ProxyCrudTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.db = Database(path=os.path.join(self._dir, "test.db"))

    def tearDown(self):
        self.db.close()

    def test_add_and_get(self):
        target = {"uia": {"name": "Save", "automation_id": "save_btn"},
                  "coord": {"abs_x": 100, "abs_y": 200, "rel_x": 10, "rel_y": 20}}
        png = b"\x89PNG\r\n\x1a\n"  # fake bytes; stored verbatim as BLOB
        pid = self.db.add_proxy(
            label="Save", target=target, screenshot=png,
            source_window_title="Notepad", source_window_class="Notepad",
            x=300, y=150,
        )
        rows = self.db.get_all_proxies()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["id"], pid)
        self.assertEqual(r["label"], "Save")
        self.assertEqual(r["screenshot"], png)
        self.assertEqual(r["source_window_title"], "Notepad")
        self.assertEqual(r["x"], 300)
        self.assertEqual(r["y"], 150)
        # target_json round-trips into a dict under "target"
        self.assertEqual(r["target"]["uia"]["name"], "Save")
        self.assertEqual(r["target"]["coord"]["abs_x"], 100)

    def test_null_screenshot_allowed(self):
        pid = self.db.add_proxy(label="x", target={}, screenshot=None)
        r = self.db.get_all_proxies()[0]
        self.assertIsNone(r["screenshot"])
        self.assertEqual(r["target"], {})
        self.db.delete_proxy(pid)
        self.assertEqual(self.db.get_all_proxies(), [])

    def test_update(self):
        pid = self.db.add_proxy(label="a", target={"v": 1})
        self.db.update_proxy(pid, x=999, y=888, label="b",
                             target={"v": 2}, source_window_title="W")
        r = self.db.get_all_proxies()[0]
        self.assertEqual(r["x"], 999)
        self.assertEqual(r["y"], 888)
        self.assertEqual(r["label"], "b")
        self.assertEqual(r["target"]["v"], 2)
        self.assertEqual(r["source_window_title"], "W")

    def test_update_ignores_unknown_fields(self):
        pid = self.db.add_proxy(label="a", target={})
        # should not raise, should not change anything unexpected
        self.db.update_proxy(pid, bogus_field="zzz")
        r = self.db.get_all_proxies()[0]
        self.assertEqual(r["label"], "a")

    def test_malformed_target_json_degrades_to_empty(self):
        pid = self.db.add_proxy(label="a", target={})
        # Corrupt the stored JSON directly, then ensure read doesn't crash.
        self.db._conn.execute(
            "UPDATE button_proxies SET target_json = ? WHERE id = ?",
            ("{not valid json", pid),
        )
        self.db._conn.commit()
        r = self.db.get_all_proxies()[0]
        self.assertEqual(r["target"], {})

    def test_tasks_and_proxies_are_independent(self):
        self.db.add_task("a task")
        self.db.add_proxy(label="a proxy", target={})
        self.assertEqual(len(self.db.get_all_tasks()), 1)
        self.assertEqual(len(self.db.get_all_proxies()), 1)


if __name__ == "__main__":
    unittest.main()
