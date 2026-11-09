import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codetools
import server


class ApiEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.slug = "endpoint-test-proj"
        self.project_dir = self.workspace / self.slug
        self.project_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(["git", "init", "-b", "main"], cwd=self.project_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.local"], cwd=self.project_dir, check=True)
        (self.project_dir / "PROJECT.md").write_text("# Test\n")
        subprocess.run(["git", "add", "-A"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.project_dir, check=True)

        self.orig_workspace = codetools.WORKSPACE
        codetools.WORKSPACE = str(self.workspace)

    def tearDown(self):
        codetools.WORKSPACE = self.orig_workspace
        self.temp_dir.cleanup()

    def test_isolated_api_lifecycle(self):
        # Create box
        c_res = codetools.create_isolated_box(self.slug, "box-1")
        self.assertTrue(c_res.get("ok"))

        # Write box
        w_res = codetools.write_isolated_box(self.slug, "box-1", "file.txt", "hello box")
        self.assertTrue(w_res.get("ok"))

        # List box
        l_res = codetools.list_isolated_box(self.slug, "box-1")
        self.assertTrue(l_res.get("ok"))
        self.assertIn("file.txt", l_res.get("files", []))

        # Merge box
        m_res = codetools.merge_isolated_box(self.slug, "box-1")
        self.assertTrue(m_res.get("ok"))
        self.assertEqual((self.project_dir / "file.txt").read_text(), "hello box")

    def test_branch_api_lifecycle(self):
        # Initial status
        st1 = codetools.get_branch_change_status(self.slug)
        self.assertEqual(st1.get("default_branch"), "main")
        self.assertFalse(st1.get("pending_approval"))

        # Create branch
        br_res = codetools.create_change_branch(self.slug, "agent/test-feat")
        self.assertTrue(br_res.get("ok"))

        (self.project_dir / "PROJECT.md").write_text("# Test Updated\n")
        codetools.commit_change_branch(self.slug, "feat: update")

        # Status should show pending approval
        st2 = codetools.get_branch_change_status(self.slug)
        self.assertTrue(st2.get("pending_approval"))
        self.assertEqual(st2.get("current_branch"), "agent/test-feat")

        # Merge approval
        m_res = codetools.merge_change_branch(self.slug, "agent/test-feat", approve=True)
        self.assertTrue(m_res.get("ok"))
        self.assertTrue(m_res.get("merged"))


if __name__ == "__main__":
    unittest.main()
