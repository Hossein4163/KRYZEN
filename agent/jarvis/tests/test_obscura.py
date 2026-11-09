"""Unit and integration tests for Obscura headless browser engine in K.R.Y.Z.E.N."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bridge"))
import runtime_settings
import pc_bridge


class TestObscuraIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_file = Path(self.tmp.name) / "test-settings.json"
        self.patch = patch.object(runtime_settings, "FILE", self.settings_file)
        self.patch.start()
        self.patch_ws = patch.object(pc_bridge, "WORKSPACE", Path(self.tmp.name))
        self.patch_ws.start()

    def tearDown(self):
        self.patch_ws.stop()
        self.patch.stop()
        self.tmp.cleanup()

    def test_runtime_settings_defaults(self):
        cfg = runtime_settings.get()
        self.assertIn("browser_engine", cfg)
        self.assertEqual(cfg["browser_engine"], "auto")
        self.assertEqual(cfg.get("obscura_path"), "/usr/local/bin/obscura")
        self.assertTrue(cfg.get("obscura_stealth"))

    def test_runtime_settings_validation(self):
        res = runtime_settings.save({"browser_engine": "obscura", "obscura_stealth": False})
        self.assertTrue(res["ok"])
        cfg = runtime_settings.get()
        self.assertEqual(cfg["browser_engine"], "obscura")
        self.assertFalse(cfg["obscura_stealth"])

        # Invalid engine
        bad = runtime_settings.save({"browser_engine": "webkit-safari"})
        self.assertFalse(bad["ok"])
        self.assertIn("browser_engine must be auto, obscura, or agent-browser", bad["errors"])

        # Empty obscura_path
        bad_path = runtime_settings.save({"obscura_path": ""})
        self.assertFalse(bad_path["ok"])
        self.assertIn("obscura_path cannot be empty", bad_path["errors"])

    def test_pc_bridge_browser_status(self):
        status = pc_bridge.h_browser_status()
        self.assertIn("active_engine", status)
        self.assertIn("configured_engine", status)
        self.assertIn("obscura", status)
        self.assertIn("agent_browser", status)
        self.assertIn("available", status["obscura"])
        self.assertIn("memory", status["obscura"])
        self.assertIn("30MB", status["obscura"]["memory"])

    def test_pc_bridge_security_blocks_file_urls(self):
        with self.assertRaises(PermissionError):
            pc_bridge.h_browser({"args": ["fetch", "file:///etc/passwd"]})
        with self.assertRaises(PermissionError):
            pc_bridge.h_browser({"action": "screenshot", "url": "file:///etc/shadow"})

    def test_pc_bridge_obscura_version_command(self):
        # Verify obscura binary execution via bridge
        if shutil.which("/usr/local/bin/obscura"):
            res = pc_bridge.h_browser({"args": ["-V"], "engine": "obscura"})
            self.assertEqual(res.get("exit_code"), 0)
            self.assertIn("obscura", res.get("output", "").lower())

    def test_pc_bridge_obscura_session_lifecycle(self):
        # Test simulated session translation
        session_id = "test-session-obscura"
        r1 = pc_bridge.h_browser({"args": ["--session", session_id, "set", "viewport", "1280", "720"]})
        self.assertTrue(r1.get("ok"))
        self.assertEqual(pc_bridge._browser_sessions.get(session_id, {}).get("viewport"), ["1280", "720"])

        r2 = pc_bridge.h_browser({"args": ["--session", session_id, "wait", "100"]})
        self.assertTrue(r2.get("ok"))

        # Test screenshot dispatch
        out_shot = Path(self.tmp.name) / "shot.png"
        pc_bridge._browser_sessions[session_id] = {"url": "https://example.com"}
        with patch.object(pc_bridge, "_run_obscura_cmd", return_value={"ok": True, "exit_code": 0, "output": "Screenshot written"}) as mock_run:
            r3 = pc_bridge.h_browser({"args": ["--session", session_id, "screenshot", str(out_shot)]})
            self.assertEqual(r3.get("exit_code"), 0)
            mock_run.assert_called_once()
            args_called = mock_run.call_args[0][0]
            self.assertEqual(args_called[0], "fetch")
            self.assertEqual(args_called[1], "https://example.com")
            self.assertEqual(args_called[2], "-s")
            self.assertEqual(args_called[3], str(out_shot))


if __name__ == "__main__":
    unittest.main()
