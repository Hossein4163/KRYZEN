"""Runtime settings for the engine (budgets, model tier, review mode, concurrency, memory).

Stored next to the other studio settings in the vault (`_DevPilot/kryzen-runtime.json`) so they survive
updates and can be edited from the Home dashboard.
"""
import json
import threading

import mesh
from projectdata import atomic_write

FILE = mesh.SYS / "kryzen-runtime.json"
DEFAULTS = {
    # Model Provider & API
    "active_provider": "auto",                        # auto | openai | ollama | agy
    "openai_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai_api_key": "",                             # API key (masked in UI responses)
    "ollama_base_url": "http://127.0.0.1:11434",
    # Role-Based Model Tiers
    "tier_reasoning": "gemini-3.8-flash",             # Orchestrator, Architect, QA
    "tier_fast": "gemini-3-flash",                    # Build, Design, Content, SEO, Marketing
    "tier_compact": "gemini-3-flash",                 # diet.py, brain.py memory extraction
    "small_model": "agy/gemini-3.8-flash",            # Antigravity CLI model
    # Security & Execution Boundaries
    "agy_skip_permissions": False,                    # strict permissions by default
    "isolated_agent_box": False,                      # run agent edits in isolated box
    "branch_per_change": False,                       # commit changes to own branch & merge upon user approval
    # Network & Tailscale
    "allow_tailscale": True,                          # allow access from *.ts.net and 100.64.0.0/10
    "allow_lan": True,                                # allow access from 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12
    "tailscale_serve": False,                         # enable tailscale serve background proxy
    "custom_allowed_hosts": "",                       # comma-separated extra hostnames/IPs
    # Budgets & Execution
    "budget_tokens": 2000000,                         # per run (turn); 0 = unlimited. Parallel teams use ~10K/call
    "budget_minutes": 0,                              # per run; 0 = unlimited (long project runs are normal)
    "budget_hard_tokens": 10000000,                   # never auto-resume past this many tokens in one run (0 = no cap)
    "auto_resume": True,                              # budget pause resumes by itself after a countdown
    "auto_resume_seconds": 30,                        # countdown before resuming (time to press Keep paused)
    "auto_continue": True,                            # step-limit / temporary-failure endings continue by themselves
    "auto_continue_max": 3,                           # automatic continues in a row before waiting for you
    "auto_screenshot": True,                          # screenshot the running preview when a project run finishes
    "review_mode": False,                             # approve file writes as diffs before they apply
    "max_concurrency": 4,                             # upper bound for adaptive model-request concurrency
    "max_lanes": 4,                                   # parallel task lanes
    "auto_memory": True,                              # extract durable project facts after each run
    "mask_after": 2,                                  # keep this many latest tool results verbatim in context
    "fold_after": 12,                                 # fold chat history older than this many messages
    "compact_at_tokens": 60000,                       # compact an agent's earlier steps once a prompt exceeds this
}
LIMITS = {"budget_hard_tokens": (0, 100_000_000), "auto_resume_seconds": (5, 3600), "auto_continue_max": (0, 20),
          "budget_tokens": (0, 20_000_000), "budget_minutes": (0, 24 * 60), "max_concurrency": (1, 8),
          "max_lanes": (1, 8), "mask_after": (1, 10), "fold_after": (4, 60),
          "compact_at_tokens": (8000, 400000)}
_lock = threading.Lock()


def get(mask_secrets=False):
    try:
        data = json.loads(FILE.read_text())
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    out = {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}
    if mask_secrets and out.get("openai_api_key"):
        out["openai_api_key"] = "••••••••"
    return out


def save(changes):
    if not isinstance(changes, dict):
        raise ValueError("settings must be an object")
    with _lock:
        cur = get(mask_secrets=False)
        errors = []
        for key, value in changes.items():
            if key not in DEFAULTS:
                errors.append(f"unknown setting {key}")
                continue
            default = DEFAULTS[key]
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    errors.append(f"{key} must be true/false")
                    continue
            elif isinstance(default, int):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append(f"{key} must be a number")
                    continue
                lo, hi = LIMITS[key]
                value = int(value)
                if not lo <= value <= hi:
                    errors.append(f"{key} must be between {lo} and {hi}")
                    continue
            elif isinstance(default, str):
                if not isinstance(value, str):
                    errors.append(f"{key} must be a string")
                    continue
                value = value.strip()
                if key == "active_provider" and value not in ("auto", "openai", "ollama", "agy"):
                    errors.append("active_provider must be auto, openai, ollama, or agy")
                    continue
                if key == "openai_api_key":
                    # If masked or blank, preserve existing key
                    if value == "••••••••" or (not value and cur.get("openai_api_key")):
                        continue
                if key in ("openai_base_url", "ollama_base_url") and value:
                    if not value.startswith(("http://", "https://")):
                        errors.append(f"{key} must start with http:// or https://")
                        continue
                if key in ("tier_reasoning", "tier_fast", "tier_compact", "small_model"):
                    if not (2 <= len(value) <= 120):
                        errors.append(f"{key} must be a valid model name")
                        continue
            cur[key] = value
        if errors:
            return {"ok": False, "errors": errors}
        atomic_write(FILE, json.dumps(cur, indent=2))
        return {"ok": True, "settings": get(mask_secrets=True)}
