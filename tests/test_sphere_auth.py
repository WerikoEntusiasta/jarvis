import unittest
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server

class MockHeaders:
    def __init__(self, headers_dict=None):
        self._headers = headers_dict or {}

    def get(self, key, default=""):
        for k, v in self._headers.items():
            if k.lower() == key.lower():
                return v
        return default

class MockRequestHandler:
    def __init__(self, headers=None, path="/api/chat"):
        self.headers = MockHeaders(headers)
        self.path = path

    def _client_is_local(self):
        return False

    # Bind the method from server.JarvisRequestHandler
    _get_request_auth = server.JarvisRequestHandler._get_request_auth

class TestSphereAuth(unittest.TestCase):

    def test_sphere_source_body_grants_owner_auth(self):
        handler = MockRequestHandler()
        body = {"source": "esfera", "device_id": "jarvis_sphere_esp32s3", "message": "desligar o pc"}
        auth = handler._get_request_auth(body)
        self.assertEqual(auth["role"], "Proprietário")
        self.assertTrue(auth["permissions"].get("full_access") or auth["permissions"].get("power_control"))

    def test_sphere_header_grants_owner_auth(self):
        handler = MockRequestHandler(headers={"X-Source": "esfera"})
        auth = handler._get_request_auth()
        self.assertEqual(auth["role"], "Proprietário")

    def test_sphere_device_id_header_grants_owner_auth(self):
        handler = MockRequestHandler(headers={"X-Device-ID": "jarvis_sphere_esp32s3"})
        auth = handler._get_request_auth()
        self.assertEqual(auth["role"], "Proprietário")

    def test_sphere_query_param_grants_owner_auth(self):
        handler = MockRequestHandler(path="/api/chat?source=esfera")
        auth = handler._get_request_auth()
        self.assertEqual(auth["role"], "Proprietário")

    def test_unauthenticated_request_remains_guest(self):
        handler = MockRequestHandler()
        auth = handler._get_request_auth()
        self.assertEqual(auth["role"], "Convidado")

if __name__ == "__main__":
    unittest.main()
