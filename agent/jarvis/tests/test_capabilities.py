"""Growth pack, continuation and project creation regressions; all writes isolated."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capability_pack
import forms
import mesh
import studio
from projectdata import continuation, parse_tasks, revision
from test_reliability import pc


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.plan = "| T1 | M1 | Done | ✅ |\n| T2 | M1 | Finish feature | pending |\n"
        self.tasks = parse_tasks(self.plan)

    def decision(self, state=None, jobs=None, changes=None):
        return continuation(state or {}, self.tasks, jobs or [], changes or [], revision(self.plan))

    def test_jobs_and_interrupted_changes_precede_new_task(self):
        self.assertEqual(self.decision(jobs=[{"id":"job1","running":True}], changes=[" M src/app.py"])["action"], "inspect_jobs")
        self.assertEqual(self.decision(changes=[" M src/app.py"])["action"], "inspect_changes")
        self.assertEqual(self.decision()["next_task"]["id"], "T2")

    def test_stale_checkpoint_does_not_reopen_completed_task(self):
        result = self.decision({"next_action":"Implement T1"})
        self.assertTrue(result["checkpoint_needs_review"])
        self.assertEqual(result["next_task"]["id"], "T2")
        self.assertEqual(result["plan_revision"], revision(self.plan))

    def test_done_and_blocked_need_review(self):
        self.assertEqual(self.decision({"status":"🔴 blocked"})["action"], "review_blocker")
        done = copy.deepcopy(self.tasks)
        for task in done: task["done"] = True
        self.assertEqual(continuation({}, done, [], [], "revision")["action"], "verify_completion")
        self.assertEqual(continuation({}, [], [], [], "revision")["action"], "review_intake")

    def test_bridge_resumes_jobs_in_project_subfolders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "test-project"
            project.mkdir()
            class Process:
                def poll(self): return None
            jobs = {"mine":{"proc":Process(),"cmd":["build"],"cwd":str(project/"src"),"started":1},
                    "other":{"proc":Process(),"cmd":["other"],"cwd":str(root/"another-project"),"started":2}}
            with patch.object(pc,"WORKSPACE",root), patch.object(pc,"PROTECTED",[]), patch.object(pc,"JOBS",jobs), \
                 patch.object(pc,"_archived_jobs",return_value={}), patch.object(pc.subprocess,"run") as run:
                run.return_value.stdout = ""
                result = pc.h_project_resume({"slug":"test-project"})
            self.assertEqual(result["continuation"]["running_job_ids"], ["mine"])


class ProjectCreationTests(unittest.TestCase):
    def test_duplicate_or_invalid_create_never_calls_initializer(self):
        calls = []
        def bridge(route, body):
            calls.append(route)
            return {"folders":["existing-project"]}
        self.assertFalse(forms.project_create({"slug":"existing-project","title":"Existing"},bridge)["ok"])
        self.assertNotIn("/project/init",calls)
        self.assertFalse(forms.project_create({"slug":"new-project","title":[]},bridge)["ok"])
        self.assertFalse(forms.project_create({"slug":"new-project","title":" "},bridge)["ok"])

    def test_bridge_create_only_does_not_change_existing_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root/"test-project"
            project.mkdir()
            marker = project/"PROJECT.md"
            marker.write_text("Keep my project")
            with patch.object(pc,"WORKSPACE",root),patch.object(pc,"PROTECTED",[]):
                result = pc.h_project_init({"slug":"test-project","create_only":True})
            self.assertIn("already exists",result["error"])
            self.assertEqual(marker.read_text(),"Keep my project")


class CapabilityPackTests(unittest.TestCase):
    def test_install_preserves_customizations_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            notes = root/"Agents"
            shutil.copytree(mesh.AGENT_NOTES,notes)
            for label,*_ in capability_pack.ROLES:
                (notes/(label+" Agent.md")).unlink(missing_ok=True)
            (root/"Flows").mkdir()
            canvas = {"nodes":[{"id":"custom","type":"text","x":10,"y":20,"width":200,"height":100,"text":"Keep my instructions","custom":True},
                              {"id":"lead","type":"file","file":"_DevPilot/Agents/Orchestrator.md","x":0,"y":200,"width":200,"height":100}],"edges":[],"extension":"preserve"}
            path = root/"Flows/Custom.canvas"
            path.write_text(json.dumps(canvas))
            (root/"jarvis-studio.json").write_text(json.dumps({"active_flow":"Custom.canvas"}))
            with patch.object(mesh,"SYS",root),patch.object(mesh,"AGENT_NOTES",notes),patch.object(mesh,"rebuild",return_value={"ok":True,"output":"fixture"}):
                result = capability_pack.install()
                after = path.read_text()
                self.assertEqual(result["agents"],14)
                self.assertEqual(capability_pack.install()["changed_files"],0)
                self.assertEqual(path.read_text(),after)
                saved = json.loads(after)
                self.assertEqual(saved["nodes"][0],canvas["nodes"][0])
                self.assertEqual(saved["extension"],"preserve")
                self.assertEqual(len(studio.routing()["allowed"]),8)

    def test_failed_rebuild_rolls_back_added_agents_skills_and_canvas(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            notes = root/"Agents"
            shutil.copytree(mesh.AGENT_NOTES,notes)
            for label,*_ in capability_pack.ROLES:
                (notes/(label+" Agent.md")).unlink(missing_ok=True)
            original = {path.name:path.read_bytes() for path in notes.glob("*.md")}
            with patch.object(mesh,"SYS",root),patch.object(mesh,"AGENT_NOTES",notes),patch.object(mesh,"rebuild",return_value={"ok":False,"output":"broken"}):
                with self.assertRaises(RuntimeError): capability_pack.install()
                self.assertEqual({path.name:path.read_bytes() for path in notes.glob("*.md")},original)
                self.assertEqual(mesh.skills(),[])


if __name__ == "__main__":
    unittest.main()
