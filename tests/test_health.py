import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings_manager


class HealthEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {"DEWEY_CONFIG_DIR": self._tmp.name})
        self._env.start()
        settings_manager._settings = None

    def tearDown(self):
        self._env.stop()
        settings_manager._settings = None
        self._tmp.cleanup()

    def test_healthz_is_ok(self):
        with TestClient(app) as client:
            response = client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "dewey")
        self.assertIn("version", body)

    def test_healthz_reachable_when_auth_enabled(self):
        settings_manager.load()
        settings_manager.save({"auth_enabled": True, "auth_session_secret": "test-secret"})
        with TestClient(app) as client:
            healthz = client.get("/healthz")
            # A normal API route is gated by auth; the health probe is not.
            gated = client.get("/api/settings")
        self.assertEqual(healthz.status_code, 200)
        self.assertEqual(gated.status_code, 401)


if __name__ == "__main__":
    unittest.main()
