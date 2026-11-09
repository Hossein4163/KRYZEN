import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import codetools


class IsolatedBoxTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.slug = "test-box-project"
        self.project_dir = self.workspace / self.slug
        self.project_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "PROJECT.md").write_text("# Test Project\n")
        (self.project_dir / "app.py").write_text("def run():\n    return 'original'\n")

        self.orig_workspace = codetools.WORKSPACE
        codetools.WORKSPACE = str(self.workspace)

    def tearDown(self):
        codetools.WORKSPACE = self.orig_workspace
        self.temp_dir.cleanup()

    def test_isolated_box_lifecycle_and_conflict_free_merge(self):
        box_id = "agent-fix-01"
        res = codetools.create_isolated_box(self.slug, box_id)
        self.assertTrue(res.get("ok"))

        # Write edit to isolated box
        write_res = codetools.write_isolated_box(self.slug, box_id, "app.py", "def run():\n    return 'fixed'\n")
        self.assertTrue(write_res.get("ok"))

        # Verify main project file is still untouched
        self.assertEqual((self.project_dir / "app.py").read_text(), "def run():\n    return 'original'\n")

        # Read from isolated box returns modified content
        read_res = codetools.read_isolated_box(self.slug, box_id, "app.py")
        self.assertIn("fixed", read_res.get("content", ""))

        # Merge isolated box into main project
        merge_res = codetools.merge_isolated_box(self.slug, box_id)
        self.assertTrue(merge_res.get("ok"), f"Merge failed: {merge_res}")
        self.assertEqual((self.project_dir / "app.py").read_text(), "def run():\n    return 'fixed'\n")

    def test_isolated_box_aborts_on_concurrent_conflict(self):
        box_id = "agent-fix-conflict"
        codetools.create_isolated_box(self.slug, box_id)

        # Stage change in isolated box
        codetools.write_isolated_box(self.slug, box_id, "app.py", "def run():\n    return 'box-edit'\n")

        # Concurrently modify main project file behind the scenes
        (self.project_dir / "app.py").write_text("def run():\n    return 'concurrent-manual-edit'\n")

        # Merge should detect conflict and abort without overwriting the conflicting file
        merge_res = codetools.merge_isolated_box(self.slug, box_id)
        self.assertFalse(merge_res.get("ok"))
        self.assertTrue(merge_res.get("conflict"))
        self.assertIn("app.py", merge_res.get("conflicts", []))

        # Main file remains preserved
        self.assertEqual((self.project_dir / "app.py").read_text(), "def run():\n    return 'concurrent-manual-edit'\n")


if __name__ == "__main__":
    unittest.main()
