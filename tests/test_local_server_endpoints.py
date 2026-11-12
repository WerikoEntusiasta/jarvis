"""
Teste Funcional dos Endpoints HTTP Locais do J.A.R.V.I.S. Windows (:8085)
"""

import urllib.request
import json
import unittest

BASE_URL = "http://127.0.0.1:8085"

class TestLocalServerEndpoints(unittest.TestCase):

    def _get(self, path):
        req = urllib.request.Request(f"{BASE_URL}{path}")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path, payload):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read().decode("utf-8"))

    def test_01_status(self):
        d = self._get("/api/status")
        self.assertEqual(d.get("status"), "online")
        self.assertEqual(d.get("mode"), "standalone_windows")

    def test_02_telemetry(self):
        d = self._get("/api/telemetry")
        self.assertIn("cpu_percent", d)
        self.assertIn("ram_percent", d)
        self.assertIn("gpu", d)

    def test_03_system_windows_and_monitors(self):
        w = self._get("/api/system/windows")
        self.assertTrue(w.get("success"))
        self.assertGreater(w.get("count", 0), 0)

        m = self._get("/api/system/monitors")
        self.assertTrue(m.get("success"))
        self.assertGreater(m.get("count", 0), 0)

        info = self._get("/api/system/info")
        self.assertTrue(info.get("success"))
        self.assertEqual(info.get("os"), "Windows")

    def test_04_system_control_mcp(self):
        res = self._post("/api/system/control", {"action": "mouse_position"})
        self.assertTrue(res.get("success"))
        self.assertIn("x", res)
        self.assertIn("y", res)

    def test_05_vision_status(self):
        st = self._get("/api/vision/status")
        self.assertIn("enabled", st)
        self.assertIn("camera_device", st)

if __name__ == "__main__":
    unittest.main()
