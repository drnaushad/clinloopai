"""
demo.py — Public demonstration mode (CLINLOOP_DEMO=1)

Lets anyone open the full app through a link without any risk to real patients:

- The database lives in memory and is filled at start-up with the repository's
  synthetic FHIR bundles only, so every restart returns to the same clean state.
- A published, view-only token (role "viewer") is shown on every page. A viewer can
  read the worklist, patient graphs, quality and governance pages, but cannot upload
  reports or images, ingest data, or change a loop, so nothing real can be put on a
  public server through it.
- Hospital connections (FHIR sync, PACS scanning, the second reader) are switched off.

Never set CLINLOOP_DEMO on a server that holds real patient data.
"""

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger("clinloop.demo")

# Published on purpose: it can only read synthetic data on a demo server
DEMO_TOKEN = "clinloop-public-demo-viewer"
DEMO_USER = "public-demo"

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SEED_BUNDLES = [os.path.join(_ROOT, "data", "fhir_example_bundle.json"),
                os.path.join(_ROOT, "data", "radiology_test_bundle.json")]

# Settings that would connect a demo server to a hospital or a model; cleared in demo mode
_HOSPITAL_SETTINGS = ("CLINLOOP_FHIR_BASE", "CLINLOOP_FHIR_TOKEN", "CLINLOOP_PACS_DICOMWEB", "CLINLOOP_PACS_TOKEN",
                      "CLINLOOP_IMAGE_SCAN", "CLINLOOP_SECOND_READER")


def enabled() -> bool:
    return os.environ.get("CLINLOOP_DEMO", "").strip().lower() in ("1", "true", "yes")


def disconnect_hospital() -> List[str]:
    """Remove any hospital connection settings, so a demo can never sync real records."""
    removed = [k for k in _HOSPITAL_SETTINGS if os.environ.pop(k, None) is not None]
    if removed:
        logger.warning("Demo mode: ignoring hospital settings %s", ", ".join(removed))
    return removed


def seed(store, bundles: Optional[List[str]] = None) -> Dict[str, int]:
    """Load the synthetic bundles through the normal ingest path; returns counts."""
    from .auth import User
    from .clinical_api import ingest_fhir, set_store
    set_store(store)
    totals = {"bundles": 0, "patients": 0, "active_loops": 0}
    for path in bundles or SEED_BUNDLES:
        if not os.path.exists(path):
            logger.warning("Demo seed bundle missing: %s", path)
            continue
        with open(path, encoding="utf-8") as fh:
            bundle = json.load(fh)
        out = ingest_fhir(bundle, None, User("demo-seed", "admin"))
        totals["bundles"] += 1
        totals["patients"] += out["patients"]
        totals["active_loops"] += out["active_loops"]
    logger.warning("Demo mode: loaded %(patients)d synthetic patients, %(active_loops)d open loops", totals)
    return totals


def web_config() -> str:
    """Extra lines for /config.js, so the pages can sign in with the demo token."""
    note = ("Public demo: synthetic patients only, view-only access, resets on restart. "
            "Do not enter real patient information.")
    return "window.CLINLOOP_DEMO = " + json.dumps({"token": DEMO_TOKEN, "note": note}) + ";\n"
