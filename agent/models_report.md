# Antigravity CLI Agent Model Engine

All agents in Jarvis run directly on the **Antigravity CLI** (`agy`). No third-party APIs (OpenAI, Anthropic, NVIDIA NIM, SearXNG, external Gemini API keys) are required or used.

| Model / Agent | CLI Native | Tool Calling | Subagent Delegation | Status |
|---|---|---|---|---|
| `agy/gemini-3.8-flash` | ✅ | ✅ | ✅ | Active (Default) |
| `agy/gemini-3-flash` | ✅ | ✅ | ✅ | Verified |
| `agy/gemini-3-pro` | ✅ | ✅ | ✅ | Verified |
| `agy/auto` | ✅ | ✅ | ✅ | Verified |

- **Permissions**: Strict permission boundaries by default; scoped access via runtime settings.
- **Sudo Privilege**: Hardcoded credentials removed. Privilege escalation requires structured user approval.
- **Orchestration**: Direct subagent spawning and multi-agent coordination managed via Antigravity CLI.
