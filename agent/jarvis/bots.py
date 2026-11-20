"""Autonomous Bots (Rakazo-style persistent teammates) for K.R.Y.Z.E.N.

Persistent AI teammates with identity, persistent memory, routines, sandbox computers,
and native compatibility with Antigravity CLI (agy) and K.R.Y.Z.E.N REST API.
"""
import json
import os
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_DIR = HERE.parent
WORKFLOW_DIR = AGENT_DIR / "workflow"

import sys
if str(WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIR))

try:
    from vaultnotes import SYS
except ImportError:
    SYS = Path.home() / "Projects" / "devpilot" / "_DevPilot"

try:
    from projectdata import atomic_write
except ImportError:
    def atomic_write(path, content):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp." + str(time.time()))
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

BOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")

DEFAULT_BOTS = [
    {
        "id": "devpilot-orchestrator",
        "name": "DevPilot Orchestrator",
        "role": "Product Lead & Mesh Coordinator",
        "description": "Decomposes user requirements into architectural milestones, enforces stage gates, coordinates specialists, and validates handoffs.",
        "color": "red",
        "avatar": "compass",
        "model": "agy/gemini-3.8-flash",
        "thinking_level": "high",
        "memory_scope": "shared",
        "sandbox_type": "bubblewrap",
        "is_default": True,
        "instructions": (
            "You are the DevPilot Orchestrator, a persistent autonomous product lead. "
            "Coordinate the engineering team, enforce stage gates (Start -> Discover -> Plan -> Design -> Build -> Verify -> Launch -> Grow), "
            "and delegate atomic tasks to specialized subagents. Never claim completion without verification evidence."
        ),
        "tools": ["think", "project_resume", "project_checkpoint", "agy_run", "pc_shell", "web_search"],
        "routines": [
            {
                "id": "rt-morning-sync",
                "title": "Milestone & Gate Alignment",
                "schedule": "0 9 * * 1-5",
                "prompt": "Inspect the active project status, uncommitted git changes, open milestone tasks, and stage gates. Output current readiness.",
                "active": True,
                "last_run": None,
            }
        ],
        "created_at": 1731000000,
    },
    {
        "id": "fullstack-builder",
        "name": "Full-Stack Engineer",
        "role": "System Architecture & Implementation",
        "description": "Writes production-ready backend and frontend code, database schemas, Clean Architecture layers, and unit tests with zero fluff.",
        "color": "blue",
        "avatar": "code",
        "model": "agy/gemini-3.8-flash",
        "thinking_level": "high",
        "memory_scope": "isolated",
        "sandbox_type": "bubblewrap",
        "is_default": True,
        "instructions": (
            "You are the Full-Stack Build Agent. Implement production-grade software according to specifications. "
            "Follow Clean Architecture, ensure all database migrations are reversible, and run builds and tests inside the sandbox before reporting."
        ),
        "tools": ["agy_run", "pc_shell", "pc_read_file", "pc_write_file", "pc_list_dir", "pc_job_status"],
        "routines": [],
        "created_at": 1731000000,
    },
    {
        "id": "ui-vibe-designer",
        "name": "Swiss UI Designer",
        "role": "Tactile Vibe & Interface Systems",
        "description": "Engineers high-contrast Swiss-Modernist interfaces, design token architectures, tactile Framer Motion spring physics, and responsive layouts.",
        "color": "purple",
        "avatar": "palette",
        "model": "agy/gemini-3.8-flash",
        "thinking_level": "medium",
        "memory_scope": "isolated",
        "sandbox_type": "bubblewrap",
        "is_default": True,
        "instructions": (
            "You are the Swiss UI Designer. Craft mathematical, high-contrast, modernist interfaces with zero AI slop. "
            "Enforce 4px/8px rhythm, semantic design tokens, monochrome ink palettes, tactile spring hover feedback, and strict accessibility."
        ),
        "tools": ["agy_run", "pc_shell", "pc_read_file", "pc_write_file", "browser"],
        "routines": [],
        "created_at": 1731000000,
    },
    {
        "id": "qa-verifier",
        "name": "QA & E2E Verifier",
        "role": "Automated Testing & Browser QA",
        "description": "Executes automated test suites, Obscura V8 and Chromium headless visual regression, DOM assertions, and network contract auditing.",
        "color": "green",
        "avatar": "activity",
        "model": "agy/gemini-3.8-flash",
        "thinking_level": "medium",
        "memory_scope": "isolated",
        "sandbox_type": "bubblewrap",
        "is_default": True,
        "instructions": (
            "You are the QA Verifier. Thoroughly test every feature and regression boundary. "
            "Run headless browser tests, capture screenshot evidence, verify HTTP response codes, and refute unverified assertions."
        ),
        "tools": ["browser", "pc_shell", "pc_job_status", "pc_read_file"],
        "routines": [
            {
                "id": "rt-e2e-suite",
                "title": "Headless Browser QA Suite",
                "schedule": "0 18 * * 1-5",
                "prompt": "Run the project test suite and headless Obscura/Chromium assertions. Report any layout regressions or failing tests.",
                "active": True,
                "last_run": None,
            }
        ],
        "created_at": 1731000000,
    },
    {
        "id": "security-devops",
        "name": "DevOps & Security",
        "role": "Sandboxing, Containers & Security",
        "description": "Maintains Bubblewrap sandboxing, multi-stage Docker builds, systemd services, OWASP security reviews, and secret confinement.",
        "color": "yellow",
        "avatar": "server",
        "model": "agy/gemini-3.8-flash",
        "thinking_level": "high",
        "memory_scope": "shared",
        "sandbox_type": "bubblewrap",
        "is_default": True,
        "instructions": (
            "You are the DevOps & Security Agent. Enforce strict trust boundaries. Zero plaintext secrets in code, "
            "isolated execution within Bubblewrap, least privilege permissions, and reliable continuous deployment."
        ),
        "tools": ["pc_shell", "pc_job_status", "pc_read_file", "pc_write_file"],
        "routines": [],
        "created_at": 1731000000,
    },
    {
        "id": "growth-seo",
        "name": "Growth & SEO Specialist",
        "role": "Technical SEO & Schema Markup",
        "description": "Generates Schema.org JSON-LD structured data, dynamic XML sitemaps, OpenGraph metadata, crawl audits, and technical writer briefs.",
        "color": "orange",
        "avatar": "sparkles",
        "model": "agy/gemini-3.8-flash",
        "thinking_level": "medium",
        "memory_scope": "shared",
        "sandbox_type": "bubblewrap",
        "is_default": True,
        "instructions": (
            "You are the Growth & SEO Specialist. Maximize organic search discovery and technical indexability. "
            "Validate JSON-LD structured data schemas against Schema.org and Google Rich Results guidelines."
        ),
        "tools": ["web_search", "web_fetch", "pc_read_file", "pc_write_file"],
        "routines": [],
        "created_at": 1731000000,
    },
]


def _bots_file() -> Path:
    if SYS.exists():
        return SYS / "bots.json"
    return HERE / "bots_data.json"


def _read_data() -> dict:
    f = _bots_file()
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "bots" in data:
                return data
        except Exception:
            pass
    # Initialize with default bots
    data = {"bots": DEFAULT_BOTS, "updated_at": time.time()}
    _write_data(data)
    return data


def _write_data(data: dict):
    f = _bots_file()
    data["updated_at"] = time.time()
    atomic_write(f, json.dumps(data, indent=2, ensure_ascii=False))


def list_bots(bridge=None) -> list:
    """Return all configured bots with live sandbox and job status."""
    data = _read_data()
    bots = data.get("bots", [])

    # Check for active running background jobs from pc_bridge if bridge is provided
    running_jobs = []
    if bridge:
        try:
            res = bridge("/jobs/list", {})
            if isinstance(res, dict):
                running_jobs = [j for j in res.get("jobs", []) if j.get("running")]
        except Exception:
            pass

    augmented = []
    for bot in bots:
        b = dict(bot)
        # Find if this bot has active jobs
        active_for_bot = [
            j for j in running_jobs
            if j.get("agent") == b.get("name") or j.get("bot_id") == b["id"]
        ]
        b["status"] = "running" if active_for_bot else "idle"
        b["active_jobs_count"] = len(active_for_bot)
        b["routines_count"] = len(b.get("routines", []))
        augmented.append(b)
    return augmented


def get_bot(bot_id: str) -> dict:
    """Get single bot detail by id."""
    data = _read_data()
    for b in data.get("bots", []):
        if b["id"] == bot_id:
            return dict(b)
    raise ValueError(f"Bot with id '{bot_id}' not found")


def save_bot(bot_data: dict) -> dict:
    """Create or update a bot."""
    bot_id = str(bot_data.get("id", "")).strip().lower()
    if not bot_id or not BOT_ID_RE.match(bot_id):
        raise ValueError("Invalid bot id (use lowercase alphanumeric and dashes, 2-40 chars)")

    name = str(bot_data.get("name", "")).strip()
    if not name:
        raise ValueError("Bot name cannot be empty")

    data = _read_data()
    bots = data.get("bots", [])

    existing_idx = next((i for i, b in enumerate(bots) if b["id"] == bot_id), -1)
    record = {
        "id": bot_id,
        "name": name,
        "role": str(bot_data.get("role", "AI Teammate")),
        "description": str(bot_data.get("description", "")),
        "color": str(bot_data.get("color", "blue")),
        "avatar": str(bot_data.get("avatar", "compass")),
        "model": str(bot_data.get("model", "agy/gemini-3.8-flash")),
        "thinking_level": str(bot_data.get("thinking_level", "high")),
        "memory_scope": str(bot_data.get("memory_scope", "isolated")),
        "sandbox_type": str(bot_data.get("sandbox_type", "bubblewrap")),
        "instructions": str(bot_data.get("instructions", "")),
        "tools": list(bot_data.get("tools", ["agy_run", "pc_shell", "pc_read_file"])),
        "routines": list(bot_data.get("routines", [])),
        "is_default": bot_data.get("is_default", False),
        "updated_at": time.time(),
        "created_at": bot_data.get("created_at", time.time()),
    }

    if existing_idx >= 0:
        bots[existing_idx] = record
    else:
        bots.append(record)

    data["bots"] = bots
    _write_data(data)
    return {"ok": True, "bot": record}


def delete_bot(bot_id: str) -> dict:
    """Delete a custom bot."""
    data = _read_data()
    bots = data.get("bots", [])
    bot = next((b for b in bots if b["id"] == bot_id), None)
    if not bot:
        raise ValueError(f"Bot '{bot_id}' does not exist")
    if bot.get("is_default"):
        raise ValueError(f"Default system teammate '{bot['name']}' cannot be deleted")

    data["bots"] = [b for b in bots if b["id"] != bot_id]
    _write_data(data)
    return {"ok": True, "deleted": bot_id}


def run_bot(bridge, bot_id: str, prompt: str, slug: str = "", mode: str = "auto", background: bool = True) -> dict:
    """Run an autonomous task with the specified bot via Antigravity CLI (agy) or bridge."""
    bot = get_bot(bot_id)
    if not prompt or not str(prompt).strip():
        raise ValueError("Prompt cannot be empty")

    import codetools

    # Format the prompt with the bot's system identity and role
    system_intro = (
        f"You are {bot['name']}, acting as {bot['role']}.\n"
        f"Instructions: {bot['instructions']}\n"
    )
    formatted_prompt = f"{system_intro}\nTask:\n{prompt.strip()}"

    model = bot.get("model", "agy/gemini-3.8-flash")
    effort = bot.get("thinking_level", "high")

    # Dispatches directly through codetools.agy to Antigravity CLI in sandbox
    res = codetools.agy(
        bridge,
        slug=slug or "",
        prompt=formatted_prompt,
        mode=mode or "auto",
        model=model,
        effort=effort,
        background=background,
    )
    res["bot_id"] = bot["id"]
    res["bot_name"] = bot["name"]
    return res


def get_bot_computer(bridge, bot_id: str, slug: str = "") -> dict:
    """Inspect the bot's computer sandbox environment, recent file actions, and jobs."""
    bot = get_bot(bot_id)
    import codetools
    cwd = codetools._root(slug) if slug else str(Path.home() / "Projects" / "devpilot")

    # Get recent jobs
    recent_jobs = []
    if bridge:
        try:
            res = bridge("/jobs/list", {})
            if isinstance(res, dict):
                recent_jobs = [
                    j for j in res.get("jobs", [])
                    if j.get("bot_id") == bot_id or j.get("agent") == bot["name"]
                ][:5]
        except Exception:
            pass

    # Check browser status
    browser_status = {"available": False}
    if bridge:
        try:
            b_res = bridge("/browser/status", {})
            if isinstance(b_res, dict):
                browser_status = b_res
        except Exception:
            pass

    return {
        "ok": True,
        "bot_id": bot["id"],
        "bot_name": bot["name"],
        "cwd": cwd,
        "sandbox_type": bot.get("sandbox_type", "bubblewrap"),
        "model": bot.get("model"),
        "browser": browser_status,
        "recent_jobs": recent_jobs,
    }


def add_or_update_routine(bot_id: str, routine_data: dict) -> dict:
    """Add or update a routine for a bot."""
    bot = get_bot(bot_id)
    routines = bot.get("routines", [])
    rid = str(routine_data.get("id") or f"rt-{int(time.time())}")
    title = str(routine_data.get("title", "Scheduled Routine")).strip()
    schedule = str(routine_data.get("schedule", "0 9 * * 1-5")).strip()
    prompt = str(routine_data.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("Routine prompt cannot be empty")

    new_routine = {
        "id": rid,
        "title": title,
        "schedule": schedule,
        "prompt": prompt,
        "active": bool(routine_data.get("active", True)),
        "last_run": routine_data.get("last_run"),
    }

    existing_idx = next((i for i, r in enumerate(routines) if r["id"] == rid), -1)
    if existing_idx >= 0:
        routines[existing_idx] = new_routine
    else:
        routines.append(new_routine)

    bot["routines"] = routines
    return save_bot(bot)
