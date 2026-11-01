"""Isolated tests: no user projects, model credits or real service mutations."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import studio
import engine
import mesh
import skill_pack


class MemoryBridge:
    def __init__(self):
        self.files = {}

    def __call__(self, path, body):
        if path == "/project/list":
            return {"folders": ["example-project"]}
        file = body.get("path", "")
        if path == "/fs/read":
            return {"content": self.files[file]} if file in self.files else {"error": "FileNotFoundError: No such file"}
        if path == "/fs/write":
            self.files[file] = body["content"]
            return {"bytes": len(body["content"])}
        raise AssertionError(f"unexpected bridge request: {path}")


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(mesh, "SYS", self.root)
        self.patch.start()
        self.bridge = MemoryBridge()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp.cleanup)

    def canvas(self):
        return {"nodes": [{"id": "n1", "type": "text", "text": "Original", "x": 0, "y": 0,
                           "width": 300, "height": 180, "extension": {"preserve": True}}], "edges": []}

    def plan(self, content):
        return studio.plan_save(self.bridge, {"slug": "example-project", "revision": studio.revision(""),
                                               "content": content})

    def test_canvas_round_trip_preserves_extensions(self):
        result = studio.flow_save({"name": "My canvas.canvas", "canvas": self.canvas()})
        self.assertTrue(result["ok"])
        saved = studio.flow_get("My canvas.canvas")
        self.assertEqual(saved["canvas"], self.canvas())
        self.assertFalse(saved["readonly"])
        self.assertTrue(studio.flow_create({"name": "Copy", "source": saved["name"]})["ok"])
        self.assertEqual(studio.flow_get("Copy.canvas")["canvas"], self.canvas())

    def test_canvas_conflict_preserves_obsidian_edit(self):
        studio.flow_save({"name": "Shared.canvas", "canvas": self.canvas()})
        loaded = studio.flow_get("Shared.canvas")
        path = self.root / "Flows" / "Shared.canvas"
        external = copy.deepcopy(self.canvas())
        external["nodes"][0]["text"] = "Changed in Obsidian"
        path.write_text(json.dumps(external))
        result = studio.flow_save({**loaded, "canvas": self.canvas()})
        self.assertTrue(result["conflict"])
        self.assertEqual(json.loads(path.read_text()), external)

    def test_canvas_boundary_and_generated_protection(self):
        for name in ("../outside.canvas", "/tmp/out.canvas", "a/inside.canvas"):
            with self.assertRaises(ValueError):
                studio.flow_get(name)
        self.assertFalse(studio.flow_save({"name": "DevPilot Flow.canvas", "canvas": self.canvas()})["ok"])
        bad = self.canvas()
        bad["nodes"][0].update(type="file", file="../../secrets")
        with self.assertRaises(ValueError):
            studio.validate_canvas(bad)

    def test_invalid_graphs_are_rejected(self):
        cases = []
        bad = self.canvas(); bad["nodes"].append(copy.deepcopy(bad["nodes"][0])); cases.append(bad)
        bad = self.canvas(); bad["nodes"][0]["x"] = math.nan; cases.append(bad)
        bad = self.canvas(); bad["nodes"][0]["height"] = -1; cases.append(bad)
        bad = self.canvas(); bad["edges"] = [{"id": "e1", "fromNode": "n1", "toNode": "missing"}]; cases.append(bad)
        for bad in cases:
            with self.subTest(canvas=bad), self.assertRaises(ValueError):
                studio.validate_canvas(bad)

    def test_routing_uses_only_linked_agent_cards_and_fails_closed(self):
        agents = [{"file": "Build Agent.md", "name": "Build Agent", "orchestrator": False}]
        canvas = self.canvas()
        canvas["nodes"].append({"id": "agent", "type": "file", "file": "_DevPilot/Agents/Build Agent.md",
                                 "x": 400, "y": 0, "width": 300, "height": 200})
        canvas["edges"] = [{"id": "e1", "fromNode": "n1", "toNode": "agent", "label": "implement"}]
        studio.flow_save({"name": "Routing.canvas", "canvas": canvas})
        with patch.object(mesh, "notes", return_value=agents):
            self.assertTrue(studio.flow_activate({"name": "Routing.canvas"})["ok"])
            route = studio.routing()
            self.assertEqual(route["allowed"], ["Build Agent"])
            self.assertEqual(route["connections"][0]["label"], "implement")
        (self.root / "Flows" / "Routing.canvas").unlink()
        with self.assertRaises(FileNotFoundError):
            studio.routing()
        self.assertTrue(studio.flow_activate({"name": ""})["ok"])
        self.assertIsNone(studio.routing())

    def test_task_updates_preserve_canonical_markdown(self):
        content = "# Plan\n\n| T1 | M1 | Build UI | src/ | Build passes | AC-1 |\n| T2 ✅ | M1 | Test UI | tests/ | Pass | AC-1 |\n\n## M2 API\n- [ ] Contract test\n"
        result = self.plan(content)
        self.assertTrue(result["ok"])
        plan = result["plan"]
        self.assertEqual(plan["progress"], {"done": 1, "total": 3})
        self.assertEqual(plan["tasks"][2]["milestone"], "M2 API")
        task = plan["tasks"][0]
        changed = studio.plan_task(self.bridge, {"slug": "example-project", "revision": plan["revision"],
                                                 "line": task["line"], "done": True})
        self.assertTrue(changed["plan"]["tasks"][0]["done"])
        self.assertIn("| T1 ✅ | M1 | Build UI | src/ | Build passes | AC-1 |", changed["plan"]["content"])
        stale = studio.plan_task(self.bridge, {"slug": "example-project", "revision": plan["revision"],
                                               "line": task["line"], "done": False})
        self.assertTrue(stale["conflict"])
        unchecked = studio.plan_task(self.bridge, {"slug": "example-project", "revision": changed["revision"],
                                                   "line": task["line"], "done": False})
        self.assertFalse(unchecked["plan"]["tasks"][0]["done"])

    def test_approval_is_bound_to_exact_revision(self):
        plan = self.plan("# Plan\n- [ ] Implement feature\n")["plan"]
        approval = studio.plan_approval(self.bridge, {"slug": "example-project", "revision": plan["revision"], "status": "approved"})
        self.assertTrue(approval["ok"])
        self.assertEqual(studio.plan_get(self.bridge, "example-project")["approval"]["status"], "approved")
        changed = studio.plan_save(self.bridge, {"slug": "example-project", "revision": plan["revision"],
                                                 "content": "# Plan\n- [ ] Implement another feature\n"})
        self.assertEqual(changed["plan"]["approval"]["status"], "outdated")
        self.assertTrue(studio.plan_approval(self.bridge, {"slug": "example-project", "revision": plan["revision"],
                                                         "status": "approved"})["conflict"])

    def test_plan_conflicts_and_project_boundary(self):
        self.plan("# Plan\n- [ ] Task\n")
        with self.assertRaises(ValueError):
            studio.plan_get(self.bridge, "../outside")
        with self.assertRaises(ValueError):
            studio.plan_get(self.bridge, "nonexistent-project")
        result = studio.plan_save(self.bridge, {"slug": "example-project", "content": "overwrite", "revision": "wrong"})
        self.assertTrue(result["conflict"])
        self.assertEqual(studio.plan_get(self.bridge, "example-project")["content"], "# Plan\n- [ ] Task\n")


class RunControlTests(unittest.TestCase):
    def engine(self):
        e = engine.Engine.__new__(engine.Engine)
        e.stop, e.pause_requested, e.paused = threading.Event(), threading.Event(), threading.Event()
        e.events = []
        e.emit = e.events.append
        return e

    def test_pause_prevents_next_operation_until_resumed(self):
        e = self.engine()
        e.pause_requested.set()
        reached = threading.Event()
        t = threading.Thread(target=lambda: (e.checkpoint_control(), reached.set()), daemon=True)
        t.start()
        self.assertTrue(e.paused.wait(1))
        self.assertFalse(reached.is_set())
        e.pause_requested.clear()
        t.join(1)
        self.assertTrue(reached.is_set())
        self.assertEqual([x["state"] for x in e.events], ["paused", "running"])

    def test_stop_releases_a_paused_run(self):
        e = self.engine()
        e.pause_requested.set()
        stopped = threading.Event()
        def run():
            try:
                e.checkpoint_control()
            except engine.Stopped:
                stopped.set()
        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.assertTrue(e.paused.wait(1))
        e.stop.set()
        t.join(1)
        self.assertTrue(stopped.is_set())
        self.assertFalse(e.paused.is_set())

    def test_stop_is_checked_before_tool_or_model_work(self):
        e = self.engine()
        e.stop.set()
        with self.assertRaises(engine.Stopped):
            e.checkpoint_control()


if __name__ == "__main__":
    unittest.main()
