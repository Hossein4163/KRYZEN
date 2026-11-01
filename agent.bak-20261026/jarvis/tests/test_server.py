"""HTTP contract and runtime integration tests, with disposable storage and no model calls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import engine
import mesh
import studio
from test_studio import MemoryBridge


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        sessions = root / "sessions"
        sessions.mkdir()
        self.bridge = MemoryBridge()
        self.patches = [patch.object(mesh, "SYS", root), patch.object(server, "SESSIONS", sessions),
                        patch.object(server, "LIVE", {}), patch.object(server, "bridge", self.bridge),
                        patch.object(server.Handler, "log_message", lambda *a: None)]
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
        req = urllib.request.Request(self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "X-Jarvis": "1", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            finally:
                e.close()

    def test_flow_http_contract_and_conflict(self):
        code, result = self.request("/api/studio/flow-create", {"name": "Test flow"})
        self.assertEqual(code, 200)
        self.assertTrue(result["ok"])
        self.assertIn("revision", result["flow"])
        code, listing = self.request("/api/studio/flows")
        self.assertEqual(listing["flows"][0]["name"], "Test flow.canvas")
        code, result = self.request("/api/studio/flow", {"name": "Test flow.canvas", "canvas": {"nodes": [], "edges": []}})
        self.assertTrue(result["conflict"])
        code, result = self.request("/api/studio/flow", {"name": "Test flow.canvas", "canvas": "invalid"})
        self.assertEqual(code, 400)
        self.assertFalse(result["ok"])

    def test_plan_http_edits_use_real_revision_and_approval(self):
        code, plan = self.request("/api/studio/plan?slug=example-project")
        self.assertEqual(code, 200)
        self.assertFalse(plan["exists"])
        code, saved = self.request("/api/studio/plan", {"slug": "example-project", "revision": plan["revision"],
                                                      "content": "# Plan\n- [ ] Deliver the feature\n"})
        self.assertTrue(saved["ok"])
        code, result = self.request("/api/studio/plan-approval", {"slug": "example-project", "status": "approved",
                                                               "revision": saved["revision"]})
        self.assertEqual(result["approval"]["status"], "approved")
        code, changed = self.request("/api/studio/plan-task", {"slug": "example-project", "line": 2,
                                                             "done": True, "revision": saved["revision"]})
        self.assertEqual(changed["plan"]["progress"], {"done": 1, "total": 1})
        self.assertEqual(changed["plan"]["approval"]["status"], "outdated")

    def test_cross_origin_and_malformed_body_are_rejected(self):
        code, _ = self.request("/api/studio/flow-create", {"name": "Denied"}, {"Origin": "https://elsewhere.example"})
        self.assertEqual(code, 403)
        code, _ = self.request("/api/studio/flow-create", [])
        self.assertEqual(code, 400)
        req = urllib.request.Request(self.base + "/api/studio/flow-create", data=b"{", headers={"X-Jarvis": "1"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(error.exception.code, 400)
        error.exception.close()

    def test_pause_resume_and_stop_http_control(self):
        session = server.Session("test-run")
        session.running = True
        session.engine = engine.Engine.__new__(engine.Engine)
        e = session.engine
        e.pause_requested, e.paused, e.stop = threading.Event(), threading.Event(), threading.Event()
        server.LIVE[session.id] = session
        code, result = self.request("/api/run-control", {"id": session.id, "action": "pause"})
        self.assertEqual(result["state"], "pause_requested")
        self.assertTrue(e.pause_requested.is_set())
        code, result = self.request("/api/session?id=test-run")
        self.assertTrue(result["pause_requested"])
        code, result = self.request("/api/run-control", {"id": session.id, "action": "resume"})
        self.assertFalse(e.pause_requested.is_set())
        code, result = self.request("/api/stop", {"id": session.id})
        self.assertTrue(e.stop.is_set())
        self.assertTrue(session.stop_requested.is_set())

    def test_routing_and_approval_change_are_guarded_during_runs(self):
        session = server.Session("active")
        session.running = True
        server.LIVE[session.id] = session
        code, result = self.request("/api/studio/flow-active", {"name": ""})
        self.assertEqual(code, 409)
        self.assertFalse(result["ok"])

    def test_fast_chat_returns_replay_cursor_and_persists_completion(self):
        class FastEngine:
            def __init__(self, emit, project=""):
                self.emit = emit
                self.stop, self.paused, self.pause_requested = threading.Event(), threading.Event(), threading.Event()
            def respond(self, text, history):
                self.emit({"type": "token", "agent": engine.ORCHESTRATOR, "text": "Fast reply"})
                return "Fast reply"
        with patch.object(engine, "Engine", FastEngine):
            code, started = self.request("/api/chat", {"text": "fast", "project": "example-project"})
            self.assertEqual(code, 200)
            self.assertEqual(started["from_seq"], 0)
            session = server.LIVE[started["id"]]
            with session.cond:
                session.cond.wait_for(lambda: not session.running, timeout=2)
            self.assertEqual(session.messages[-1]["content"], "Fast reply")
            self.assertEqual(session.next_seq, 3)
            req = urllib.request.Request(self.base + "/api/events?id=" + session.id + "&from=0",
                                         headers={"Last-Event-ID": "1"})
            with urllib.request.urlopen(req, timeout=2) as response:
                self.assertEqual(response.readline(), b"id: 2\n")
                self.assertIn(b'"turn_end"', response.readline())

    def test_continue_requires_project_and_prevents_duplicate_project_runs(self):
        code, result = self.request("/api/continue", {})
        self.assertEqual(code, 400)
        code, result = self.request("/api/continue", {"project": ["example-project"]})
        self.assertEqual(code, 400)
        active = server.Session("already-working")
        active.project, active.running = "example-project", True
        server.LIVE[active.id] = active
        code, result = self.request("/api/continue", {"project": "example-project"})
        self.assertEqual(code, 409)
        self.assertEqual(result["active_session"], active.id)
        self.assertTrue(active.running)

    def test_continue_uses_explicit_project_and_saved_checkpoint_prompt(self):
        class ContinueEngine:
            def __init__(self, emit, project=""):
                self.project = project
                self.stop, self.paused, self.pause_requested = threading.Event(), threading.Event(), threading.Event()
            def respond(self, text, history):
                return self.project + ": " + text
        with patch.object(engine, "Engine", ContinueEngine):
            code, started = self.request("/api/continue", {"project":"example-project", "text":"ignore the selected project"})
            self.assertEqual(code, 200)
            session = server.LIVE[started["id"]]
            with session.cond:
                session.cond.wait_for(lambda: not session.running, timeout=2)
            self.assertEqual(session.project, "example-project")
            self.assertEqual(session.messages[0]["content"], "Continue project example-project from its saved checkpoint.")

    def test_avatar_is_served_locally(self):
        with urllib.request.urlopen(self.base + "/assets/user-avatar.svg", timeout=2) as response:
            self.assertEqual(response.headers.get_content_type(), "image/svg+xml")
            self.assertIn(b"<svg", response.read())

    def test_sessions_filter_by_project(self):
        # Create two sessions with different projects and one general session
        s1 = server.Session("20261024-000001-aaaa")
        s1.title = "Chat in project alpha"
        s1.project = "alpha"
        s1.messages = [{"role": "user", "content": "hi"}]
        s1.save()

        s2 = server.Session("20261024-000002-bbbb")
        s2.title = "Chat in project beta"
        s2.project = "beta"
        s2.messages = [{"role": "user", "content": "hello"}]
        s2.save()

        s3 = server.Session("20261024-000003-cccc")
        s3.title = "General chat"
        s3.project = None
        s3.save()

        # Unfiltered returns all 3
        code, res = self.request("/api/sessions")
        self.assertEqual(code, 200)
        self.assertEqual(len(res["sessions"]), 3)

        # Filtered by alpha returns only s1
        code, res_alpha = self.request("/api/sessions?project=alpha")
        self.assertEqual(code, 200)
        self.assertEqual(len(res_alpha["sessions"]), 1)
        self.assertEqual(res_alpha["sessions"][0]["id"], "20261024-000001-aaaa")
        self.assertEqual(res_alpha["sessions"][0]["project"], "alpha")

        # Filtered by beta returns only s2
        code, res_beta = self.request("/api/sessions?project=beta")
        self.assertEqual(code, 200)
        self.assertEqual(len(res_beta["sessions"]), 1)
        self.assertEqual(res_beta["sessions"][0]["id"], "20261024-000002-bbbb")
        self.assertEqual(res_beta["sessions"][0]["project"], "beta")

        # Filtered by nonexistent project returns 0
        code, res_gamma = self.request("/api/sessions?project=gamma")
        self.assertEqual(code, 200)
        self.assertEqual(len(res_gamma["sessions"]), 0)


class RuntimeContextTests(unittest.TestCase):
    def test_selected_project_receives_fresh_resume_decision(self):
        agents = {engine.ORCHESTRATOR: engine.AgentSpec(engine.ORCHESTRATOR, "test", "system", 5, [])}
        resumed = {"continuation":{"action":"inspect_jobs","running_job_ids":["existing-job"]},
                   "state":{"next_action":"inspect saved changes"},"background_jobs":[],"uncommitted":[]}
        plan = {"slug":"example-project","revision":"current","tasks":[],"state":{},"approval":{"status":"pending"}}
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(engine,"load_agents",return_value=agents),patch.object(engine,"secret",return_value="dummy"), \
                 patch.object(engine,"AGENT_NOTES",Path(temp)),patch.object(studio,"routing",return_value=None), \
                 patch.object(studio,"plan_get",return_value=plan),patch.object(engine.Engine,"bridge",return_value=json.dumps(resumed)) as bridge:
                e = engine.Engine(lambda event:None,project="example-project")
        bridge.assert_called_once_with("/project/resume",{"slug":"example-project"})
        context = e.agents[engine.ORCHESTRATOR].system
        self.assertIn("FRESH CONTINUATION CONTEXT",context)
        self.assertIn("existing-job",context)
        self.assertIn("current",context)

    def test_assigned_skills_plan_tools_and_canvas_restrictions_reach_runtime(self):
        read = engine.Tool("pc_read_file", "Read", "Read a file", "bridge")
        write = engine.Tool("pc_write_file", "Write", "Write a file", "bridge")
        build = engine.Tool("delegate_build", "Build", "Build", "agent", agent="Build Agent")
        qa = engine.Tool("delegate_qa", "QA", "QA", "agent", agent="QA Agent")
        agents = {engine.ORCHESTRATOR: engine.AgentSpec(engine.ORCHESTRATOR, "test", "system", 5, [read, write, build, qa]),
                  "Build Agent": engine.AgentSpec("Build Agent", "test", "system", 5, [read, write]),
                  "QA Agent": engine.AgentSpec("QA Agent", "test", "system", 5, [read])}
        with tempfile.TemporaryDirectory() as temp:
            notes = Path(temp)
            (notes / "Build.md").write_text("---\nagent: Build Agent\nskills:\n  - test-engineering\n---\n# Build\n")
            with patch.object(engine, "load_agents", return_value=agents), patch.object(engine, "secret", return_value="dummy"), \
                 patch.object(engine, "AGENT_NOTES", notes), \
                 patch.object(studio, "routing", return_value={"name": "Test.canvas", "allowed": ["Build Agent"], "connections": []}):
                e = engine.Engine(lambda ev: None)
        delegated = [t.agent for t in e.agents[engine.ORCHESTRATOR].tools if t.kind == "agent"]
        self.assertEqual(delegated, ["Build Agent"])
        self.assertIn("test-engineering", e.agents["Build Agent"].system)
        self.assertIn("read_project_plan", [t.name for t in e.agents["QA Agent"].tools])
        self.assertNotIn("update_plan_task", [t.name for t in e.agents["QA Agent"].tools])
        self.assertIn("update_plan_task", [t.name for t in e.agents["Build Agent"].tools])


if __name__ == "__main__":
    unittest.main()
