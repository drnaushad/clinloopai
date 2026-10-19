"""
The "Analyse patient" page (analyse.html).

On the public website it runs the engine in the browser (Pyodide) from the files listed in
js/engine_manifest.json and src/clinloop_engine/browser_analyse.py; on a hospital's server it posts the
bundle to POST /api/v1/fhir/ingest (admin). These tests keep the manifest in sync with the engine, run the
browser's Python call path in CPython on the example bundles and on a pasted report (the bundle the page
builds in JavaScript, mirrored here), and check the server path and the page's safety wording.
"""

import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from src.clinloop_engine.browser_analyse import analyse_bundle, analyse_json  # noqa: E402

TOKENS = {
    "admin": "test-admin-token-0123456789",
    "clinician": "test-clinician-token-012345",
    "navigator": "test-navigator-token-01234",
    "viewer": "test-viewer-token-0123456789",
}
os.environ["CLINLOOP_API_TOKENS"] = ",".join(f"{t}:{role}.user:{role}" for role, t in TOKENS.items())

EXAMPLES = {"lung-nodule": ("R003", "open"), "positive-fit": ("R017", "open"), "warfarin-inr": ("R007", "closed")}
EVAL = "2026-09-01T00:00:00"
NODULE = "9 mm solid nodule in the right upper lobe. Recommend follow-up CT in 3 months."


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def paste_bundle(kind, title, date, text):
    """Mirror of pasteBundle() in analyse.html."""
    category = "PAT" if kind == "PAT" else "RAD"
    return {
        "resourceType": "Bundle", "type": "collection",
        "meta": {"tag": [{"code": "synthetic", "display": "Pasted report"}]},
        "entry": [
            {"fullUrl": "urn:uuid:Patient-PASTE-1", "resource": {"resourceType": "Patient", "id": "PASTE-1"}},
            {"fullUrl": "urn:uuid:DiagnosticReport-PASTE-REPORT-1", "resource": {
                "resourceType": "DiagnosticReport", "id": "PASTE-REPORT-1", "status": "final",
                "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v2-0074", "code": category}]}],
                "code": {"text": title}, "subject": {"reference": "Patient/PASTE-1"},
                "effectiveDateTime": date, "issued": date, "conclusion": text,
            }},
        ],
    }


def example(name):
    return json.loads(read("demo", "examples", f"{name}.json"))


class TestEngineManifest(unittest.TestCase):

    def setUp(self):
        self.manifest = json.loads(read("js", "engine_manifest.json"))

    def test_manifest_is_up_to_date_and_every_file_exists(self):
        import build_engine_manifest
        self.assertEqual(self.manifest, build_engine_manifest.build(),
                         "run: python scripts/build_engine_manifest.py")
        for f in self.manifest["files"]:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, f)), f)
        self.assertEqual(self.manifest["entry"], "src.clinloop_engine.browser_analyse")

    def test_manifest_covers_every_module_the_analysis_imports(self):
        """Run the browser's call path in a fresh interpreter, with the server-only packages made
        unimportable, on every example and a pasted report: each engine module it loads is listed."""
        bundles = [example(n) for n in EXAMPLES] + [paste_bundle("RAD", "CT chest", "2026-03-01", NODULE),
                                                    paste_bundle("PAT", "Skin biopsy", "2026-03-01", "Melanoma.")]
        code = (
            "import json, sys\n"
            "for m in ('fastapi', 'starlette', 'pydantic', 'requests', 'pandas', 'scipy', 'sklearn', 'matplotlib',"
            " 'PIL', 'torch', 'pydicom', 'httpx', 'uvicorn'):\n"
            "    sys.modules[m] = None\n"
            "from src.clinloop_engine.browser_analyse import analyse_json\n"
            "for b in json.load(sys.stdin):\n"
            "    analyse_json(json.dumps(b), '2026-09-01T00:00:00')\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.startswith('src.clinloop_engine.'))))\n")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, input=json.dumps(bundles),
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        listed = {f[:-3].replace("/", ".") for f in self.manifest["files"] if f.endswith(".py")}
        for mod in json.loads(out.stdout):
            self.assertIn(mod, listed)
        self.assertIn("src/clinloop_engine/config/critical_findings.json", self.manifest["files"])

    def test_github_pages_serves_the_engine_files(self):
        # Jekyll would drop __init__.py (a leading underscore); .nojekyll serves the site as it is
        self.assertTrue(os.path.isfile(os.path.join(ROOT, ".nojekyll")))
        ignored = read(".gitignore")
        for pattern in ("src/", "js/", "demo/", "*.py", "*.json"):
            self.assertNotIn("\n" + pattern + "\n", "\n" + ignored + "\n")


class TestBrowserCallPath(unittest.TestCase):

    def test_examples_give_the_expected_loops(self):
        for name, (rule, status) in EXAMPLES.items():
            with self.subTest(example=name):
                bundle = example(name)
                self.assertEqual(bundle["resourceType"], "Bundle")
                self.assertIn("synthetic", json.dumps(bundle["meta"]).lower())
                r = analyse_bundle(bundle, EVAL)
                self.assertIn((rule, status), [(d["rule_id"], d["status"]) for d in r["detections"]])
                self.assertEqual(r["evaluation_time"], EVAL)

    def test_pasted_nodule_report_opens_a_loop_with_its_basis(self):
        r = json.loads(analyse_json(json.dumps(paste_bundle("RAD", "CT chest", "2026-03-01", NODULE)), EVAL))
        self.assertEqual(r["patients"], 1)
        self.assertEqual(r["active_loops"], 1)
        d = r["detections"][0]
        self.assertEqual((d["patient_id"], d["rule_id"], d["status"]), ("PASTE-1", "R003", "open"))
        self.assertTrue(d["deadline"].startswith("2026-06"))
        self.assertIn("followup_ct", d["missing"])
        self.assertTrue(any("9 mm solid nodule" in b for b in d["basis"]))
        # Default evaluation time is now
        self.assertTrue(analyse_bundle(paste_bundle("RAD", "CT chest", "2026-03-01", NODULE))["evaluation_time"])

    def test_same_result_as_the_server_ingest(self):
        """The page's in-browser result names the same loops as POST /fhir/ingest records for the bundle."""
        try:
            from fastapi.testclient import TestClient
            from src.clinloop_engine import clinical_api
            from src.clinloop_engine.api import app
            from src.clinloop_engine.loop_store import LoopStore
        except ImportError:
            self.skipTest("API dependencies not installed")
        store = LoopStore()
        clinical_api.set_store(store)
        client = TestClient(app)
        bundle = paste_bundle("RAD", "CT chest", "2026-03-01", NODULE)
        h = lambda role: {"Authorization": f"Bearer {TOKENS[role]}"}
        self.assertEqual(client.post(f"/api/v1/fhir/ingest?evaluation_time={EVAL}", json=bundle,
                                     headers=h("viewer")).status_code, 403)       # loading needs an admin
        res = client.post(f"/api/v1/fhir/ingest?evaluation_time={EVAL}", json=bundle, headers=h("admin"))
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual((body["patients"], body["active_loops"], body["loops"]["new"]), (1, 1, 1))
        here = analyse_bundle(bundle, EVAL)
        self.assertEqual(here["active_loops"], body["active_loops"])
        keys = {loop["loop_key"] for loop in store.worklist()}
        self.assertEqual({k.split("|")[1] for k in keys}, {d["rule_id"] for d in here["detections"]})
        self.assertTrue(any(k.startswith("PASTE-1|R003|") for k in keys))
        self.assertEqual(client.post("/api/v1/fhir/ingest", json={"resourceType": "Patient"},
                                     headers=h("admin")).status_code, 422)

    def test_not_a_bundle_is_refused(self):
        with self.assertRaises(ValueError):
            analyse_bundle({"resourceType": "Patient", "id": "x"})


class TestAnalysePage(unittest.TestCase):

    def setUp(self):
        self.html = read("analyse.html")

    def test_two_modes_and_the_privacy_note(self):
        self.assertIn("Runs in this browser only. Nothing is sent anywhere. Synthetic data only — do not load "
                      "real patient information on the public site.", self.html)
        self.assertIn("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/", self.html)        # exact version
        self.assertIn("params.get('inbrowser') === '1'", self.html)
        self.assertIn("window.CLINLOOP_API_BASE == null", self.html)
        self.assertIn("api('/api/v1/fhir/ingest'", self.html)
        self.assertIn("js/engine_manifest.json", self.html)
        self.assertIn("MAX_BYTES = 5 * 1024 * 1024", self.html)
        self.assertIn("Loading patient data needs an admin", self.html)
        # The only requests carrying the bundle go to this hospital's server (state.base)
        for call in re.findall(r"fetch\(([^,)]*)", self.html):
            self.assertIn(call.strip(), ("state.base + path", "'js/engine_manifest.json'", "f",
                                         "`demo/examples/${btn.dataset.example}.json`"), call)
        self.assertIn('aria-live="polite"', self.html)

    def test_paste_bundle_in_the_page_matches_the_mirror(self):
        js = self.html[self.html.index("function pasteBundle"):self.html.index("// Never echo")]
        for piece in ("id: 'PASTE-1'", "status: 'final'", "conclusion: text", "code: { text: title }",
                      "effectiveDateTime: date", "reference: 'Patient/PASTE-1'", "v2-0074",
                      "kind === 'PAT' ? 'PAT' : 'RAD'"):
            self.assertIn(piece, js)

    def test_page_is_registered_everywhere_pages_are_listed(self):
        self.assertIn("{ page: 'analyse', href: 'analyse', en: 'Analyse patient', ko: '환자 분석' }", read("js", "appnav.js"))
        self.assertRegex(read("src", "clinloop_engine", "api.py"), r'for _page in \([^)]*"analyse"')
        self.assertIn("https://clinloopai.app/analyse.html", read("sitemap.xml"))
        docker = read("Dockerfile")
        self.assertIn("analyse.html", docker)
        self.assertIn("COPY demo/examples ./web/demo/examples", docker)


if __name__ == "__main__":
    unittest.main()
