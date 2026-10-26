"""Synthetic regression: new follow-up evidence must not be lost to cached FHIR searches."""
import copy
import os
import sys
import unittest
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
from test_fhir_sync import NOW, TOKEN, StubFHIR, _resources
from src.clinloop_engine.fhir_sync import FHIRClient, sync_once
from src.clinloop_engine.loop_store import LoopStore


class TestFreshFHIRSearches(unittest.TestCase):
    def test_new_followup_not_lost_to_cached_history_and_cursor(self):
        stub = StubFHIR(_resources())
        client = FHIRClient(stub.base, token=TOKEN)
        original_get = client.session.get
        cached = {}
        def hapi_cache(url, **kwargs):
            # HAPI caches a repeated patient-history search even after a write.
            # A fresh changed-patient query can therefore see an update that the
            # subsequent cached history query omits unless no-cache is requested.
            history = 'patient=' in url or '_id=' in url
            fresh = 'no-cache' in client.session.headers.get('Cache-Control', '')
            if history and not fresh and url in cached:
                return copy.deepcopy(cached[url])
            response = original_get(url, **kwargs)
            if history: cached[url] = copy.deepcopy(response)
            return response
        store = LoopStore(':memory:')
        try:
            with patch.object(client.session, 'get', side_effect=hapi_cache):
                self.assertTrue(sync_once(store, client, now=NOW)['ok'])
                stub.resources.append({'resourceType':'Procedure','id':'fresh-synthetic-procedure','status':'completed',
                    'subject':{'reference':'Patient/SYN-001'},'performedDateTime':'2026-08-31T09:00:00Z',
                    'code':{'text':'Colonoscopy'},'meta':{'lastUpdated':'2026-08-31T10:00:00Z'}})
                updated = sync_once(store, client, now=NOW + timedelta(hours=1))
                self.assertTrue(updated['ok'])
                self.assertEqual(updated['patients'], 1)
                self.assertEqual(updated['loops']['resolved_by_engine'], 1)
                self.assertNotIn('R017', {row['rule_id'] for row in store.worklist()})
                repeated = sync_once(store, client, now=NOW + timedelta(hours=2))
                self.assertEqual(repeated['patients'], 0)
                self.assertTrue(store.verify_audit_chain())
        finally:
            stub.close()
