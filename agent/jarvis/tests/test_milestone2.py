"""Tests for Milestone 2: Multi-Provider Router, Failover, SQLite WAL State & MCP Interface."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "bridge"))
sys.path.insert(0, str(HERE.parents[1] / "workflow"))

import brain
import engine
import pc_bridge
import runtime_settings
import server


class Milestone2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    # --- 1. Model Router & Tiers
    def test_model_router_tiers_and_chain(self):
        e = engine.Engine.__new__(engine.Engine)
        router = engine.ModelRouter(e)
        
        reasoning_model = router.get_tier_model("Architect Agent")
        self.assertEqual(reasoning_model, runtime_settings.get().get("tier_reasoning", "gemini-3.8-flash"))
        
        fast_model = router.get_tier_model("Build Agent")
        self.assertEqual(fast_model, runtime_settings.get().get("tier_fast", "gemini-3-flash"))

        agent_agy = engine.AgentSpec("Orch", "agy/gemini-3.8-flash", "sys", 1, [])
        chain_agy = router.get_chain(agent_agy)
        self.assertEqual(chain_agy[0][0], "agy")

        agent_openai = engine.AgentSpec("Orch", "openai/gpt-4o", "sys", 1, [])
        with patch.object(router.openai, "is_available", return_value=True):
            chain_openai = router.get_chain(agent_openai)
            self.assertEqual(chain_openai[0][0], "openai")

    # --- 2. SQLite WAL State & Synchronization
    def test_sqlite_wal_state_syncs_with_files(self):
        sdb = brain.StateDB(self.root)
        
        # Test state dict saves to SQLite and syncs to .devpilot/STATE.json
        state_data = {"phase": "build", "status": "active", "next_action": "implement tests"}
        sdb.set_state("state", state_data)
        
        self.assertEqual(sdb.get_state("state"), state_data)
        state_json = self.root / ".devpilot" / "STATE.json"
        self.assertTrue(state_json.exists())
        self.assertEqual(json.loads(state_json.read_text()), state_data)

        # Test plan syncs to PLAN.md
        plan_text = "# Test Plan\n\n- [ ] Task 1\n- [ ] Task 2\n"
        sdb.set_state("plan", plan_text)
        self.assertEqual(sdb.get_state("plan"), plan_text)
        plan_file = self.root / "PLAN.md"
        self.assertTrue(plan_file.exists())
        self.assertEqual(plan_file.read_text(), plan_text)

    # --- 3. Tainted Context Tracking & Safety
    def test_tainted_context_requires_approval_for_shell(self):
        e = engine.Engine.__new__(engine.Engine)
        e.stop, e.pause_requested = threading.Event(), threading.Event()
        e.emit = MagicMock()
        e.tainted_context = False
        e.project_root = str(self.root)
        e.settings = {"review_mode": False}
        e.approvals = MagicMock(return_value={"approved": False, "note": "Rejected"})

        agent = engine.AgentSpec("Build", "test", "sys", 1, [])
        fetch_tool = engine.Tool("web_fetch", "Fetch Page", "Fetch", "bridge", path="/web/fetch")
        shell_tool = engine.Tool("pc_shell", "Shell", "Run cmd", "bridge", path="/shell")

        # Running web fetch taints the context
        with patch.object(e, "bridge", return_value='{"content": "untrusted web page"}'):
            e.run_tool(agent, fetch_tool, {"url": "https://example.com"}, 0)
        
        self.assertTrue(e.tainted_context)

        # Running shell in tainted context must raise PermissionError if approval is rejected
        with self.assertRaises(PermissionError):
            e.run_tool(agent, shell_tool, {"cmd": "ls -la"}, 0)

        e.approvals.assert_called_once()

    # --- 4. CLIAgentProvider in pc_bridge
    def test_cli_agent_provider_adapter(self):
        with patch.object(pc_bridge, "run", return_value={"exit_code": 0, "stdout": "ok"}) as mock_run:
            res = pc_bridge.h_cli_agent({"cli": "claude", "prompt": "build this", "cwd": str(self.root)})
            self.assertEqual(res["exit_code"], 0)
            mock_run.assert_called_once()
            argv = mock_run.call_args[0][0]
            self.assertEqual(argv[:2], ["claude", "-p"])

    # --- 5. MCP Endpoint Protocol
    def test_mcp_initialize_and_tools(self):
        class MockReq:
            def __init__(self, data):
                import io
                self.rfile = io.BytesIO(data)
                self.headers = {"Content-Length": str(len(data))}
                self.response_code = None
                self.response_data = None
            def send(self, code, obj):
                self.response_code = code
                self.response_data = obj

        handler = server.Handler.__new__(server.Handler)
        
        # Test initialize
        init_req = MockReq(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}).encode())
        handler.rfile = init_req.rfile
        handler.headers = init_req.headers
        handler.send = init_req.send
        handler.handle_mcp()
        
        self.assertEqual(init_req.response_code, 200)
        self.assertEqual(init_req.response_data["result"]["serverInfo"]["name"], "kryzen-mcp")

        # Test tools/list
        tools_req = MockReq(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode())
        handler.rfile = tools_req.rfile
        handler.headers = tools_req.headers
        handler.send = tools_req.send
        handler.handle_mcp()
        
        self.assertEqual(tools_req.response_code, 200)
        tool_names = [t["name"] for t in tools_req.response_data["result"]["tools"]]
        self.assertIn("kryzen_delegate", tool_names)
        self.assertIn("kryzen_project_memory", tool_names)
        self.assertIn("kryzen_skills", tool_names)


if __name__ == "__main__":
    unittest.main()
