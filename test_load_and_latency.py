"""Manual synthetic benchmark; never targets a network server.

    python test_load_and_latency.py --requests 500 --workers 20

Requires the repository core/API test dependencies. Uses real signed CDS JWTs,
FastAPI TestClient and temporary disk-backed SQLite WAL databases. The first
phase shares the app's real LoopStore; the second uses independent LoopStore
connections to exercise SQLite writer contention. No model inference is run.
This is a closed-loop, in-process benchmark, not a hospital capacity guarantee.
500 total requests with 20 workers means at most 20 concurrent requests.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import platform
import sqlite3
import statistics
import tempfile
import time
import uuid
from unittest.mock import patch


def summarize(samples: list[tuple[float, str]], wall: float) -> dict:
    """Report all-request latency, including failed requests, in milliseconds."""
    latencies = [latency * 1000 for latency, _ in samples]
    percentiles = statistics.quantiles(latencies, n=100, method="inclusive")
    outcomes = Counter(outcome for _, outcome in samples)
    return {
        "attempted": len(samples), "succeeded": outcomes.get("ok", 0),
        "outcomes": dict(outcomes), "wall_seconds": round(wall, 6),
        "attempted_per_second": round(len(samples) / wall, 2),
        "successful_per_second": round(outcomes.get("ok", 0) / wall, 2),
        "latency_ms": {"p50": round(statistics.median(latencies), 2),
                       "p95": round(percentiles[94], 2),
                       "p99": round(percentiles[98], 2), "max": round(max(latencies), 2)},
    }


def run_benchmark(requests: int, workers: int) -> dict:
    """Run bounded local workloads; return only aggregate synthetic results."""
    if not 2 <= requests <= 10000 or not 1 <= workers <= min(requests, 64):
        raise ValueError("Use 2..10000 requests and 1..64 workers, no more workers than requests")
    # Test-only imports configure synthetic bearer accounts before API imports.
    from tests import test_cds_hooks as fixtures
    from src.clinloop_engine.loop_store import LoopStore
    from src.clinloop_engine.loop_detector import ClinLoopDetector
    from src.clinloop_engine import clinical_api

    if not fixtures.HAVE_API:
        raise RuntimeError("Install the repository core/API test dependencies")
    private, jwks = fixtures._key_pair()
    now = int(time.time())
    # Prepare one unique nonce per request outside the measured HTTP latency.
    tokens = [fixtures.jwt.encode(
        {"iss": fixtures.EHR, "aud": fixtures.URL, "iat": now, "exp": now + 600,
         "jti": str(uuid.uuid4()), "sub": "synthetic-load-client"},
        private, algorithm="RS384", headers={"kid": "ehr-1"}) for _ in range(requests)]
    batches = [list(range(worker, requests, workers)) for worker in range(workers)]
    previous = clinical_api.get_store()
    with tempfile.TemporaryDirectory(prefix="clinloop-synthetic-load-") as directory:
        database = str(Path(directory) / "load.sqlite")
        store = LoopStore(database)
        connections = []
        clinical_api.set_store(store)
        try:
            events = [{"event_id": "synthetic-fit", "patient_id": "SYNTHETIC-LOAD",
                       "event_type": "lab_result", "timestamp": "2026-05-01T09:00:00",
                       "status": "completed", "details": {"test": "FIT", "result": "positive"}}]
            store.upsert_detections(ClinLoopDetector(evaluation_time="2026-06-01T00:00:00")
                                    .process_patient("synthetic", "SYNTHETIC-LOAD", events))
            expected = {row["loop_key"] for row in store.worklist(patient_id="SYNTHETIC-LOAD")}
            if not expected:
                raise RuntimeError("Synthetic fixture did not produce a follow-up obligation")
            mode = store._db.execute("PRAGMA journal_mode").fetchone()[0]
            if mode.lower() != "wal":
                raise RuntimeError("Disk-backed benchmark requires SQLite WAL mode")

            def cds_batch(indices: list[int]) -> list[tuple[float, str]]:
                samples = []
                # No application lifespan: do not start feed/model watchers.
                client = fixtures.TestClient(fixtures.app)
                try:
                    for index in indices:
                        start = time.perf_counter()
                        try:
                            response = client.post("/cds-services/clinloop-open-loops",
                                headers={"Authorization": "Bearer " + tokens[index]},
                                json={"hook": "patient-view", "hookInstance": str(uuid.uuid4()),
                                      "context": {"patientId": "SYNTHETIC-LOAD",
                                                  "userId": "Practitioner/synthetic-load"}})
                            cards = response.json().get("cards", []) if response.status_code == 200 else []
                            outcome = ("ok" if response.status_code == 200 and
                                       {card.get("uuid") for card in cards} == expected else
                                       f"http_{response.status_code}_or_card_mismatch")
                        except Exception as error:
                            outcome = type(error).__name__  # No payloads, credentials or exception text.
                        samples.append((time.perf_counter() - start, outcome))
                finally:
                    client.close()
                return samples

            environment = {"CLINLOOP_CDS_CLIENTS": json.dumps([{"iss": fixtures.EHR, "jwks": jwks}]),
                           "CLINLOOP_PUBLIC_URL": "https://clinloop.hospital.example",
                           "CLINLOOP_SILENT_RUN": "0", "CLINLOOP_ENFORCE_SIGNOFF": "0",
                           "CLINLOOP_CDS_MAX_CARDS": "5"}
            with patch.dict(fixtures.os.environ, environment):
                start = time.perf_counter()
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    cds_samples = [sample for batch in executor.map(cds_batch, batches) for sample in batch]
                cds = summarize(cds_samples, time.perf_counter() - start)
            cds_rows = store._db.execute("SELECT COUNT(*) FROM audit_log WHERE action='cds_patient_view'").fetchone()[0]
            replay_rows = store._db.execute("SELECT COUNT(*) FROM cds_replay_tokens").fetchone()[0]
            cds.update(audit_rows=cds_rows, consumed_nonces=replay_rows,
                       audit_chain_intact=store.verify_audit_chain())

            # Create all connections before the timed phase; each worker owns one.
            connections = [LoopStore(database) for _ in range(workers)]

            def writer_batch(worker: int) -> list[tuple[float, str]]:
                samples = []
                for _ in batches[worker]:
                    start = time.perf_counter()
                    try:
                        connections[worker].record_audit("synthetic-load", "test", "synthetic_load_write", None, {})
                        outcome = "ok"
                    except sqlite3.OperationalError as error:
                        outcome = "sqlite_locked" if "locked" in str(error).lower() else "sqlite_operational_error"
                    except Exception as error:
                        outcome = type(error).__name__
                    samples.append((time.perf_counter() - start, outcome))
                return samples

            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=workers) as executor:
                writer_samples = [sample for batch in executor.map(writer_batch, range(workers)) for sample in batch]
            writes = summarize(writer_samples, time.perf_counter() - start)
            writes.update(audit_rows=store._db.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action='synthetic_load_write'").fetchone()[0],
                audit_chain_intact=store.verify_audit_chain())
            passed = (cds["succeeded"] == requests == cds_rows == replay_rows and cds["audit_chain_intact"]
                      and writes["succeeded"] == requests == writes["audit_rows"] and writes["audit_chain_intact"])
            return {"passed": bool(passed), "total_per_phase": requests, "max_workers": workers,
                    "sqlite_mode": mode, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                    "cds": cds, "independent_connection_writes": writes,
                    "scope": "In-process synthetic test; no network, TLS, model inference or production capacity validation",
                    "timing": "Per-operation latency excludes executor queue and JWT signing; wall time includes worker setup"}
        finally:
            clinical_api.set_store(previous)
            for connection in connections:
                connection._db.close()
            store._db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    result = run_benchmark(args.requests, args.workers)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
