# DevPilot

An n8n multi-agent system that researches, designs, plans, builds and browser-tests software projects on this PC.

```
agent/
├── README.md                 this file
├── bridge/
│   ├── pc_bridge.py          HTTP bridge n8n → PC (sandboxed shell, files, agy, browser, skills, projects)
│   ├── pc-bridge.service     systemd user unit (linked into ~/.config/systemd/user/)
│   ├── .token                bridge auth token (chmod 600, stored in n8n as "PC Bridge Token")
│   └── jobs/                 logs of background jobs
├── skills/                   DevPilot skills (also linked into ~/.agents/skills for agy)
│   ├── project-standards/    folder layout + conventions
│   ├── pc-control/           using the bridge safely
│   ├── agy-cli/              driving the Antigravity CLI
│   ├── project-research/     research brief workflow
│   ├── project-planning/     think-first planning → docs/plan/PLAN.md
│   ├── project-resume/       checkpoints + continue-where-it-stopped protocol
│   ├── ui-build-debug/       references → design → build → fix loop
│   └── browser-qa/           agent-browser UI testing
├── templates/project/        skeleton copied by the Create Project tool
├── workflow/
│   ├── build_workflow.py     generates the n8n workflow (edit this, not the JSON)
│   ├── ai-dev-agent.json     generated DevPilot workflow (id UHpLpx9tkH6AyFdc)
│   └── autoresume.json       generated DevPilot Auto-Resume error workflow (id DevPilotResume01)
├── test_models.py            lists + live-tests NVIDIA NIM / Gemini models
├── models_report.md          last model test results
└── .keys.env                 API keys for test_models.py (chmod 600, never commit)
```

## Obsidian vault (manage everything here)

`~/Projects/devpilot` is an Obsidian vault. `_DevPilot/` holds the control files:
- `Agents/*.md` — **source of truth** for every agent (prompt, description, model, max steps, tools)
- `Flows/*.canvas` — generated reference diagrams and editable Jarvis canvases · `Project Lifecycle.md` · `Home.md` · `Tools.md`
- `Skills/` and `Templates/` — the real skill and template folders (`agent/skills`, `agent/templates` are symlinks)

Edit in Obsidian, then run `devpilot-sync` (rebuild + import into n8n). Skills/templates apply immediately.
`_DevPilot/` and `.obsidian/` are read-only for agents.

## Antigravity GUI / Jarvis (Upgraded Web GUI for Antigravity CLI)

`jarvis/` — an upgraded HUD for the **Antigravity CLI** (`agy`) at **http://127.0.0.1:8770**: streaming chat, a live agent graph (agents light up, tool
calls orbit them, reasoning scrolls underneath), and Project / Files / Activity panels.
- **Engine** (`jarvis/engine.py`): runs agents and multi-agent orchestration directly on **Antigravity CLI** (`agy`) with streaming, tool execution, and subagent delegation. Operates completely without external third-party APIs (no NVIDIA NIM, no external API keys). All operations auto-approved (`--dangerously-skip-permissions`).
- **Sudo environment**: full sudo access configured with password `33303330` across all environments (`SUDO_PASS=33303330`, `SUDO_PASSWORD=33303330`).
- **Server** (`jarvis/server.py`): localhost only; POSTs need `X-Jarvis: 1` + same origin. Conversations are saved
  in `jarvis/sessions/`. Stop button cancels a run; say *continue* to resume from the last checkpoint.
- Start: `systemctl --user enable --now jarvis` (unit: `jarvis/jarvis.service`).
- **Agent mesh**: click an agent to edit its prompt, description, model, steps, colour, tools and skills;
  **＋ Agent** adds a specialist (the Orchestrator can delegate to it automatically), Archive removes one.
  Layers: tools (light up when used), skills ring, flow arrows. **Sync n8n** pushes the mesh to n8n.
- **⚙ Control Center** (no code needed — every setting is a form; Jarvis writes the files):
  Appearance (name, greeting, accent colour, glass strength, motion, quick buttons) · Agents · Prompt blocks
  (`Settings.md`) · Tools (custom tools with inputs, command, folder, time limit, which agents get them) · Skills
  (instructions + which agents use them) · Projects (create, open, start) · Models (verified list, apply to all)
  · Services (status, logs, restart) · Advanced files (the raw files, if you ever want them).
  Saves that affect agents rebuild the mesh and revert on failure; deletes go to `_DevPilot/Archive/files/`.
- **Design**: neutral liquid glass on solid dark gray (`#1c1c1f`), no coloured glows; glass strength and accent
  come from Appearance.
- **⌨ Code workspace** (per project, all through the sandboxed bridge): file tree with filter (Ctrl+P), multi-tab
  editor with line numbers (Ctrl+S), **Ask Jarvis** about a file or selection, and a dock with Terminal (history,
  background jobs, Ctrl+`), Run (install + every package.json script; dev/start run in the background with live
  output and Stop), Search (ripgrep, regex/case/glob, click a hit to jump to the line — Ctrl+Shift+F), Git
  (status, coloured diff, history, commit all) and Preview (the dev server inside Jarvis, address auto-detected).
- **Agent coding tools** (custom tools): `search_code`, `git_diff`, `run_script`, `install_deps`, `project_checks`.
- **Custom tools**: `_DevPilot/Tools/<id>.md` — a shell command template with `{param}` slots run in the sandbox;
  tick it in an agent's editor. Jarvis-only (n8n skips them). Example: `project_checks` (lint + typecheck + tests).
- **Flow Studio**: Obsidian-compatible canvases with draggable notes and linked agents, labeled connections,
  pan/zoom/Fit, inspector controls, keyboard positioning, import/export, duplication and Ctrl+S. Generated flows
  stay read-only; editable copies survive workflow rebuilds. Content revisions reject stale Obsidian/window edits.
  The included **Jarvis Mission** canvas shows the research → design → plan → build ⇄ verify handoffs.
  **Activate routing** limits specialist delegation to linked agent cards on subsequent Jarvis runs; connections
  provide orchestration guidance, not a deterministic execution graph. Disable routing to restore the full team.
  This routing setting applies to Jarvis; it does not rewire n8n.
- **Plan Studio**: the selected project's actual `docs/plan/PLAN.md`, shown as milestone/task progress, Markdown
  source and preview. Task checkboxes update that same file. Save uses revision checks; approval is stored in
  `.devpilot/plan-approval.json` and becomes outdated after any plan content change. Ask Planner and Continue
  start explicit project-scoped chat runs. Normal chat also receives the selected project's plan/checkpoint context.
  Agents with file access receive **Read Project Plan**; agents with write access also receive **Update Plan Task**.
- **Run controls**: Pause waits at the next tool/model boundary, Resume releases it, and Stop releases a paused
  run. An operation already in progress may finish before pause/stop takes effect.
- **Skills library**: searchable instructions and agent filters, with editable assignments. The curated pack adds
  18 skills (26 total in the shared vault): orchestration, canvas/plan control, UI design, frontend engineering,
  accessibility, API contracts, databases, testing, debugging, security, performance, Git, deployments, docs,
  skill authoring, source verification and data files. Assigned names are included in each agent's runtime prompt;
  bodies are read on demand through the bridge. Reinstall additively with `python3 -I jarvis/skill_pack.py --install`;
  existing skill text is preserved. Use Sync n8n separately if you also want to import updated agent notes there.

Jarvis validation (from the n8n workspace root):

```sh
python3 -m unittest discover -s agent/jarvis/tests -v
python3 -m py_compile agent/jarvis/server.py agent/jarvis/engine.py agent/jarvis/studio.py
node --check agent/jarvis/studio.js
```

The test suite uses disposable storage and fake bridge/model dependencies. Browser QA evidence and limitations
are recorded in `jarvis/docs/qa/REPORT.md`.

## Agents

| Agent | Model (NVIDIA NIM) | Tools | Writes |
|---|---|---|---|
| DevPilot Orchestrator | nemotron-3.5-super-120b | Think, Create/List Projects, files, skills, the 5 agents | `PROJECT.md`, `docs/design/`, `docs/decisions/` |
| Research Agent | nemotron-3.5-super-120b | Web Search, Fetch Page, files | `docs/research/BRIEF.md` |
| Reference Agent | nemotron-3.5-super-120b | Web Search, Fetch Page, Browser, files | `docs/references/` |
| Planner Agent | nemotron-3.5-super-120b | Think, files (read-only codebase review) | `docs/plan/PLAN.md`, ADRs |
| Build Agent | nemotron-3.5-super-120b | Antigravity CLI, Shell, files — implements PLAN.md tasks in order | `src/`, `README.md`, `CHANGELOG.md` |
| QA Agent | nemotron-3.5-super-120b | Browser, Shell, Antigravity CLI, files — tests every PLAN.md AC | `docs/qa/` |

## Projects

Every project is created by the **Create Project** tool in `~/Projects/devpilot/<slug>/` and listed in
`~/Projects/devpilot/INDEX.md`. Layout: see `skills/project-standards/SKILL.md`.

## Security model

- The bridge listens only on the n8n Docker network (`172.22.0.1:8765`) and requires the token.
- Shell commands run in bubblewrap: home contains only the workspace (writable) and the toolchain (read-only);
  no Docker socket, no `~/.ssh`, no other drives.
- File, browser-screenshot and project paths must be inside `~/Projects/devpilot`; `file:` URLs are refused.
- agy always runs with `--sandbox`; `--dangerously-skip-permissions` needs `PC_BRIDGE_ALLOW_AGY_ACCEPT_ALL=1`.
- Agents that read the web (Research, Reference) have no shell.

## Resuming interrupted work

- The bridge journals every shell command, file write and agy run inside a project to `<project>/.devpilot/journal.jsonl`.
- Agents call **Save Checkpoint** after every step → `<project>/.devpilot/STATE.json` (phase, task, `next_action`).
- Say **continue** / **ادامه** in the chat (any session): the orchestrator calls **Resume Project**, which returns the
  saved state, plan progress, open tasks, docs status, recent journal, git log, uncommitted changes and running
  jobs, then carries on from `next_action`. Interrupted tasks show up as uncommitted changes and are finished first.
- **Automatic**: when DevPilot is *published*, a failed run triggers **DevPilot Auto-Resume** (error workflow), which
  waits 60 s and calls DevPilot with an `AUTO-RESUME` message — max 3 times per 30 min (`bridge/autoresume.json`).
  Manual editor runs don't trigger error workflows.

## Troubleshooting

- **"Request timed out" after ~10 s on a model node**: `telemetry.n8n.io` doesn't resolve on this network and
  each failed lookup blocks a Node DNS thread for 5 s, starving the NVIDIA lookup. Fixed in `../.env` with
  `N8N_DIAGNOSTICS_ENABLED=false`, `N8N_VERSION_NOTIFICATIONS_ENABLED=false`, `UV_THREADPOOL_SIZE=32`
  (apply with `docker compose up -d n8n`).
- **"Received tool input did not match expected schema"**: a tool field without a default is required; give
  optional fields a default in `build_workflow.py` (`ai(key, desc, type, default)`).

## Common tasks

```sh
systemctl --user status pc-bridge          # bridge health
journalctl --user -u pc-bridge -f          # live tool calls
python3 workflow/build_workflow.py         # regenerate the workflow after editing
docker cp workflow/ai-dev-agent.json n8n-n8n-1:/tmp/wf.json && docker exec n8n-n8n-1 n8n import:workflow --input=/tmp/wf.json
```

## Reliability and recovery

Jarvis now saves active chats during execution and marks interrupted runs recoverable after restart. Live events
use stable IDs across retention and reconnection. The code editor and canonical plan reject stale file revisions;
use the editor Reload action to review newer disk contents after a conflict. New-file creation preserves existing files.

Background jobs started by the updated bridge save their metadata and output. After bridge restart, finished logs
remain available and unfinished jobs are labeled interrupted; resume from the project checkpoint. In-progress
commands do not continue automatically across a bridge restart.

The complete audit evidence and repeatable browser fixture are documented in `jarvis/docs/qa/RELIABILITY.md`.
The regression suite has 37 tests; the disposable browser script has 9 scenarios. Both n8n and Jarvis receive
assigned role skills in their prompts. n8n publication remains an explicit workflow setting.

## Running (web UI only)

K.R.Y.Z.E.N runs as a local web UI at **http://127.0.0.1:8770** (app launcher: **K.R.Y.Z.E.N**, opens as a web-app window).
Everything starts at boot without logging in (user lingering is on):

| User unit (`~/.config/systemd/user/`) | Does |
|---|---|
| `kryzen-backend.service` | waits for `/mnt/bullshit`, then `docker compose -p n8n up -d` (docker.socket starts Docker on demand) |
| `pc-bridge.service` | sandboxed tools for the agents; retries until the backend network exists |
| `jarvis.service` | engine + web UI on port 8770 |

- Unit sources live next to the code (`agent/kryzen-backend.service`, `agent/bridge/pc-bridge.service`,
  `agent/jarvis/jarvis.service`); after editing one, copy it to `~/.config/systemd/user/` and `systemctl --user daemon-reload`.
- Settings for the services: `agent/runtime.env`. Containers also have `restart: unless-stopped`.
- Restart: `systemctl --user restart jarvis pc-bridge` · logs: `journalctl --user -u jarvis -f` · status: Home › Health.

## Super upgrade views (2026-10-27)

- **Home** (default view): running work with budgets and lanes, run queue, approvals inbox, token spend, projects,
  deep health + Repair backend; tabs for Skills (usage, versions, imports, drafts), Project memory and Runtime settings.
- **Trace**: every model/tool call of a conversation with exact prompts, full outputs, timeline, replay and export.
- **Ctrl+K**: command palette for views, actions, conversations, projects, files and settings.
- Runtime settings live in `_DevPilot/kryzen-runtime.json`; traces in `jarvis/sessions/<id>/trace.jsonl` + `blobs/`;
  usage ledger `jarvis/sessions/_usage.jsonl`; project memory `<project>/.devpilot/memory.md`.
- Plan and delivery notes: `jarvis/docs/plan/SUPER-UPGRADE.md`.
