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


if __name__ == "__main__":
    unittest.main()
