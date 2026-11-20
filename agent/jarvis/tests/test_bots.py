import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bots


class BotsModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.bots_file = self.workspace / "bots.json"
        self.patcher = patch.object(bots, "_bots_file", return_value=self.bots_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_default_bots_initialization(self):
        loaded = bots.list_bots()
        self.assertGreaterEqual(len(loaded), 6)
        ids = [b["id"] for b in loaded]
        self.assertIn("devpilot-orchestrator", ids)
        self.assertIn("fullstack-builder", ids)
        self.assertIn("ui-vibe-designer", ids)
        self.assertIn("qa-verifier", ids)
        self.assertIn("security-devops", ids)
        self.assertIn("growth-seo", ids)

    def test_save_and_get_bot(self):
        new_bot = {
            "id": "custom-agent",
            "name": "Custom Agent",
            "role": "API Tester",
            "model": "agy/gemini-3.8-flash",
            "color": "green",
            "instructions": "Test instructions",
            "memory_scope": "isolated",
            "thinking_level": "medium",
        }
        res = bots.save_bot(new_bot)
        self.assertTrue(res.get("ok"))

        retrieved = bots.get_bot("custom-agent")
        self.assertEqual(retrieved["name"], "Custom Agent")
        self.assertEqual(retrieved["role"], "API Tester")
        self.assertEqual(retrieved["model"], "agy/gemini-3.8-flash")

    def test_delete_bot(self):
        new_bot = {
            "id": "to-delete",
            "name": "Deletable Agent",
            "role": "Temporary",
            "model": "agy/gemini-3.8-flash",
            "is_default": False,
        }
        bots.save_bot(new_bot)
        del_res = bots.delete_bot("to-delete")
        self.assertTrue(del_res.get("ok"))

        with self.assertRaises(ValueError):
            bots.get_bot("to-delete")

    def test_cannot_delete_default_bot(self):
        with self.assertRaises(ValueError):
            bots.delete_bot("devpilot-orchestrator")

    def test_add_routine(self):
        routine_data = {
            "id": "test-routine",
            "title": "Nightly Build Verification",
            "schedule": "0 0 * * *",
            "prompt": "Run full test suite",
        }
        res = bots.add_or_update_routine("fullstack-builder", routine_data)
        self.assertTrue(res.get("ok"))

        builder = bots.get_bot("fullstack-builder")
        routine_ids = [r["id"] for r in builder.get("routines", [])]
        self.assertIn("test-routine", routine_ids)

    def test_run_bot_invokes_agy(self):
        fake_bridge = MagicMock(return_value={"id": "job-123", "running": True})
        with patch("codetools.agy", return_value={"id": "job-123", "running": True}) as mock_agy:
            res = bots.run_bot(fake_bridge, "fullstack-builder", "Build new auth module", "my-slug")
            self.assertTrue(mock_agy.called)
            self.assertEqual(res.get("id"), "job-123")
            self.assertEqual(res.get("bot_id"), "fullstack-builder")


class BotsHttpServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bots_file = self.root / "bots.json"
        
        import server
        self.server = server
        self.patches = [
            patch.object(bots, "_bots_file", return_value=self.bots_file),
            patch.object(server.Handler, "log_message", lambda *a: None),
        ]
        for p in self.patches:
            p.start()

        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port_patch = patch.object(server, "PORT", self.http.server_port)
        self.port_patch.start()
        import threading
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

    def test_get_bots_api(self):
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(f"{self.base}/api/bots", headers={"Host": f"127.0.0.1:{self.http.server_port}", "X-Jarvis": "1"})
        with opener.open(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertGreaterEqual(len(data.get("bots", [])), 6)

    def test_post_save_and_run_bot_api(self):
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        # Test POST /api/bots/save
        new_bot = {
            "id": "qa-api-tester",
            "name": "QA API Tester",
            "role": "API Verification",
            "model": "agy/gemini-3.8-flash",
            "color": "green",
            "instructions": "Test APIs with rigor",
            "memory_scope": "isolated",
            "thinking_level": "high",
        }
        req = urllib.request.Request(
            f"{self.base}/api/bots/save",
            data=json.dumps(new_bot).encode(),
            headers={"Host": f"127.0.0.1:{self.http.server_port}", "X-Jarvis": "1", "Content-Type": "application/json"}
        )
        with opener.open(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertEqual(data["bot"]["id"], "qa-api-tester")

        # Test GET /api/bots/computer
        req_comp = urllib.request.Request(
            f"{self.base}/api/bots/computer?id=qa-api-tester",
            headers={"Host": f"127.0.0.1:{self.http.server_port}", "X-Jarvis": "1"}
        )
        with opener.open(req_comp) as resp:
            self.assertEqual(resp.status, 200)
            cdata = json.loads(resp.read().decode())
            self.assertTrue(cdata.get("ok"))
            self.assertEqual(cdata["bot_id"], "qa-api-tester")

        # Test POST /api/bots/run with agy mock
        with patch("codetools.agy", return_value={"id": "job-qa-1", "running": True}):
            req_run = urllib.request.Request(
                f"{self.base}/api/bots/run",
                data=json.dumps({"id": "qa-api-tester", "prompt": "Verify health endpoint", "mode": "auto"}).encode(),
                headers={"Host": f"127.0.0.1:{self.http.server_port}", "X-Jarvis": "1", "Content-Type": "application/json"}
            )
            with opener.open(req_run) as resp:
                self.assertEqual(resp.status, 200)
                rdata = json.loads(resp.read().decode())
                self.assertEqual(rdata.get("id"), "job-qa-1")
                self.assertEqual(rdata.get("bot_id"), "qa-api-tester")


if __name__ == "__main__":
    unittest.main()
