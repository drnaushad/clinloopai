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

PAGES = ["index.html", "worklist.html", "patient.html", "quality.html", "governance.html", "imaging.html", "pilot.html"]


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

    def test_cockpit_top_bar_never_changes_the_layout_while_scrolling(self):
        # Phones and tablets: the top bar scrolls away and a fixed slim bar slides in. A bar that shrank
        # on scroll moved the page under the reader's finger and flickered (seen on a phone recording).
        with open(os.path.join(ROOT, "index.html"), encoding="utf-8") as f:
            html = f.read()
        top = html.index('id="top-chrome"')
        self.assertTrue(top < html.index('class="app-header') < html.index('id="global-impact-bar"')
                        < html.index('id="mini-bar"') < html.index('<main class="cockpit-workspace">'))
        self.assertIn('src="js/top-chrome.js', html)
        with open(os.path.join(ROOT, "css", "responsive.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertNotIn("is-condensed", css)
        self.assertRegex(css, r"\.mini-bar \{ position: fixed;[^}]*transform: translateY")
        self.assertIn("backdrop-filter: none !important", css)
        with open(os.path.join(ROOT, "js", "top-chrome.js"), encoding="utf-8") as f:
            js = f.read()
        self.assertIn("IntersectionObserver", js)
        self.assertNotIn("addEventListener('scroll'", js)
        # First paint: fonts are linked from the page, not chained through an @import in the stylesheet
        with open(os.path.join(ROOT, "css", "styles.css"), encoding="utf-8") as f:
            self.assertNotIn("@import url", f.read())
        self.assertIn('rel="preconnect" href="https://fonts.gstatic.com" crossorigin', html)

    def test_many_people_at_once_in_the_browser(self):
        """Dialogs close by Escape/✕/outside click; one sign-in per tab with sign-out; the worklist
        refreshes itself (never mid-typing), offers real staff when assigning, and explains conflicts."""
        read = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()
        app, nav, wl, css = read("js", "app.js"), read("js", "appnav.js"), read("worklist.html"), read("css", "styles.css")
        self.assertIn("setupDialogs()", app)
        self.assertIn("e.key === 'Escape'", app)
        self.assertRegex(css, r"\.modal-overlay \{[^}]*visibility: hidden")
        self.assertIn("btn-signout", nav)
        self.assertIn("form.requestSubmit()", nav)
        self.assertIn("setInterval(() => { if (state.user && !busy()) refresh(); }, 30000)", wl)
        self.assertIn("/api/v1/users", wl)
        self.assertIn("Someone else changed this loop first", wl)
        for page in ("worklist.html", "patient.html", "quality.html", "governance.html", "imaging.html", "pilot.html"):
            self.assertNotIn("throw new Error(body.detail ||", read(page), page)   # FastAPI lists → readable text

    def test_plain_professional_wording_and_no_overclaims(self):
        """Search title without marketing words; nothing claims a privacy layer, certification or
        model that is not built; the charter states what has not been shown."""
        read = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()
        html, app = read("index.html"), read("js", "app.js")
        self.assertIn("<title>ClinLoop AI | Closed-Loop Follow-up of Clinical Results</title>", html)
        self.assertIn('rel="canonical" href="https://clinloopai.app/"', html)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "favicon.ico")))
        for phrase in ("Noble", "Nobility", "Hippocratic", "Causal Reasoning", "DTH-Hybrid", "ISO 29101", "8/8",
                       "Re-ID Risk", "Safe for Claude", "Empathy", "Pre-Market", "Explainable AI Audit Trail",
                       "Exponential Hazard", "Autonomous Life-Saving"):
            self.assertNotIn(phrase, html + app, phrase)
        privacy = html[html.index('id="view-privacy"'):html.index("end view-privacy")]
        self.assertNotIn("✅ Active", privacy)
        self.assertIn("Not built", privacy)
        self.assertIn("What has not been shown yet", html)
        self.assertIn('class="status-strip"', html)

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
