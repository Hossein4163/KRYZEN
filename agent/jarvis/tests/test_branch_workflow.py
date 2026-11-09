import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codetools


class BranchWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.slug = "test-git-project"
        self.project_dir = self.workspace / self.slug
        self.project_dir.mkdir(parents=True, exist_ok=True)

        # Initialize real git repo with default branch 'main'
        subprocess.run(["git", "init", "-b", "main"], cwd=self.project_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.project_dir, check=True)
        (self.project_dir / "PROJECT.md").write_text("# Test Git Project\n")
        (self.project_dir / "calc.py").write_text("def add(a, b): return a + b\n")
        subprocess.run(["git", "add", "-A"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=self.project_dir, check=True)

        self.orig_workspace = codetools.WORKSPACE
        codetools.WORKSPACE = str(self.workspace)

    def tearDown(self):
        codetools.WORKSPACE = self.orig_workspace
        self.temp_dir.cleanup()

    def test_detect_default_branch(self):
        branch = codetools.detect_default_branch(self.slug)
        self.assertEqual(branch, "main")

    def test_branch_per_change_and_approval_merge(self):
        # 1. Create dedicated branch for change
        branch_name = "agent/fix-calc"
        create_res = codetools.create_change_branch(self.slug, branch_name)
        self.assertTrue(create_res.get("ok"))

        # Verify current branch is branch_name
        curr = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.project_dir, capture_output=True, text=True).stdout.strip()
        self.assertEqual(curr, branch_name)

        # 2. Make change and commit
        (self.project_dir / "calc.py").write_text("def add(a, b): return a + b + 0\n")
        commit_res = codetools.commit_change_branch(self.slug, "fix: calc update")
        self.assertTrue(commit_res.get("ok"))

        # 3. Check branch status (pending approval)
        status = codetools.get_branch_change_status(self.slug)
        self.assertTrue(status.get("pending_approval"))
        self.assertEqual(status.get("current_branch"), branch_name)
        self.assertEqual(status.get("default_branch"), "main")

        # 4. User approval merge
        merge_res = codetools.merge_change_branch(self.slug, branch_name, approve=True)
        self.assertTrue(merge_res.get("ok"))
        self.assertTrue(merge_res.get("merged"))

        # Verify back on main and file updated
        curr_after = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.project_dir, capture_output=True, text=True).stdout.strip()
        self.assertEqual(curr_after, "main")
        self.assertIn("return a + b + 0", (self.project_dir / "calc.py").read_text())


if __name__ == "__main__":
    unittest.main()
