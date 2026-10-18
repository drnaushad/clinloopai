"""
fhir_folder.py — Run the engine over a folder of FHIR files (Synthea, a bulk export saved to disk)

For testing scale and mapping on synthetic or public data before any hospital connection. The folder
is read like a Bulk FHIR export: every resource goes into the loop store's local copy
(`fhir_mirror`), then the normal sync (`fhir_sync.sync_once`) evaluates each patient from it. Nothing
here is new clinical logic: the same mapping, rules, report and result versions and warnings apply as
for a hospital feed.

Inputs (any mix, sub-folders included):
  * *.ndjson — one resource per line (Synthea `exporter.fhir.bulk_data = true`, Bulk FHIR files);
  * *.json   — a Bundle (Synthea's default export: one transaction Bundle per patient) or one resource.

Files are streamed: a Bundle is read one file at a time and NDJSON one line at a time, so memory stays
bounded by the largest single Bundle. References are made local before storing: inside a Bundle each
`urn:uuid:` reference is resolved through the entries' fullUrl; in NDJSON a `urn:uuid:` subject or
patient reference is read as Patient/<uuid> (Synthea's convention) and counted.

    python -m src.clinloop_engine.fhir_folder data/synthea/fhir --db /tmp/run.db

The summary has counts only (files, resources, patients, loops per rule, warnings, time): no patient
identifiers, so it can be pasted into a report. Synthetic results are not evidence of accuracy on real
patients (docs/regulatory/CLINICAL_EVALUATION_PLAN.md §2).
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

from .fhir_ingest import _patient_id
from .loop_store import LoopStore

logger = logging.getLogger(__name__)
BATCH = 500


class FolderError(Exception):
    pass


def _local_refs(node, full_urls: Dict[str, str], stats: Counter, key: str = "") -> None:
    """Rewrite `urn:uuid:` references in place: through the Bundle's fullUrls, else (NDJSON) a
    subject/patient reference to Patient/<uuid>."""
    if isinstance(node, dict):
        ref = node.get("reference")
        if isinstance(ref, str) and ref.startswith("urn:uuid:"):
            if ref in full_urls:
                node["reference"] = full_urls[ref]
            elif key in ("subject", "patient"):
                node["reference"] = "Patient/" + ref[len("urn:uuid:"):]
                stats["uuid_subject_assumed_patient"] += 1
            else:
                stats["unresolved_uuid_reference"] += 1
        for k, v in node.items():
            _local_refs(v, full_urls, stats, k)
    elif isinstance(node, list):
        for v in node:
            _local_refs(v, full_urls, stats, key)


def iter_folder(path: str, stats: Counter) -> Iterator[Dict]:
    """Every resource in the folder, references made local. Unreadable files and lines are counted."""
    files = sorted(os.path.join(d, f) for d, _, names in os.walk(path) for f in names
                   if f.endswith((".ndjson", ".json")))
    if not files:
        raise FolderError(f"No .ndjson or .json files under {path}")
    for name in files:
        stats["files"] += 1
        if name.endswith(".ndjson"):
            with open(name, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except ValueError:
                        stats["unreadable_lines"] += 1
                        continue
                    if isinstance(r, dict) and r.get("resourceType"):
                        _local_refs(r, {}, stats)
                        yield r
            continue
        try:
            with open(name, encoding="utf-8") as f:
                doc = json.load(f)
        except ValueError:
            stats["unreadable_files"] += 1
            continue
        if not isinstance(doc, dict):
            stats["unreadable_files"] += 1
            continue
        if doc.get("resourceType") != "Bundle":
            _local_refs(doc, {}, stats)
            yield doc
            continue
        entries = [e for e in doc.get("entry", []) if isinstance(e, dict) and isinstance(e.get("resource"), dict)]
        full_urls = {e["fullUrl"]: f"{e['resource'].get('resourceType')}/{e['resource'].get('id')}"
                     for e in entries if e.get("fullUrl") and e["resource"].get("id")}
        for e in entries:
            _local_refs(e["resource"], full_urls, stats)
            yield e["resource"]


def load_resources(path: str) -> List[Dict]:
    """A FHIR export as a list of resources: a folder (bundles and NDJSON, as above) or one JSON file
    (a Bundle or a resource). For the validation tools, which work on samples that fit in memory."""
    if os.path.isdir(path):
        return list(iter_folder(path, Counter()))
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if isinstance(doc, list):
        return doc
    if doc.get("resourceType") == "Bundle":
        return [e["resource"] for e in doc.get("entry", []) if isinstance(e, dict) and isinstance(e.get("resource"), dict)]
    return [doc]


class FolderClient:
    """Looks like BulkFHIRClient to the sync: changed_patients() loads the folder into the local copy."""

    def __init__(self, path: str):
        self.path = path
        self.store: Optional[LoopStore] = None
        self.stats: Counter = Counter()

    def bind(self, store: LoopStore) -> "FolderClient":
        self.store = store
        return self

    def changed_patients(self, since: str) -> Tuple[Set[str], Optional[str]]:
        if self.store is None:
            raise FolderError("Folder client is not bound to a loop store")
        patients: Set[str] = set()
        batch: List[Tuple[str, Optional[str], str, Dict]] = []
        for r in iter_folder(self.path, self.stats):
            if not r.get("id"):
                self.stats["resources_without_id"] += 1
                continue
            rtype = r["resourceType"]
            pid = r["id"] if rtype == "Patient" else _patient_id(r)
            if pid:
                patients.add(pid)
            else:
                self.stats["resources_without_patient"] += 1
            self.stats["resources"] += 1
            self.stats[f"type:{rtype}"] += 1
            batch.append((rtype, pid, r["id"], r))
            if len(batch) >= BATCH:
                self.store.mirror_upsert(batch)
                batch = []
        self.store.mirror_upsert(batch)
        return patients, None

    def patient_history(self, patient_id: str) -> List[Dict]:
        return self.store.mirror_history(patient_id)


def run_folder(path: str, store: LoopStore, now: Optional[datetime] = None) -> Dict:
    """Load the folder and evaluate every patient in it. Returns a summary with counts only."""
    from .fhir_sync import sync_once
    client = FolderClient(path)
    started = time.monotonic()
    result = sync_once(store, client, source="folder-run", now=now)
    elapsed = time.monotonic() - started
    if not result.get("ok"):
        raise FolderError(result.get("error") or "the run failed")
    loops = store.worklist(include_inactive=True)
    by_rule = Counter(l["rule_id"] for l in loops)
    open_by_rule = Counter(l["rule_id"] for l in loops if l["engine_status"] in ("open", "needs_human_review"))
    stats = dict(client.stats)
    return {"files": stats.pop("files", 0), "resources": stats.pop("resources", 0),
            "resource_types": {k[5:]: stats.pop(k) for k in sorted(k for k in list(stats) if k.startswith("type:"))},
            "patients": result["patients"], "events": result["events"], "mapping_warnings": result["warnings"],
            "loops": len(loops), "loops_by_rule": dict(sorted(by_rule.items())),
            "open_or_review_by_rule": dict(sorted(open_by_rule.items())),
            "reading": stats, "seconds": round(elapsed, 1),
            "note": "Synthetic or public data: counts show the pipeline works, not clinical accuracy."}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run ClinLoop over a folder of FHIR files (counts only)")
    ap.add_argument("folder")
    ap.add_argument("--db", help="SQLite file for the run (default: a temporary file, deleted afterwards)")
    ap.add_argument("--evaluation-time", help="ISO time to evaluate deadlines at (default: now)")
    args = ap.parse_args(argv)
    now = datetime.fromisoformat(args.evaluation_time) if args.evaluation_time else None
    tmp = None
    if not args.db:
        tmp = tempfile.TemporaryDirectory()
        db = os.path.join(tmp.name, "run.db")
    else:
        db = args.db
    try:
        summary = run_folder(args.folder, LoopStore(db), now=now)
    except FolderError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if tmp is not None:
            tmp.cleanup()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
