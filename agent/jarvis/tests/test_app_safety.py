"""Regressions for server access, cancellation, and workspace boundaries."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codetools
import engine
import mesh
import runtime_settings
import server
from engine import pc_bridge


class AccessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "assets").mkdir()
        (self.root / "assets" / "public.css").write_text("body {}")
        (self.root / "outside.txt").write_text("synthetic marker")
        (self.root / "assets" / "link.css").symlink_to(self.root / "outside.txt")
        for name, value in {"HERE": self.root, "SESSIONS": self.root, "LIVE": {},
                            "QUEUE": [], "bridge": self.bridge}.items():
            patcher = patch.object(server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        config = self.root / "runtime.json"
        config.write_text(json.dumps({"openai_api_key": "synthetic-marker"}))
        config_patch = patch.object(runtime_settings, "FILE", config)
        config_patch.start()
        self.addCleanup(config_patch.stop)
        self.files = {}
        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)

    def bridge(self, path, args):
        if path == "/project/list":
            return {"folders": ["Demo.Project"]}
        if path == "/fs/read":
            if args["path"] in self.files:
                return {"content": self.files[args["path"]]}
            return {"error": "file not found"}
        if path == "/fs/write":
            before = self.files.get(args["path"], "") if args.get("append") else ""
            self.files[args["path"]] = before + args["content"]
            return {"ok": True}
        return {}

    def request(self, path, data=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.http.server_port, timeout=3)
        try:
            headers = {"X-Jarvis": "1", "Content-Type": "application/json", **(headers or {})}
            client.request("GET" if data is None else "POST", path, json.dumps(data) if data is not None else None, headers)
            response = client.getresponse()
            return response.status, response.read()
        finally:
            client.close()

    def test_assets_reject_traversal_and_symlinks(self):
        self.assertEqual(self.request("/assets/public.css")[0], 200)
        self.assertEqual(self.request("/assets/../outside.txt")[0], 404)
        self.assertEqual(self.request("/assets/link.css")[0], 404)

    def test_dashboard_omits_legacy_and_environment_secrets(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic-env-marker"}):
            status, data = self.request("/api/dashboard")
        self.assertEqual(status, 200)
        self.assertNotIn(b"synthetic", data)
        self.assertNotIn("openai_api_key", json.loads(data)["settings"])
        self.assertTrue(runtime_settings.save({"auto_resume": False})["ok"])
        self.assertNotIn("openai_api_key", json.loads(runtime_settings.FILE.read_text()))

    def test_host_origin_and_auth_apply_to_every_api(self):
        self.assertEqual(self.request("/api/dashboard", headers={"Host": "unknown.example"})[0], 403)
        with patch.dict(os.environ, {"JARVIS_ACCESS_TOKEN": "test-marker"}):
            self.assertEqual(self.request("/mcp", {"method": "tools/list"})[0], 401)
            headers = {"Authorization": "Bearer test-marker", "Origin": "http://localhost:1"}
            self.assertEqual(self.request("/mcp", {"method": "tools/list"}, headers)[0], 403)
            headers.pop("Origin")
            self.assertEqual(self.request("/mcp", {"method": "tools/list"}, headers)[0], 200)
            self.assertEqual(self.request("/api/dashboard", headers=headers)[0], 200)

    def test_mcp_memory_roundtrip(self):
        request = {"method": "tools/call", "id": 1, "params": {"name": "kryzen_project_memory",
                   "arguments": {"project": "Demo.Project", "action": "remember", "fact": "Keep release tests offline."}}}
        status, data = self.request("/mcp", request)
        self.assertEqual(status, 200)
        self.assertIn(b"Remembered", data)
        request["params"]["arguments"] = {"project": "Demo.Project", "action": "recall", "query": "release"}
        status, data = self.request("/mcp", request)
        self.assertIn(b"Keep release tests offline.", data)
        self.assertEqual(len(self.files), 1)

    def test_stop_cancels_only_the_current_turn_and_its_queue(self):
        session = server.Session("stoppable")
        session.running, session.turn_seq = True, 8
        server.LIVE[session.id] = session
        server.enqueue("cancel this", "Demo.Project", session.id)
        server.enqueue("keep this", "Demo.Project", "another")
        self.assertEqual(self.request("/api/stop", {"id": session.id, "turn_seq": 7})[0], 409)
        self.assertFalse(session.stop_requested.is_set())
        status, data = self.request("/api/stop", {"id": session.id, "turn_seq": 8})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["cancelled_queue"], 1)
        self.assertTrue(session.stop_requested.is_set())
        self.assertEqual(server.QUEUE[0]["session"], "another")
        self.assertEqual(self.request("/api/run-control", {"id": session.id, "action": "resume"})[0], 409)


class WorkspaceSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / "Demo.Project"
        self.project.mkdir()
        for module, attr, value in ((pc_bridge, "WORKSPACE", self.root),
                                    (pc_bridge, "PROTECTED", []),
                                    (codetools, "WORKSPACE", str(self.root)),
                                    (mesh, "SYS", self.root / "vault")):
            patcher = patch.object(module, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_dotted_project_keeps_its_identity(self):
        with patch.object(pc_bridge, "HOME", self.root):
            linked = pc_bridge.h_project_link({"path": str(self.project)})
            self.assertEqual(linked["slug"], "Demo.Project")
            self.assertIn("Demo.Project", pc_bridge.h_project_list({})["folders"])
            self.assertEqual(pc_bridge.slug_of({"slug": "Demo.Project"}), "Demo.Project")

    def test_box_discard_cannot_touch_metadata_and_writes_reject_symlinks(self):
        codetools.create_isolated_box("Demo.Project", "one")
        marker = self.project / ".devpilot" / "keep"
        marker.write_text("keep this")
        with self.assertRaises(ValueError):
            codetools.discard_isolated_box("Demo.Project", "..")
        self.assertTrue(marker.is_file())
        outside = self.root / "outside"
        outside.write_text("keep this too")
        (self.project / "link").symlink_to(outside)
        with self.assertRaises(ValueError):
            codetools.write_isolated_box("Demo.Project", "one", "link", "overwrite")
        self.assertEqual(outside.read_text(), "keep this too")

    def test_gate_persists_and_is_scoped_to_the_project(self):
        mesh.set_gate("plan", True, "Demo.Project")
        self.assertEqual(mesh.blocking_gate("Demo.Project", "build"), "plan")
        self.assertIsNone(mesh.blocking_gate("Demo.Project", "plan"))
        self.assertIsNone(mesh.blocking_gate("another", "build"))
        self.assertTrue((mesh.SYS / "stage-gates.json").is_file())
        mesh.set_gate("plan", False, "Demo.Project")
        self.assertIsNone(mesh.blocking_gate("Demo.Project", "build"))

    def test_runner_cancels_an_active_sandbox_process(self):
        cancelled = threading.Event()
        result = {}
        def run():
            marker = pc_bridge.RUN_CANCEL.set(cancelled)
            try:
                result.update(pc_bridge.h_shell({"cwd": str(self.project), "cmd": "touch started; sleep 20; touch too-late"}))
            finally:
                pc_bridge.RUN_CANCEL.reset(marker)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        for _ in range(60):
            if (self.project / "started").is_file() or not worker.is_alive():
                break
            time.sleep(0.05)
        started = (self.project / "started").is_file()
        cancelled.set()
        worker.join(2)
        self.assertTrue(started, result)
        self.assertFalse(worker.is_alive())
        self.assertTrue(result.get("cancelled"), result)
        self.assertFalse((self.project / "too-late").exists())

    def test_web_fetch_rejects_loopback(self):
        with self.assertRaises(PermissionError):
            pc_bridge.h_fetch({"url": "http://127.0.0.1:8780/api/dashboard"})

    def test_shell_cannot_read_or_write_another_project(self):
        (self.root / "private").write_text("other project")
        result = pc_bridge.h_shell({"cwd": str(self.project), "cmd": "test ! -e ../private && ! touch ../nope && touch inside"})
        self.assertEqual(result.get("exit_code"), 0, result)
        self.assertTrue((self.project / "inside").is_file())
        self.assertFalse((self.root / "nope").exists())


class CancellationTests(unittest.TestCase):
    def engine(self):
        model = engine.Engine.__new__(engine.Engine)
        model.stop, model.pause_requested, model.paused = (threading.Event() for _ in range(3))
        model.emit = lambda event: None
        return model

    def test_pause_waits_for_inflight_operation(self):
        model = self.engine()
        entered, complete = threading.Event(), threading.Event()
        def operate():
            with model.operation():
                entered.set()
                complete.wait(3)
        operation = threading.Thread(target=operate, daemon=True)
        operation.start()
        self.assertTrue(entered.wait(1))
        model.pause_requested.set()
        boundary = threading.Thread(target=model.checkpoint_control, daemon=True)
        boundary.start()
        try:
            self.assertFalse(model.paused.wait(0.2))
            complete.set()
            self.assertTrue(model.paused.wait(1))
        finally:
            complete.set()
            model.pause_requested.clear()
            operation.join(2)
            boundary.join(2)
        self.assertFalse(boundary.is_alive())
        self.assertFalse(model.paused.is_set())

    def test_stop_interrupts_a_silent_model_stream(self):
        opened, release, stopped = (threading.Event() for _ in range(3))
        model = self.engine()
        class Silent(server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                opened.set()
                release.wait(5)

            def log_message(self, *args):
                return

        http = server.ThreadingHTTPServer(("127.0.0.1", 0), Silent)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()

        def request():
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{http.server_port}")
                model._stream_from_req(engine.AgentSpec("test", "test", "", 1, []), req)
            except engine.Stopped:
                stopped.set()

        stream = threading.Thread(target=request, daemon=True)
        stream.start()
        try:
            self.assertTrue(opened.wait(2))
            model.request_stop()
            self.assertTrue(stopped.wait(2))
        finally:
            release.set()
            stream.join(2)
            http.shutdown()
            worker.join(2)
            http.server_close()


if __name__ == "__main__":
    unittest.main()
