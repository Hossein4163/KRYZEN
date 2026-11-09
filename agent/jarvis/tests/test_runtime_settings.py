import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_settings


class RuntimeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = Path(self.temp_dir.name) / "kryzen-runtime.json"
        self.patch = patch.object(runtime_settings, "FILE", self.file_path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp_dir.cleanup()

    def test_isolated_box_and_branch_per_change_defaults(self):
        cfg = runtime_settings.get()
        self.assertIn("isolated_agent_box", cfg)
        self.assertIn("branch_per_change", cfg)
        self.assertFalse(cfg["isolated_agent_box"])
        self.assertFalse(cfg["branch_per_change"])

    def test_save_isolated_box_and_branch_per_change(self):
        res = runtime_settings.save({
            "isolated_agent_box": True,
            "branch_per_change": True,
        })
        self.assertTrue(res["ok"])
        self.assertTrue(res["settings"]["isolated_agent_box"])
        self.assertTrue(res["settings"]["branch_per_change"])

        # Reload from disk
        cfg = runtime_settings.get()
        self.assertTrue(cfg["isolated_agent_box"])
        self.assertTrue(cfg["branch_per_change"])

    def test_save_rejects_invalid_type(self):
        res = runtime_settings.save({
            "isolated_agent_box": "not-a-bool"
        })
        self.assertFalse(res["ok"])
        self.assertIn("isolated_agent_box must be true/false", res["errors"])


if __name__ == "__main__":
    unittest.main()
