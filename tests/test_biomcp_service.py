"""Internal service hosts remain allowlisted; rebinding protection stays enabled."""
import unittest
from types import SimpleNamespace
from src.clinloop_engine.biomcp_service import configure_security


class TestBioMCPService(unittest.TestCase):
    def test_internal_host_is_allowed_without_wildcards(self):
        app=SimpleNamespace(settings=SimpleNamespace())
        configure_security(app)
        security=app.settings.transport_security
        self.assertTrue(security.enable_dns_rebinding_protection)
        self.assertIn('biomcp:8000',security.allowed_hosts)
        self.assertNotIn('*',security.allowed_hosts)
        self.assertNotIn('evil.example',security.allowed_hosts)
