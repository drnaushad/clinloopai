"""
test_static_demo.py — The public website's read-only demo (demo/api/, js/demo.js)

The website has no server: js/demo.js answers the pages' requests from demo/api/<hash>.json, written by
scripts/build_static_demo.py. Both sides must hash a request the same way, and the snapshot must hold
everything the pages ask for.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from build_static_demo import fnv1a, request_key  # noqa: E402

API = os.path.join(ROOT, "demo", "api")


class TestStaticDemo(unittest.TestCase):

    def test_request_keys_and_hashes(self):
        self.assertEqual(request_key("/api/v1/worklist", {"include_inactive": "false"}),
                         "/api/v1/worklist?include_inactive=false")
        self.assertEqual(request_key("/api/v1/x", {"b": "2", "a": "1", "c": ""}), "/api/v1/x?a=1&b=2")
        self.assertEqual(fnv1a(""), "811c9dc5")
        self.assertEqual(fnv1a("a"), "e40c292c")                      # FNV-1a reference values

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_browser_hash_matches(self):
        src = open(os.path.join(ROOT, "js", "demo.js"), encoding="utf-8").read()
        body = src[src.index("function fnv1a"):src.index("function reply")]
        keys = ["/api/v1/loops/RP-01|R003|DiagnosticReport/RAD-01:radiology_report/audit",
                "/api/v1/worklist?include_inactive=false", "/api/v1/patients/환자-1/graph"]
        js = body + "\nconsole.log(JSON.stringify(" + json.dumps(keys) + ".map(fnv1a)));"
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [fnv1a(k) for k in keys])

    @unittest.skipUnless(os.path.exists(os.path.join(API, "index.json")), "snapshot not built")
    def test_practice_mode_follows_the_server_rules(self):
        """Practice mode (public site): actions are answered in the browser with the server's rules and kept
        only in that browser. Run in Node against a small fake snapshot."""
        if not shutil.which("node"):
            self.skipTest("node not installed")
        src = open(os.path.join(ROOT, "js", "demo.js"), encoding="utf-8").read()
        layer = src[src.index("  function practiceLayer("):src.index("  // ── banner, sign-in, patient list")]
        js = layer + r"""
const store = {}; globalThis.window = { localStorage: { getItem: k => store[k] || null,
  setItem: (k, v) => { store[k] = v; }, removeItem: k => { delete store[k]; } } };
const loops = [{loop_key: 'P1|R017|x', rule_id: 'R017', workflow_state: 'new', owner: 'unassigned', rule_signoff: 'pending'}];
const snap = (path) => Promise.resolve(path === '/api/v1/worklist' ? {status: 200, body: {loops, count: 1}}
  : path.endsWith('/audit') ? {status: 200, body: {audit: []}} : {status: 404, body: {}});
const reply = (status, body) => Promise.resolve({status, body});
(async () => {
  let P = practiceLayer(snap, reply); const out = [];
  const go = async (m, p, b, q) => { const r = await P.handle(m, p, q || {}, b); return r ? [r.status, r.body] : null; };
  out.push((await go('GET', '/api/v1/me'))[1].role);
  out.push((await go('POST', '/api/v1/loops/P1|R017|x/close', {evidence: ''}))[0]);           // evidence required
  out.push((await go('POST', '/api/v1/loops/P1|R017|x/defer', {reason_code: 'not_clinically_indicated'}))[0]);
  out.push((await go('POST', '/api/v1/loops/P1|R017|x/acknowledge'))[1].workflow_state);
  out.push((await go('POST', '/api/v1/loops/P1|R017|x/acknowledge'))[0]);                    // not twice
  out.push((await go('POST', '/api/v1/loops/P1|R017|x/assign', {owner: 'someone.else'}))[0]); // staff only
  out.push((await go('POST', '/api/v1/loops/P1|R017|x/close', {evidence: 'Colonoscopy 2026-08-01'}))[1].workflow_state);
  out.push((await go('GET', '/api/v1/worklist', null, {include_inactive: 'false'}))[1].count);
  out.push((await go('GET', '/api/v1/loops/P1|R017|x/audit'))[1].audit.map(a => a.action).join(','));
  const sid = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';
  out.push((await go('POST', '/api/v1/quality/second-reader/suggestions/' + sid + '/review', {verdict: 'real_miss', urgent: true}))[0]);
  out.push((await go('POST', '/api/v1/fhir/ingest', {})) === null);                            // not practised: refused upstream
  P = practiceLayer(snap, reply);                                                              // reload keeps changes
  out.push((await go('GET', '/api/v1/worklist', null, {include_inactive: 'false'}))[1].count);
  P.reset(); P = practiceLayer(snap, reply);
  out.push((await go('GET', '/api/v1/worklist', null, {include_inactive: 'false'}))[1].count);
  console.log(JSON.stringify(out));
})();"""
        out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout), ["clinician", 422, 422, "acknowledged", 409, 422, "closed_by_clinician",
                                                  0, "acknowledge,close", 409, True, 0, 1])

    def test_snapshot_covers_what_the_pages_ask_for(self):
        def load(path, query=None):
            with open(os.path.join(API, fnv1a(request_key(path, query)) + ".json"), encoding="utf-8") as f:
                return json.load(f)
        self.assertEqual(load("/api/v1/me")["role"], "viewer")
        loops = load("/api/v1/worklist", {"include_inactive": "false"})["loops"]
        self.assertTrue(loops)
        for loop in loops:
            load(f"/api/v1/loops/{loop['loop_key']}/audit")
            load(f"/api/v1/patients/{loop['patient_id']}/graph")
        for path in ("/api/v1/metrics/breakdowns", "/api/v1/governance/rules", "/api/v1/imaging/models"):
            load(path)
        index = json.load(open(os.path.join(API, "index.json"), encoding="utf-8"))
        self.assertIn("synthetic", index["note"])

    def test_every_fixed_request_a_page_makes_is_in_the_snapshot(self):
        """Device check, Oct 2026: Quality and Rule sign-off asked for three endpoints the snapshot lacked.
        A role-limited endpoint is stored as its refusal, so the page gets the same 403 as from a server."""
        import glob
        import re
        paths = set()
        for page in glob.glob(os.path.join(ROOT, "*.html")):
            paths |= set(re.findall(r"api\('(/api/v1/[^'$?]+)'\)", open(page, encoding="utf-8").read()))
        self.assertGreaterEqual(len(paths), 8)
        for path in sorted(paths):
            self.assertTrue(os.path.exists(os.path.join(API, fnv1a(request_key(path, None)) + ".json")), path)
        with open(os.path.join(API, fnv1a(request_key("/api/v1/quality/documentation-audit", None)) + ".json"),
                  encoding="utf-8") as f:
            self.assertEqual(json.load(f)["__status"], 403)


if __name__ == "__main__":
    unittest.main()
