"""Tests for Milestone 4: Ultra-Professional Swiss Telemetry Mesh & Controls."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "bridge"))
sys.path.insert(0, str(HERE.parents[1] / "workflow"))

import mesh
import server


class Milestone4MeshTests(unittest.TestCase):
    def test_gate_breakers_state(self):
        mesh.GATES.clear()
        res = mesh.set_gate("plan", True)
        self.assertTrue(res["ok"])
        self.assertEqual(res["stage"], "plan")
        self.assertTrue(res["locked"])

        gates = mesh.get_gates()
        self.assertTrue(gates.get("plan"))

        mesh.set_gate("plan", False)
        self.assertFalse(mesh.get_gates().get("plan"))

    def test_journey_script_exports_and_syntax(self):
        p = HERE.parent / "assets" / "journey.js"
        self.assertTrue(p.exists())
        content = p.read_text()

        # Check required architectural and tactile components
        self.assertIn("manhattanLink", content)
        self.assertIn("jr-planet jr-agent", content)
        self.assertIn("data-agent", content)
        self.assertIn("jr-card-bg", content)
        self.assertIn("jr-card-id", content)
        self.assertIn("jr-card-tier", content)
        self.assertIn("jr-card-led", content)
        self.assertIn("jr-card-ticker", content)
        self.assertIn("jr-gate-breaker", content)
        self.assertIn("jr-loop-track", content)
        self.assertIn("jr-minimap", content)
        self.assertIn("openAgentInspector", content)

        # Check Window exports
        for exp in ("init", "render", "setActive", "burst", "setCalls", "setStep", "setLiveTicker", "onRetry", "resetRun", "fit", "closeDrawer", "openAgentInspector"):
            self.assertIn(exp, content)

    def test_mesh_hidable_drawer_and_scrolling(self):
        p = HERE.parent / "assets" / "journey.js"
        content = p.read_text()
        css_p = HERE.parent / "ui" / "mesh.css"
        css_content = css_p.read_text()

        # Drawer toggle & close behavior
        self.assertIn("closeDrawer", content)
        self.assertIn("jr-drawer-close", content)
        self.assertIn("jr-drawer-tab", content)
        self.assertIn("e.key === 'Escape'", content)
        self.assertIn("closeDrawer();", content)

        # Mesh scrollability & panning bounds
        self.assertIn("minX", content)
        self.assertIn("maxX", content)
        self.assertIn("minY", content)
        self.assertIn("maxY", content)
        self.assertIn("e.shiftKey", content)
        self.assertIn("ArrowRight", content)
        self.assertIn("ArrowLeft", content)

        # CSS drawer styles and hide transitions
        self.assertIn(".jr-agent-drawer", css_content)
        self.assertIn(".jr-drawer-tab", css_content)
        self.assertIn(".jr-drawer-close", css_content)
        self.assertIn(".jr-agent-drawer.hidden", css_content)
        self.assertIn("translateX(100%)", css_content)


class HTTPMeshGatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        sessions = root / "sessions"
        sessions.mkdir()

        def mock_bridge(path, body):
            return {"ok": True}

        self.patches = [
            patch.object(server, "SESSIONS", sessions),
            patch.object(server, "LIVE", {}),
            patch.object(server, "bridge", mock_bridge),
            patch.object(server.Handler, "log_message", lambda *a: None)
        ]
        for p in self.patches:
            p.start()

        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port_patch = patch.object(server, "PORT", self.http.server_port)
        self.port_patch.start()
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(2)
        self.port_patch.stop()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        h = {"X-Jarvis": "1", "Origin": "http://127.0.0.1:8770", **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/json"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=h)
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())

    def test_gate_endpoints(self):
        # 1. POST /api/mesh/gate
        code, res = self.request("/api/mesh/gate", {"stage": "design", "locked": True})
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])
        self.assertEqual(res["stage"], "design")
        self.assertTrue(res["locked"])

        # 2. GET /api/mesh/gates
        code, res = self.request("/api/mesh/gates")
        self.assertEqual(code, 200)
        self.assertTrue(res["gates"].get("design"))

        # 3. Release gate
        code, res = self.request("/api/mesh/gate", {"stage": "design", "locked": False})
        self.assertEqual(code, 200)
        self.assertFalse(res["locked"])


if __name__ == "__main__":
    unittest.main()
