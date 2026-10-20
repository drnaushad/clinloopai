"""Public gateway boundaries; fixed synthetic inputs and a fake model only."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.clinloop_engine import public_model_gateway as g


class TestPublicModelGateway(unittest.TestCase):
    def setUp(self):
        g._recent.clear()
        self.client = TestClient(g.app)
        self.case_id = g.reader.catalog()["cases"][0]["id"]
        self.path = f"/api/v1/demo/reports/{self.case_id}/live"

    def test_only_catalogue_routes_are_exposed(self):
        self.assertEqual(self.client.get('/api/v1/demo/reports').status_code, 200)
        for path in ['/api/tags', '/api/generate', '/api/v1/worklist', '/api/v1/fhir/check', '/docs', '/openapi.json']:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post('/api/v1/demo/reports/unknown/live').status_code, 404)

    def test_body_and_unapproved_origin_cannot_reach_model(self):
        with patch.object(g.reader, 'live_read') as model:
            self.assertEqual(self.client.post(self.path, json={'prompt':'Synthetic prompt'}).status_code, 400)
            self.assertEqual(self.client.post(self.path, headers={'Origin':'https://example.org'}).status_code, 403)
            model.assert_not_called()

    def test_global_quota_and_cors(self):
        with patch.dict('os.environ', {'CLINLOOP_PUBLIC_READS_PER_HOUR':'1'}), patch.object(g.reader, 'live_read', return_value={'available':True,'items':[]}):
            r = self.client.post(self.path, headers={'Origin':g.ORIGIN})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.headers['access-control-allow-origin'], g.ORIGIN)
            self.assertEqual(self.client.post(self.path).status_code, 429)

    def test_failure_does_not_disclose_internal_error(self):
        with patch.object(g.reader, 'live_read', return_value={'available':False,'reason':'internal URL secret'}):
            r = self.client.post(self.path)
            self.assertEqual(r.status_code, 503)
            self.assertNotIn('secret', r.text)
