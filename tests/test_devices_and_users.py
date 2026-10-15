"""
test_devices_and_users.py — Every page works on phones, tablets and laptops; many users at once

Layout checks that need a real browser are run by hand with Playwright (see the PR); these tests keep
the pieces they rely on from being removed: the shared phone/tablet stylesheet on every page, the
home-screen icon, and a loop registry that serves many users and processes without locking errors.
"""

import os
import re
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
                self.assertIn('class="brand-mark"', html)          # the logo in the page header
                self.assertIn('href="icons/logo.svg"', html)       # and in the browser tab
        for icon in ("logo.svg", "app-icon.svg", "icon-192.png", "icon-512.png", "favicon-32.png"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "icons", icon)), icon)

    def test_cockpit_top_bar_stays_pinned_and_condenses(self):
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            html = f.read()
        top = html.index('id="top-chrome"')
        self.assertTrue(top < html.index('class="app-header') < html.index('id="global-impact-bar"')
                        < html.index('<main class="cockpit-workspace">'))
        self.assertIn('src="js/top-chrome.js"', html)
        with open(os.path.join(ROOT, "css", "responsive.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertRegex(css, r"\.top-chrome \{[^}]*position: sticky")
        self.assertIn(".top-chrome.is-condensed", css)

    def test_every_page_has_the_shared_navigation_and_no_stale_copies(self):
        for page in PAGES:
            with open(os.path.join(ROOT, page), encoding="utf-8") as f:
                html = f.read()
            with self.subTest(page=page):
                self.assertIn('<nav class="app-nav">', html)
                self.assertIn('src="js/appnav.js"', html)
        with open(os.path.join(ROOT, "js", "appnav.js"), encoding="utf-8") as f:
            nav = f.read()
        for page in PAGES:
            self.assertIn(f"'{page}'", nav)
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            cockpit = f.read()
        self.assertNotIn("run.app", cockpit)                          # no link to an outside, unvetted app
        self.assertIn('class="more-menu"', cockpit)
        for stale in ("index.prelight.html", "js/app.prelight.js", "css/styles.backup.css"):
            self.assertFalse(os.path.exists(os.path.join(ROOT, stale)), stale)

    def test_accessibility_basics_stay_in_place(self):
        """WCAG 2.1 AA was audited with axe-core (0 violations on all pages, light/dark, desktop/phone);
        these keep its main fixes: AA-contrast accent colours and keyboard access."""
        def contrast(fg, bg):
            def lum(h):
                r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
                f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
            hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)
        for page in PAGES[1:]:
            with open(os.path.join(ROOT, page), encoding="utf-8") as f:
                html = f.read()
            accent = re.search(r"--accent: (#[0-9a-f]{6});", html).group(1)
            dim = re.search(r"--dim: (#[0-9a-f]{6});", html).group(1)
            with self.subTest(page=page):
                self.assertGreaterEqual(contrast(accent, "#ffffff"), 4.5)
                self.assertGreaterEqual(contrast(dim, "#f1f5f9"), 4.5)
        with open(os.path.join(ROOT, "js", "app.js"), encoding="utf-8") as f:
            app = f.read()
        self.assertIn("card.setAttribute('role', 'button')", app)      # case cards work from the keyboard
        with open(os.path.join(ROOT, "js", "appnav.js"), encoding="utf-8") as f:
            self.assertIn("focusableScrollers", f.read())               # scrolling tables reachable by keyboard

    def test_wide_screens_are_an_app_shell_with_independent_panels(self):
        with open(os.path.join(ROOT, "css", "responsive.css"), encoding="utf-8") as f:
            css = f.read()
        shell = css[css.index("@media (min-width: 1151px) {"):]
        shell = shell[:shell.index("\n}\n")]
        self.assertIn("overflow: hidden !important", shell)          # the page itself never scrolls
        for panel in (".case-queue-list", ".cockpit-center-stage", ".cockpit-sidebar-right"):
            self.assertRegex(shell, re.escape(panel) + r" \{[^}]*overflow-y: auto")
        self.assertRegex(shell, r"\.stage-view-tabs \{[^}]*position: sticky")
        self.assertNotIn("max-height: 900px", css)                    # no whole-page scrolling on short laptops

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
