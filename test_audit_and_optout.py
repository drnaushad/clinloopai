"""Synthetic audit/opt-out regression entry point using actual ClinLoop code.

Run in the repository with its core/API test dependencies installed:
    python test_audit_and_optout.py -v
    python -m pytest test_audit_and_optout.py -v

Reuses maintained preference, provider-blocking and access-audit regressions.
No real messages are sent. Verification returns a boolean, not a corrupt index.
An unanchored hash chain cannot prove that its tail was not deleted, nor prevent
an administrator from rewriting all hashes. These tests do not certify consent
compliance, independent clinical review or external audit anchoring.
"""

import unittest

from tests import test_clinical_api as api_tests
from tests.test_phase1_production import TestAccessLog, TestOutreachOptOut, TestPhase1API
from src.clinloop_engine import clinical_api
from src.clinloop_engine.loop_store import LoopStore


class TestAuditEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        if not api_tests.HAVE_API:
            self.fail("Install the core/API test dependencies; audit endpoint checks must run.")
        previous = clinical_api.get_store()
        self.store = LoopStore()
        clinical_api.set_store(self.store)
        self.addCleanup(clinical_api.set_store, previous)
        self.addCleanup(self.store._db.close)
        self.client = api_tests.TestClient(api_tests.app)
        self.addCleanup(self.client.close)

    def test_empty_chain_and_admin_only_verification(self) -> None:
        self.assertEqual(self.client.get("/api/v1/audit/verify").status_code, 401)
        for role in ("viewer", "navigator", "clinician"):
            with self.subTest(role=role):
                self.assertEqual(self.client.get("/api/v1/audit/verify",
                                                 headers=api_tests._h(role)).status_code, 403)
        response = self.client.get("/api/v1/audit/verify", headers=api_tests._h("admin"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"audit_chain_intact": True})

    def test_preference_chain_and_out_of_band_tampering(self) -> None:
        self.store.set_outreach_preference("SYNTHETIC-AUDIT", True, "synthetic.navigator",
                                          "navigator", reason="Synthetic phone preference")
        self.store.set_outreach_preference("SYNTHETIC-AUDIT", False, "synthetic.navigator", "navigator")
        rows = list(reversed(self.store.audit_trail()))
        self.assertEqual([row["action"] for row in rows], ["outreach_opt_out", "outreach_opt_in"])
        self.assertEqual(rows[0]["prev_hash"], "GENESIS")
        self.assertEqual(rows[1]["prev_hash"], rows[0]["hash"])
        self.assertEqual(len(rows[0]["hash"]), 64)
        self.assertTrue(self.store.verify_audit_chain())
        for column, replacement in (("detail", '{}'), ("prev_hash", "synthetic-broken-link")):
            with self.subTest(column=column):
                original = self.store._db.execute(
                    f"SELECT {column} FROM audit_log WHERE id=?", (rows[1]["id"],)).fetchone()[0]
                try:
                    self.store._db.execute(f"UPDATE audit_log SET {column}=? WHERE id=?",
                                           (replacement, rows[1]["id"]))
                    self.store._db.commit()
                    response = self.client.get("/api/v1/audit/verify", headers=api_tests._h("admin"))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {"audit_chain_intact": False})
                finally:
                    self.store._db.execute(f"UPDATE audit_log SET {column}=? WHERE id=?",
                                           (original, rows[1]["id"]))
                    self.store._db.commit()
                self.assertTrue(self.store.verify_audit_chain())


if __name__ == "__main__":
    unittest.main()
