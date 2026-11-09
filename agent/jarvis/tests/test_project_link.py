import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

bridge_path = Path(__file__).resolve().parents[2] / "bridge" / "pc_bridge.py"
spec = importlib.util.spec_from_file_location("test_pc_bridge", bridge_path)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


class ProjectLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp_home = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_home.name).resolve()
        self.workspace = self.home / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.patches = [
            patch.object(pc, "HOME", self.home),
            patch.object(pc, "WORKSPACE", self.workspace),
            patch.object(pc, "PROTECTED", [self.workspace / "_DevPilot", self.workspace / ".obsidian"]),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp_home.cleanup()

    def test_link_folder_without_project_md_creates_spec_and_lists_it(self):
        external_folder = self.home / "my-external-app"
        external_folder.mkdir(parents=True, exist_ok=True)
        (external_folder / "index.js").write_text("console.log('hello');")

        # Prior to fix: external_folder has no PROJECT.md
        self.assertFalse((external_folder / "PROJECT.md").exists())

        res = pc.h_project_link({"path": str(external_folder)})
        self.assertTrue(res.get("ok"))
        slug = res.get("slug")
        self.assertEqual(slug, "my-external-app")

        # After linking, PROJECT.md must exist in target
        self.assertTrue((external_folder / "PROJECT.md").exists(), "PROJECT.md should be initialized upon linking")

        # Project listing must include the new slug
        listing = pc.h_project_list({})
        self.assertIn("my-external-app", listing.get("folders", []), "Linked folder must be included in h_project_list")

    def test_link_folder_inside_workspace_without_project_md(self):
        in_workspace = self.workspace / "sub-project"
        in_workspace.mkdir(parents=True, exist_ok=True)

        res = pc.h_project_link({"path": str(in_workspace)})
        self.assertTrue(res.get("ok"))

        self.assertTrue((in_workspace / "PROJECT.md").exists())
        listing = pc.h_project_list({})
        self.assertIn("sub-project", listing.get("folders", []))


if __name__ == "__main__":
    unittest.main()
