import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "bridge"))
sys.path.insert(0, str(HERE.parents[1] / "workflow"))

import codetools
import engine
import media
import server


class Milestone3VibeStudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name)
        self.project_name = "test-vibe-project"
        self.project_dir = self.workspace / self.project_name
        self.project_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "PROJECT.md").write_text("# Test Project")

        self.orig_workspace = codetools.WORKSPACE
        codetools.WORKSPACE = str(self.workspace)

    def tearDown(self):
        codetools.WORKSPACE = self.orig_workspace
        self.tmp_dir.cleanup()

    def test_vibe_config_defaults_and_save(self):
        cfg = codetools.vibe_config_get(self.project_name)
        self.assertEqual(cfg.get("aesthetic"), "Swiss Grid")
        self.assertEqual(cfg.get("density"), 3)
        self.assertEqual(cfg.get("motion"), 3)
        self.assertEqual(cfg.get("stack"), "Vanilla Zero-Dep")

        updated = codetools.vibe_config_save(self.project_name, {
            "aesthetic": "Brutalist",
            "density": 5,
            "motion": 1,
            "stack": "React/Tailwind"
        })
        self.assertEqual(updated["aesthetic"], "Brutalist")
        self.assertEqual(updated["density"], 5)
        self.assertEqual(updated["motion"], 1)

        reloaded = codetools.vibe_config_get(self.project_name)
        self.assertEqual(reloaded["aesthetic"], "Brutalist")
        self.assertEqual(reloaded["density"], 5)

    def test_vibe_checkpoint_and_rollback(self):
        bridge_mock = MagicMock()
        bridge_mock.return_value = {"exit_code": 0, "stdout": "abc1234\n", "stderr": ""}

        res = codetools.vibe_checkpoint(bridge_mock, self.project_name, "test freeze")
        self.assertTrue(res["ok"])
        self.assertTrue(res["tag"].startswith("vibe-checkpoint-"))
        self.assertEqual(res["label"], "test freeze")

        # Checkpoints listing
        list_res = codetools.vibe_checkpoints(bridge_mock, self.project_name)
        self.assertTrue(list_res["ok"])
        self.assertTrue(len(list_res["checkpoints"]) >= 1)
        self.assertEqual(list_res["checkpoints"][0]["label"], "test freeze")

        # Rollback
        rb_res = codetools.vibe_rollback(bridge_mock, self.project_name, res["tag"])
        self.assertTrue(rb_res["ok"])
        self.assertEqual(rb_res["restored"], res["tag"])

    def test_vibe_token_extraction_and_css_generation(self):
        tokens = media.extract_vibe_tokens(aesthetic="Swiss Grid")
        self.assertIn("bg", tokens)
        self.assertIn("accent", tokens)
        self.assertIn("radius", tokens)
        self.assertEqual(tokens["radius"], "0px")

        css = media.generate_vibe_tokens_css(tokens)
        self.assertIn(":root", css)
        self.assertIn("--vibe-bg:", css)
        self.assertIn("--vibe-accent:", css)
        self.assertIn("--vibe-radius: 0px;", css)

        # SaaS aesthetic gives rounded border radius
        saas_tokens = media.extract_vibe_tokens(aesthetic="Minimal SaaS")
        self.assertEqual(saas_tokens["radius"], "6px")

    def test_vibe_directives_injected_in_agent_system_prompt(self):
        codetools.vibe_config_save(self.project_name, {
            "aesthetic": "Cyberpunk",
            "density": 4,
            "motion": 5,
            "stack": "React/Tailwind"
        })

        e = engine.Engine.__new__(engine.Engine)
        e.project = self.project_name
        e.project_root = str(self.project_dir)
        e.bridge = None
        e.settings = {"mask_after": 2}
        e.blobs = {}
        e.emit = MagicMock()

        agent = engine.AgentSpec("Design Agent", "m", "Base system prompt.", 1, [])
        passed_views = []

        def mock_chat(ag, view, tools):
            passed_views.append(view)
            return ("Vibe design finished.", [])

        e.chat = mock_chat
        e.checkpoint_control = MagicMock()
        e._maybe_compact = MagicMock()

        e.run_agent(agent, "Design hero header", [])
        self.assertTrue(len(passed_views) > 0)
        system_content = passed_views[0][0]["content"]
        self.assertIn("VIBE STUDIO DIRECTIVES", system_content)
        self.assertIn("Aesthetic Dial: Cyberpunk", system_content)
        self.assertIn("UI Density: Level 4/5", system_content)
        self.assertIn("Motion Dynamics: Level 5/5", system_content)
        self.assertIn("Architecture & Stack Lock: React/Tailwind", system_content)


class HTTPVibeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        sessions = root / "sessions"
        sessions.mkdir()
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.project_dir = self.workspace / "test-vibe"
        self.project_dir.mkdir()
        (self.project_dir / "PROJECT.md").write_text("# Test")

        self.orig_workspace = codetools.WORKSPACE
        codetools.WORKSPACE = str(self.workspace)

        def mock_bridge(path, body):
            if path == "/fs/write":
                return {"ok": True}
            if path == "/shell":
                return {"exit_code": 0, "stdout": "abc1234\n", "stderr": ""}
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
        codetools.WORKSPACE = self.orig_workspace
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        h = {"X-Jarvis": "1", "Origin": "http://127.0.0.1:8770", **(headers or {})}
        if body is not None:
            h["Content-Type"] = "application/json"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=h)
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())

    def test_vibe_http_api_endpoints(self):
        # 1. GET /api/vibe/config
        code, res = self.request("/api/vibe/config?slug=test-vibe")
        self.assertEqual(code, 200)
        self.assertEqual(res["config"]["aesthetic"], "Swiss Grid")

        # 2. POST /api/vibe/config
        code, res = self.request("/api/vibe/config", {"slug": "test-vibe", "config": {"aesthetic": "Brutalist", "density": 5}})
        self.assertEqual(code, 200)
        self.assertEqual(res["config"]["aesthetic"], "Brutalist")

        # 3. POST /api/vibe/checkpoint
        code, res = self.request("/api/vibe/checkpoint", {"slug": "test-vibe", "label": "pre-redesign"})
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])
        tag = res["tag"]

        # 4. GET /api/vibe/checkpoints
        code, res = self.request("/api/vibe/checkpoints?slug=test-vibe")
        self.assertEqual(code, 200)
        self.assertTrue(any(c["tag"] == tag for c in res["checkpoints"]))

        # 5. POST /api/vibe/rollback
        code, res = self.request("/api/vibe/rollback", {"slug": "test-vibe", "checkpoint_id": tag})
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])

        # 6. POST /api/vibe/clone
        code, res = self.request("/api/vibe/clone", {"slug": "test-vibe", "aesthetic": "Swiss Grid"})
        self.assertEqual(code, 200)
        self.assertTrue(res["ok"])
        self.assertIn(":root", res["css"])


if __name__ == "__main__":
    unittest.main()
