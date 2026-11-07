"""Tests for the super-upgrade modules: telemetry, context diet, brain, adaptive gate, skills v2, queue."""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "workflow"))

import brain  # noqa: E402
import diet  # noqa: E402
import telemetry  # noqa: E402
from orchestration import RequestGate  # noqa: E402


class TelemetryTests(unittest.TestCase):
    def test_spans_blobs_and_usage_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            usage = Path(d) / "_usage.jsonl"
            t = telemetry.Trace(Path(d) / "s1", session="s1", project="p", usage_file=usage, turn=1)
            msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
            t.model_call("A", "m/x", msgs, 100, 20, False, ms=5)
            t.model_call("A", "m/x", msgs + [{"role": "assistant", "content": "ok"}], 120, 10, True, ms=5)
            span = t.tool_call("A", "Read", {"path": "x"}, "x" * 50000, True, 3)
            self.assertEqual(t.snapshot()["prompt"], 220)
            # identical messages are stored once
            self.assertEqual(len(list((Path(d) / "s1" / "blobs").glob("*.txt"))), 4)
            self.assertEqual(len(telemetry.read_blob(Path(d) / "s1", span["output"])), 50000)
            self.assertEqual(telemetry.find_blob(d, span["output"])[:3], "xxx")
            spans = telemetry.read_trace(Path(d) / "s1", turn=1)
            self.assertEqual([s["kind"] for s in spans], ["model_call", "model_call", "tool_call"])
            summary = telemetry.usage_summary(usage)
            self.assertEqual(summary["today"]["prompt"], 220)
            self.assertEqual(summary["by_project"]["p"], 250)

    def test_blob_ids_are_validated(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                telemetry.read_blob(d, "../../etc/passwd")


class DietTests(unittest.TestCase):
    def test_smart_truncate_keeps_head_tail_and_errors(self):
        text = "HEAD\n" + "\n".join(f"line {i}" for i in range(5000)) + "\nTypeError: boom\n" + \
               "\n".join(f"more {i}" for i in range(5000)) + "\nTAIL"
        out = diet.smart_truncate(text, 4000)
        self.assertLess(len(out), 4600)
        self.assertTrue(out.startswith("HEAD"))
        self.assertTrue(out.endswith("TAIL"))
        self.assertIn("TypeError: boom", out)

    def test_mask_keeps_recent_results_and_does_not_mutate(self):
        msgs = [{"role": "system", "content": "s"}]
        for i in range(4):
            msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"result {i}\n" + "x" * 2000})
        view = diet.mask_observations(msgs, {f"c{i}": f"b{i}" for i in range(4)}, keep_last=2)
        self.assertIn("blob b0", view[1]["content"])
        self.assertIn("blob b1", view[2]["content"])
        self.assertTrue(view[3]["content"].startswith("result 2"))
        self.assertTrue(msgs[1]["content"].startswith("result 0"))
        self.assertLess(diet.prompt_chars(view), diet.prompt_chars(msgs))

    def test_fold_history_uses_cache_and_falls_back(self):
        hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(20)]
        calls = []
        cache = {}
        out, key = diet.fold_history(hist, 6, lambda older: calls.append(1) or "SUMMARY", cache)
        self.assertEqual(len(out), 8)
        self.assertIn("SUMMARY", out[0]["content"])
        diet.fold_history(hist, 6, lambda older: calls.append(1) or "x", cache)
        self.assertEqual(len(calls), 1)
        out, _ = diet.fold_history(hist[:5], 6, None, {})
        self.assertEqual(len(out), 5)
        out, _ = diet.fold_history(hist, 6, lambda older: 1 / 0, {})
        self.assertIn("m0", out[0]["content"])

    def test_budget_warns_then_pauses_then_extends(self):
        b = diet.Budget(1000, 0)
        self.assertEqual(b.check(500)[0], None)
        self.assertEqual(b.check(850)[0], "warn")
        self.assertEqual(b.check(1001)[0], "pause")
        self.assertEqual(b.check(1200)[0], None)
        b.extend()
        self.assertEqual(b.max_tokens, 1500)

    def test_ledger_digest_is_bounded(self):
        mem = [{"id": f"t{i}", "state": "completed", "agent": "Build Agent", "task": "x" * 300} for i in range(200)]
        self.assertLessEqual(len(diet.ledger_digest(mem)), 2200)


class BrainTests(unittest.TestCase):
    def test_memory_roundtrip_and_recall(self):
        text = brain.MEMORY_HEADER + brain.memory_line("Use Prisma for the database", "decision") + \
            brain.memory_line("Tests run with vitest", "convention")
        entries = brain.parse_memory(text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(brain.recall(entries, "which database orm?")[0]["kind"], "decision")

    def test_memory_rejects_secrets(self):
        with self.assertRaises(ValueError):
            brain.memory_line("api_key = nvapi-abcdefghijklmnop1234", "fact")

    def test_failure_hints_and_repo_map(self):
        self.assertIn("dependency", brain.failure_hint("Error: Cannot find module 'react'"))
        self.assertEqual(brain.failure_hint("all good"), "")
        out = brain.format_repo_map("src/a.ts:3:export function foo() {\nsrc/a.ts:9:class Bar {\nb.py:1:def x():")
        self.assertIn("src/a.ts", out)
        self.assertIn("3: export function foo() {", out)
        self.assertNotIn("..", brain.repo_map_command("../../etc").split("--")[-1])

    def test_extracted_memories_skip_known_and_invalid(self):
        known = brain.parse_memory(brain.memory_line("Use Prisma", "decision"))
        reply = '[{"kind":"decision","text":"Use Prisma"},{"kind":"gotcha","text":"Port 3000 is used by Docker"},{"text":"x"}]'
        lines = brain.parse_extracted(reply, known)
        self.assertEqual(len(lines), 1)
        self.assertIn("(gotcha) Port 3000", lines[0])


class GateTests(unittest.TestCase):
    def test_concurrency_adapts_to_rate_limits(self):
        g = RequestGate(limit=2, spacing=0, max_limit=4, streak=3)
        for _ in range(3):
            g.on_success()
        self.assertEqual(g.limit, 3)
        g.on_rate_limit()
        g.on_rate_limit()
        g.on_rate_limit()
        self.assertEqual(g.limit, 1)
        g.configure(1)
        for _ in range(10):
            g.on_success()
        self.assertEqual(g.limit, 1)


class SkillsV2Tests(unittest.TestCase):
    def test_versions_rollback_tests_and_drafts(self):
        import skills2
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Skills" / "demo").mkdir(parents=True)
            (root / "Skills" / "demo" / "SKILL.md").write_text("---\ndescription: v1\n---\nbody one")
            with mock.patch.multiple(skills2, SKILLS=root / "Skills", VERSIONS=root / "Archive" / "v",
                                     DRAFTS=root / "Archive" / "d", TESTS=root / "tests.json"):
                stamp = skills2.snapshot("demo")
                (root / "Skills" / "demo" / "SKILL.md").write_text("---\ndescription: v2\n---\nbody two")
                self.assertEqual(len(skills2.versions("demo")), 1)
                skills2.rollback("demo", stamp)
                self.assertIn("body one", (root / "Skills" / "demo" / "SKILL.md").read_text())
                self.assertEqual(len(skills2.versions("demo")), 2)
                skills2.set_test("demo", "Try the demo")
                self.assertEqual(skills2.load_tests()["demo"], "Try the demo")
                draft = skills2.save_draft('{"name":"Fix Ports","description":"when ports clash","body":"1. check"}')
                self.assertEqual(draft["name"], "fix-ports")
                self.assertEqual(len(skills2.drafts()), 1)
                with self.assertRaises(ValueError):
                    skills2.save_draft("no json here")
                with self.assertRaises(ValueError):
                    skills2.version_get("demo", "../x")

    def test_usage_stats_from_traces(self):
        import skills2
        with tempfile.TemporaryDirectory() as d:
            t = telemetry.Trace(Path(d) / "s", session="s")
            t.tool_call("Build Agent", "Read Skill", {"name": "testing"}, "text", True, 1)
            t.tool_call("QA Agent", "Read Skill", {"name": "testing"}, "error", False, 1)
            t.tool_call("QA Agent", "List Skills", {}, "[]", True, 1)
            stats = skills2.usage_stats(d)
            self.assertEqual(stats["testing"]["reads"], 2)
            self.assertEqual(stats["testing"]["ok"], 1)


class QueueTests(unittest.TestCase):
    def test_queued_run_starts_when_session_is_free(self):
        import server
        started = threading.Event()

        class FakeSession:
            id, project, running = "q1", "", True
            def __init__(self):
                self.cond = threading.Condition()
                self.stop_requested, self.pause_requested = threading.Event(), threading.Event()
                self.next_seq, self.engine = 0, None
            def run(self, text, project, images=None):
                started.set()
            def emit(self, ev):
                return ev

        fake = FakeSession()
        with mock.patch.dict(server.LIVE, {"q1": fake}, clear=True), mock.patch.object(server, "QUEUE", []):
            server.enqueue("next task", "", "q1")
            server.dispatch_queue()
            self.assertFalse(started.is_set())
            fake.running = False
            server.dispatch_queue()
            self.assertTrue(started.wait(2))
            self.assertEqual(server.QUEUE, [])


if __name__ == "__main__":
    unittest.main()


class FanOutTests(unittest.TestCase):
    def test_sibling_delegations_run_concurrently(self):
        import engine
        e = engine.Engine.__new__(engine.Engine)
        e.stop = threading.Event()
        events, active, peak = [], [0], [0]
        lock = threading.Lock()
        e.emit = events.append

        def run_tool(agent, tool, args, depth):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(.3)
            with lock:
                active[0] -= 1
            return f"{tool.agent} done"
        e.run_tool = run_tool
        tools = {f"delegate_{n}": engine.Tool(f"delegate_{n}", n, "", "agent", agent=n) for n in ("a", "b", "c")}
        calls = [{"name": f"delegate_{n}", "args": json.dumps({"task": "t"}), "id": n} for n in ("a", "b", "c")]
        calls.append({"name": "delegate_a", "args": json.dumps({"task": "again"}), "id": "a2"})  # same agent: serialized
        t0 = time.time()
        out = e._fan_out(engine.AgentSpec("Coord", "m", "", 1, []), calls, tools, 0)
        self.assertLess(time.time() - t0, .8)
        self.assertEqual(peak[0], 3)
        self.assertEqual(sorted(out), [0, 1, 2])
        self.assertEqual(out[1][0], "b done")
        self.assertEqual(events[0]["type"], "fanout")

    def test_single_delegation_is_left_sequential(self):
        import engine
        e = engine.Engine.__new__(engine.Engine)
        tools = {"delegate_a": engine.Tool("delegate_a", "a", "", "agent", agent="a")}
        self.assertEqual(e._fan_out(engine.AgentSpec("C", "m", "", 1, []),
                                    [{"name": "delegate_a", "args": '{"task":"x"}', "id": "1"}], tools, 0), {})


class AutoResumeTests(unittest.TestCase):
    def _engine(self):
        import engine
        e = engine.Engine.__new__(engine.Engine)
        e.stop, e.pause_requested = threading.Event(), threading.Event()
        e.budget = diet.Budget(100, 0)
        e.events = []
        e.emit = e.events.append
        return e

    def test_budget_pause_resumes_by_itself(self):
        e = self._engine()
        e.budget.check(150)            # trips the budget
        e.pause_requested.set()
        e._schedule_auto_resume(0.05)
        time.sleep(0.25)
        self.assertFalse(e.pause_requested.is_set())
        self.assertEqual(e.events[-1]["state"], "auto_resumed")

    def test_keep_paused_cancels_auto_resume(self):
        e = self._engine()
        e.budget.check(150)
        e.pause_requested.set()
        e._schedule_auto_resume(0.1)
        e.hold_auto_resume()
        time.sleep(0.25)
        self.assertTrue(e.pause_requested.is_set())


class AutoContinueTests(unittest.TestCase):
    def test_step_limit_schedules_continue_and_user_message_cancels(self):
        import server
        s = server.Session("autotest-1")
        s.project, events = "demo", []
        s.emit = lambda ev: events.append(ev) or ev
        started = []
        with mock.patch.object(server.runtime_settings, "get", return_value={"auto_continue": True, "auto_continue_max": 2}), \
             mock.patch.object(server, "start_turn", lambda sess, text, project, auto=False: started.append((text, auto)) or (200, {})), \
             mock.patch.object(server.threading, "Timer") as timer:
            s._maybe_auto_continue("limit")
            self.assertEqual(events[-1]["state"], "scheduled")
            fire = timer.call_args[0][1]
            fire()
            self.assertEqual(started, [("Continue project demo from its saved checkpoint.", True)])
            s._maybe_auto_continue("limit")
            self.assertTrue(s.cancel_auto_continue())
            timer.call_args[0][1]()          # cancelled: must not start
            self.assertEqual(len(started), 1)
            s._maybe_auto_continue("limit")
            self.assertEqual(events[-1]["state"], "exhausted")
            s._maybe_auto_continue("stopped")
            self.assertEqual(events[-1]["state"], "exhausted")

    def test_transient_classification(self):
        import server
        import urllib.error
        self.assertTrue(server._transient(urllib.error.HTTPError("u", 429, "rate", {}, None)))
        self.assertFalse(server._transient(urllib.error.HTTPError("u", 401, "auth", {}, None)))
        self.assertTrue(server._transient(RuntimeError("model call failed after retries: x")))
        self.assertFalse(server._transient(ValueError("select an existing project")))


class CompactionTests(unittest.TestCase):
    def _run(self, steps=12):
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
        for i in range(steps):
            msgs.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": f"c{i}", "type": "function", "function": {"name": "pc_read_file", "arguments": f'{{"path":"f{i}"}}'}}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"content {i} " + "x" * 3000})
        return msgs

    def test_boundary_keeps_tool_results_with_their_calls(self):
        msgs = self._run()
        cut = diet.compact_boundary(msgs, 2)
        self.assertEqual(msgs[cut]["role"], "assistant")
        self.assertIsNone(diet.compact_boundary(self._run(2), 2))

    def test_engine_compacts_view_but_keeps_full_history(self):
        import engine
        e = engine.Engine.__new__(engine.Engine)
        e.settings = {"compact_at_tokens": 1000}
        e._tl = threading.local(); e._tl.last_prompt = 5000
        e.events = []; e.emit = e.events.append
        e.quick = lambda prompt, **kw: "- read f0..f7\n- next: finish"
        msgs, state = self._run(), {}
        e._maybe_compact(engine.AgentSpec("Build Agent", "m", "", 1, []), msgs, 2, state)
        view = diet.compacted_view(msgs, 2, state)
        self.assertEqual(len(msgs), 26)                       # nothing removed from the saved history
        self.assertLess(len(view), len(msgs))
        self.assertIn("Context compacted", view[2]["content"])
        self.assertEqual(view[3]["role"], "assistant")
        self.assertEqual(e.events[-1]["type"], "context")
        e._tl.last_prompt = 10
        before = dict(state)
        e._maybe_compact(engine.AgentSpec("B", "m", "", 1, []), msgs, 2, state)
        self.assertEqual(state, before)                       # under the limit: untouched

    def test_fold_shrinks_long_recent_history(self):
        hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": "y" * 9000} for i in range(12)]
        out, key = diet.fold_history(hist, 12, lambda older: "S", {}, max_chars=40000)
        self.assertIsNotNone(key)
        self.assertLessEqual(sum(len(m["content"]) for m in out[2:]), 40000)


try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    Image = None
    ImageDraw = None
    HAS_PIL = False


class MediaTests(unittest.TestCase):
    def _png(self, size=(2400, 1200), color="red"):
        if HAS_PIL:
            import io
            buf = io.BytesIO()
            Image.new("RGB", size, color).save(buf, "PNG")
            return buf.getvalue()
        import struct, zlib
        w, h = size
        row = b"\x00" + b"\xff\x00\x00" * w
        compressed = zlib.compress(row * h)
        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")

    def test_upload_is_validated_downscaled_and_deduplicated(self):
        import media
        with tempfile.TemporaryDirectory() as d:
            a = media.save_upload(d, self._png())
            b = media.save_upload(d, self._png())
            self.assertEqual(a["id"], b["id"])
            self.assertEqual(max(a["width"], a["height"]), media.MAX_SIDE)
            self.assertTrue(media.upload_path(d, a["id"]).exists())
            with self.assertRaises(ValueError):
                media.save_upload(d, b"not an image")
            with self.assertRaises(ValueError):
                media.upload_path(d, "../../etc/passwd")
            data = media.decode_data_url("data:image/png;base64," + __import__("base64").b64encode(self._png((10, 10))).decode())
            self.assertTrue(data.startswith(b"\x89PNG"))

    def test_project_images_stay_inside_the_project(self):
        import media
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"; (root / "public").mkdir(parents=True)
            (root / "public" / "logo.png").write_bytes(self._png((20, 20)))
            (root / "notes.txt").write_text("x")
            (Path(d) / "secret.png").write_bytes(self._png((5, 5)))
            self.assertEqual(media.project_image(root, "public/logo.png").name, "logo.png")
            with self.assertRaises(PermissionError):
                media.project_image(root, "../secret.png")
            with self.assertRaises(ValueError):
                media.project_image(root, "notes.txt")

    def test_vision_part_is_small_jpeg(self):
        import media
        part = media.as_part(self._png())
        self.assertTrue(part["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertLess(len(part["image_url"]["url"]), 200_000)

    def test_preview_urls_from_dev_server_output(self):
        import media
        out = "  VITE v6  ready\n  ➜  Local:   http://localhost:5173/\n  ➜  Network: use --host\nready - started server on 0.0.0.0:3000, url: http://0.0.0.0:3000"
        self.assertEqual(media.preview_urls(out), ["http://localhost:5173", "http://127.0.0.1:3000"])

    @unittest.skipUnless(HAS_PIL, "PIL required for analyze script")
    def test_analyze_script_stats_and_compare(self):
        import media
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            a, b, diff = Path(d) / "a.png", Path(d) / "b.png", Path(d) / "diff.png"
            Image.new("RGB", (100, 50), "white").save(a)
            im = Image.new("RGB", (100, 50), "white"); ImageDraw.Draw(im).rectangle((10, 10, 29, 29), fill="black"); im.save(b)
            stats = json.loads(subprocess.run(["python3", "-c", media.ANALYZE_SCRIPT, "stats", str(b)], capture_output=True, text=True, check=True).stdout)
            self.assertEqual(stats["size"], [100, 50])
            self.assertEqual(stats["palette"][0]["hex"], "#ffffff")
            self.assertGreater(stats["contrast_top_two"], 20)
            cmp_ = json.loads(subprocess.run(["python3", "-c", media.ANALYZE_SCRIPT, "compare", str(a), str(b), str(diff)], capture_output=True, text=True, check=True).stdout)
            self.assertEqual(cmp_["changed_pixels"], 400)
            self.assertEqual(cmp_["changed_box"], [10, 10, 30, 30])
            self.assertTrue(diff.exists())

    def test_task_with_images_goes_to_the_model_as_content_parts(self):
        import engine
        e = engine.Engine.__new__(engine.Engine)
        e.stop, e.pause_requested = threading.Event(), threading.Event()
        e.emit = lambda ev: None
        seen = {}
        def chat(agent, messages, tools):
            seen["user"] = messages[-1]
            return "ok", []
        e.chat = chat
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "x.png"; img.write_bytes(self._png((40, 40)))
            out = e.run_agent(engine.AgentSpec("Coord", "m", "sys", 2, []), "what is this?", [], images=[str(img)])
        self.assertEqual(out, "ok")
        parts = seen["user"]["content"]
        self.assertEqual(parts[0]["type"], "text")
        self.assertIn("what is this?", parts[0]["text"])
        self.assertEqual(parts[1]["type"], "image_url")
