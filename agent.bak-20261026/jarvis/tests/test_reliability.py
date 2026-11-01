"""Regression checks for persistence, runtime failures, settings and bridge behavior."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import engine
import control
import forms
import mesh
import codetools
from projectdata import revision, parse_tasks

bridge_path = Path(__file__).resolve().parents[2] / "bridge" / "pc_bridge.py"
spec = importlib.util.spec_from_file_location("test_pc_bridge", bridge_path)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(server, "SESSIONS", Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp.cleanup)

    def test_retention_never_resets_event_cursor(self):
        session = server.Session("retention")
        with patch.object(server, "MAX_EVENTS", 3):
            for i in range(8):
                session.emit({"type": "token", "text": str(i)})
        self.assertEqual([e["seq"] for e in session.events], [5, 6, 7])
        self.assertEqual(session.next_seq, 8)
        session.save()
        loaded = server.Session.load("retention")
        loaded.emit({"type": "token", "text": "after restart"})
        self.assertEqual(loaded.events[-1]["seq"], 8)

    def test_interrupted_run_is_saved_and_recovered_once(self):
        session = server.Session("interrupted")
        session.project = "example-project"
        session.running = True
        session.messages.append({"role": "user", "content": "Build the feature"})
        session.emit({"type": "turn_start", "text": "Build the feature"})
        recovered = server.Session.load("interrupted")
        self.assertFalse(recovered.running)
        self.assertEqual(recovered.project, "example-project")
        self.assertIn("interrupted", recovered.messages[-1]["content"])
        self.assertEqual(len(server.Session.load("interrupted").messages), 2)

    def test_session_paths_and_identity_are_validated(self):
        for sid in ("../outside", "/tmp/secret", ["bad"], "", "a" * 81):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                server.get_session(sid, create=True)
        Path(self.temp.name, "named.json").write_text('{"id":"../other"}')
        with self.assertRaises(ValueError):
            server.Session.load("named")

    def test_concurrent_emit_ids_are_unique(self):
        session = server.Session("concurrent")
        threads = [threading.Thread(target=lambda: [session.emit({"type": "token", "text": "x"}) for _ in range(50)]) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join(3)
        self.assertEqual([e["seq"] for e in session.events], list(range(200)))


class Stream(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class EngineTests(unittest.TestCase):
    def engine(self):
        e = engine.Engine.__new__(engine.Engine)
        e.stop, e.paused, e.pause_requested = threading.Event(), threading.Event(), threading.Event()
        e.nim_key, e.events = "test-key", []
        e.emit = e.events.append
        return e

    def test_truncated_model_response_never_executes_tools(self):
        e = self.engine()
        chunk = b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"pc_shell","arguments":"{}"}}]}}]}\n\n'
        with patch.object(engine.urllib.request, "urlopen", return_value=Stream(chunk)):
            with self.assertRaises(engine.IncompleteStream):
                e._stream(engine.AgentSpec("A", "test", "system", 1, []), b"{}")

    def test_completed_stream_and_repeated_function_name(self):
        e = self.engine()
        chunks = [
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "read_file", "arguments": "{"}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "read_file", "arguments": "}"}}]}, "finish_reason": "tool_calls"}]}]
        raw = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"
        with patch.object(engine.urllib.request, "urlopen", return_value=Stream(raw)):
            _, calls = e._stream(engine.AgentSpec("A", "test", "system", 1, []), b"{}")
        self.assertEqual(calls[0]["name"], "read_file")
        self.assertEqual(calls[0]["args"], "{}")

    def model_stream(self, content="", calls=None, finish="stop"):
        delta = {"content":content}
        if calls: delta["tool_calls"] = calls
        return Stream(("data: " + json.dumps({"choices":[{"delta":delta,"finish_reason":finish}]}) + "\n\ndata: [DONE]\n\n").encode())

    def test_output_budget_and_model_specific_efficient_reasoning(self):
        e = self.engine()
        for model in ("nvidia/nemotron-3.5-super-vl-120b-a12b", "another/model"):
            with patch.object(e,"_stream",return_value=("Short reply",[])) as stream:
                e.chat(engine.AgentSpec("A",model,"system",1,[]),[{"role":"user","content":"test"}],[])
            body=json.loads(stream.call_args.args[1])
            self.assertEqual(body["max_tokens"],8192)
            self.assertEqual("reasoning_effort" in body,model.startswith("nvidia/nemotron-3.5"))
            self.assertNotIn("chat_template_kwargs",body)

    def test_length_retry_discards_partial_calls_then_executes_complete_call_once(self):
        e = self.engine()
        tool = engine.Tool("write","Write","Write","bridge",path="/fs/write")
        agent=engine.AgentSpec("A","nvidia/nemotron-3.5-super-vl-120b-a12b","system",3,[tool])
        truncated=[{"index":0,"id":"discarded","function":{"name":"write","arguments":'{"content":"unfinished'}}]
        complete=[{"index":0,"id":"valid","function":{"name":"write","arguments":"{}"}}]
        streams=[self.model_stream("Incomplete",truncated,"length"),self.model_stream("",complete,"tool_calls"),self.model_stream("Done.")]
        with patch.object(engine.urllib.request,"urlopen",side_effect=streams) as opened,patch.object(e,"run_tool",return_value='{"ok":true}') as run:
            result=e.run_agent(agent,"Do the work",[])
        self.assertEqual(result,"Done.")
        run.assert_called_once_with(agent,tool,{},0)
        self.assertEqual(opened.call_count,3)
        retried=json.loads(opened.call_args_list[1].args[0].data)
        self.assertEqual(retried["max_tokens"],16384)
        self.assertEqual(retried["chat_template_kwargs"],{"enable_thinking":False})
        self.assertNotIn("reasoning_effort",retried)
        self.assertFalse(any(message.get("tool_calls") for message in retried["messages"]))
        self.assertNotIn("unfinished",json.dumps(retried["messages"]))
        self.assertIn("COMPACT RESPONSES:",retried["messages"][0]["content"])
        self.assertEqual(sum(ev["type"]=="stream_reset" for ev in e.events),1)

    def test_repeated_length_has_one_retry_and_never_executes_tools(self):
        e=self.engine()
        tool=engine.Tool("write","Write","Write","bridge",path="/fs/write")
        agent=engine.AgentSpec("A","test","system",3,[tool])
        calls=[{"index":0,"function":{"name":"write","arguments":"{}"}}]
        with patch.object(engine.urllib.request,"urlopen",side_effect=[self.model_stream("",calls,"length"),self.model_stream("",calls,"length")]) as opened,patch.object(e,"run_tool") as run:
            with self.assertRaises(engine.OutputLimit):e.run_agent(agent,"test",[])
        self.assertEqual(opened.call_count,2)
        run.assert_not_called()

    def test_content_filter_is_not_retried(self):
        e=self.engine()
        with patch.object(engine.urllib.request,"urlopen",return_value=self.model_stream(finish="content_filter")) as opened:
            with self.assertRaisesRegex(RuntimeError,"content_filter"):e.chat(engine.AgentSpec("A","test","system",1,[]),[],[])
        self.assertEqual(opened.call_count,1)

    def test_compact_retry_can_be_stopped_before_another_request(self):
        e=self.engine()
        def emit(event):
            e.events.append(event)
            if event["type"]=="retry":e.stop.set()
        e.emit=emit
        with patch.object(e,"_stream",side_effect=engine.OutputLimit("limit")) as stream:
            with self.assertRaises(engine.Stopped):e.chat(engine.AgentSpec("A","test","system",1,[]),[],[])
        self.assertEqual(stream.call_count,1)

    def test_auth_failure_is_not_retried(self):
        e = self.engine()
        error = urllib.error.HTTPError("http://test", 401, "unauthorized", {}, None)
        with patch.object(e, "_stream", side_effect=error) as stream:
            with self.assertRaises(urllib.error.HTTPError):
                e.chat(engine.AgentSpec("A", "test", "system", 1, []), [], [])
        self.assertEqual(stream.call_count, 1)
        self.assertFalse(e.events)
        error.close()

    def test_retry_is_cancelable(self):
        e = self.engine()
        def fail(*args):
            e.stop.set()
            raise urllib.error.URLError("network unavailable")
        with patch.object(e, "_stream", side_effect=fail):
            with self.assertRaises(engine.Stopped):
                e.chat(engine.AgentSpec("A", "test", "system", 1, []), [], [])
        self.assertIn("stream_reset", [ev["type"] for ev in e.events])

    def test_invalid_arguments_cannot_call_bridge(self):
        e = self.engine()
        tool = engine.Tool("write", "Write", "Write", "bridge", path="/fs/write", params=[("path", "file", "string", None)])
        with patch.object(e, "bridge") as bridge:
            for args in ([], {"path": False}, {}):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    e.run_tool(None, tool, args, 0)
        bridge.assert_not_called()

    def test_failed_bridge_tool_is_shown_as_failed(self):
        e = self.engine()
        tool = engine.Tool("shell", "Shell", "Run", "bridge", path="/shell")
        agent = engine.AgentSpec("A", "test", "system", 2, [tool])
        replies = [("", [{"id": "c1", "name": "shell", "args": "{}"}]), ("Reported failure", [])]
        for result in ('{"exit_code":2,"stderr":"failed"}', '{"error":"not found"}'):
            e.events.clear()
            with patch.object(e, "chat", side_effect=replies), patch.object(e, "run_tool", return_value=result):
                e.run_agent(agent, "test", [])
            self.assertFalse(next(ev for ev in e.events if ev["type"] == "tool_end")["ok"])


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "example-project"
        self.project.mkdir()
        self.patches = [patch.object(pc, "WORKSPACE", self.root),
                        patch.object(pc, "PROTECTED", [self.root / "_DevPilot", self.root / ".obsidian"]),
                        patch.object(pc, "JOBS", {})]
        for p in self.patches: p.start()
        self.addCleanup(self.temp.cleanup)
        for p in self.patches: self.addCleanup(p.stop)

    def test_file_conflicts_and_create_do_not_overwrite(self):
        file = self.project / "file.txt"
        file.write_text("Original")
        old = pc.h_read({"path": str(file), "raw": True})
        file.write_text("External edit")
        conflict = pc.h_write({"path": str(file), "content": "Overwrite", "expected_revision": old["revision"]})
        self.assertTrue(conflict["conflict"])
        self.assertEqual(file.read_text(), "External edit")
        self.assertTrue(pc.h_write({"path": str(file), "content": "", "create_only": True})["conflict"])
        saved = pc.h_write({"path": str(file), "content": "Verified", "expected_revision": revision("External edit")})
        self.assertEqual(saved["revision"], revision("Verified"))

    def test_project_slug_and_symlink_boundary(self):
        for slug in ("../escape", "/tmp", "_DevPilot", ".obsidian"):
            with self.subTest(slug=slug), self.assertRaises((ValueError, PermissionError)):
                pc.h_project_resume({"slug": slug})
        (self.root / "linked-project").symlink_to(self.root.parent)
        with self.assertRaises(PermissionError):
            pc.h_project_checkpoint({"slug": "linked-project", "next_action": "escape"})
        with self.assertRaises(ValueError):
            pc.h_fetch({"url": "file:///etc/passwd"})

    def test_resume_handles_checkboxes_and_partial_journal(self):
        plan = self.project / "docs/plan/PLAN.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("# Plan\n## Milestone 1: Work\n- [x] Finished\n- [ ] Remaining\n| T1 | M2 | Table task | files | Verify | AC1 |\n")
        state = self.project / ".devpilot"
        state.mkdir()
        (state / "journal.jsonl").write_text('{"tool":"saved"}\n{"partial":')
        with patch.object(pc.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            result = pc.h_project_resume({"slug": "example-project"})
        self.assertEqual(result["plan_progress"], "1/3 tasks done")
        self.assertEqual(len(result["next_open_tasks"]), 2)
        self.assertEqual(result["recent_journal"], [{"tool": "saved"}])
        self.assertEqual(parse_tasks(plan.read_text())[0]["milestone"], "Milestone 1: Work")

    def test_timeout_terminates_command_and_reports_output(self):
        result = pc.run([sys.executable, "-c", "import time; print('started',flush=True); time.sleep(10)"], str(self.project), .1, False)
        self.assertIn("timed out", result["error"])
        self.assertIn("started", result["stdout"])

    def test_background_output_survives_bridge_restart(self):
        here = self.root / "bridge"
        here.mkdir()
        with patch.object(pc, "HERE", here):
            started = pc.run([sys.executable, "-c", "print('saved background output')"], str(self.project), 2, True)
            job_id = started["job_id"]
            pc.JOBS[job_id]["proc"].wait(timeout=2)
            self.assertEqual(pc.h_job({"id": job_id})["exit_code"], 0)
            pc.JOBS.clear()
            restored = pc.h_job({"id": job_id})
            self.assertEqual(restored["status"], "finished")
            self.assertIn("saved background output", restored["output"])
            self.assertEqual(pc.h_jobs_list({})["jobs"][0]["cwd"], str(self.project))

    def test_project_list_excludes_internal_and_unregistered_folders(self):
        (self.project / "PROJECT.md").write_text("# Real project")
        (self.root / "unrelated-folder").mkdir()
        self.assertEqual(pc.h_project_list({})["folders"], ["example-project"])


class SettingsTests(unittest.TestCase):
    def test_skill_rename_failure_restores_folder_and_exact_assignments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / "Skills/old-skill"
            old.mkdir(parents=True)
            original = "---\nname: old-skill\ndescription: Old skill\n---\n# Original instructions\n"
            (old / "SKILL.md").write_text(original)
            notes = root / "Agents"
            notes.mkdir()
            file = notes / "Build.md"
            file.write_text("original agent note")
            agent = {"file": "Build.md", "name": "Build Agent", "skills": ["old-skill"]}
            def agents():
                current = dict(agent)
                current["skills"] = ["new-skill"] if file.read_text() == "renamed" else ["old-skill"]
                return [current]
            def write(a, p): p.write_text("renamed" if a["skills"] else "unassigned")
            with patch.object(mesh, "SYS", root), patch.object(mesh, "AGENT_NOTES", notes), \
                 patch.object(mesh, "notes", side_effect=agents), patch.object(mesh, "_write", side_effect=write), \
                 patch.object(mesh, "rebuild", return_value={"ok": False, "output": "bad workflow"}):
                result = forms.skill_save({"name": "new-skill", "original_name": "old-skill", "description": "Changed", "body": "# New", "agents": []})
            self.assertFalse(result["ok"])
            self.assertFalse((root / "Skills/new-skill").exists())
            self.assertEqual((old / "SKILL.md").read_text(), original)
            self.assertEqual(file.read_text(), "original agent note")

    def test_service_failure_is_not_success(self):
        with patch.object(control, "_run", return_value=subprocess.CompletedProcess([], 1, "", "restart denied")):
            result = control.service_action("bridge", "restart")
        self.assertFalse(result["ok"])
        self.assertIn("restart denied", result["output"])

    def test_package_scripts_and_search_errors(self):
        calls = []
        def bridge(route, body):
            calls.append(body)
            if route == "/fs/read": return {"content": '{"scripts":{"test; echo injected":"echo safe"}}'}
            if route == "/fs/list": return {"entries": []}
            return {"exit_code": 2, "stderr": "invalid regex"}
        scripts = codetools.scripts(bridge, "example-project")
        self.assertEqual(scripts["scripts"][0]["run"], "npm run 'test; echo injected'")
        self.assertEqual(codetools.search(bridge, "example-project", "[", regex=True)["error"], "invalid regex")


if __name__ == "__main__":
    unittest.main()
