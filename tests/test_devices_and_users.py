"""
test_devices_and_users.py — Every page works on phones, tablets and laptops; many users at once

Layout checks that need a real browser are run by hand with Playwright (see the PR); these tests keep
the pieces they rely on from being removed: the shared phone/tablet stylesheet on every page, the
home-screen icon, and a loop registry that serves many users and processes without locking errors.
"""

import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.clinloop_engine.loop_store import LoopStore  # noqa: E402

PAGES = ["index.html", "worklist.html", "patient.html", "quality.html", "governance.html", "imaging.html"]


class TestEveryDevice(unittest.TestCase):

    def test_every_page_is_ready_for_phones_and_home_screens(self):
        for page in PAGES:
            with open(os.path.join(ROOT, page), encoding="utf-8") as f:
                html = f.read()
            with self.subTest(page=page):
                self.assertRegex(html, r'<meta name="viewport" content="width=device-width, initial-scale=1')
                self.assertRegex(html, r'href="css/responsive\.css(\?v=\w+)?"')
                self.assertIn('rel="icon"', html)
                self.assertIn('rel="manifest"', html)
                self.assertIn('rel="apple-touch-icon"', html)

    def test_shared_stylesheet_keeps_the_key_fixes(self):
        with open(os.path.join(ROOT, "css", "responsive.css"), encoding="utf-8") as f:
            css = f.read()
        # Tables scroll sideways rather than squeezing columns to one letter
        self.assertIn("overflow-wrap: break-word !important", css)
        # All cockpit tabs reachable at every width
        self.assertRegex(css, r"\.stage-view-tabs \{[^}]*overflow-x: auto")
        # No zoom-on-focus on iPhone/iPad
        self.assertRegex(css, r"@media \(pointer: coarse\) \{[^@]*font-size: 16px")


class TestManyUsers(unittest.TestCase):

    def test_registry_uses_wal_and_waits_instead_of_failing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "clinloop.db")
            store = LoopStore(path)
            self.assertEqual(store._db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertGreaterEqual(store._db.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
            # A second process-like connection can read while the server holds the database
            other = LoopStore(path)
            self.assertEqual(other._db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 0)

    def test_concurrent_audit_writes_keep_the_chain_intact(self):
        store = LoopStore()
        errors = []

        def work(i):
            try:
                for n in range(25):
                    store.record_audit(f"user{i}", "clinician", "view", None, {"n": n})
            except Exception as e:      # pragma: no cover - reported below
                errors.append(e)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(store._db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 500)
        self.assertTrue(store.verify_audit_chain())


if __name__ == "__main__":
    unittest.main()
