"""Mesh editing for Jarvis: read and change the agent notes in the Obsidian vault, then rebuild.

The notes in ~/Projects/devpilot/_DevPilot/Agents are the source of truth for the agents.
Saving here rewrites a note and runs build_workflow.py (Jarvis uses the result on its next message);
"""
import json
import re
import subprocess
import sys
import time
import threading
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = AGENT_DIR / "workflow"
sys.path.insert(0, str(WORKFLOW_DIR))
from vaultnotes import AGENT_NOTES, ARCHIVE, COLORS, SYS, note_intro, read_note, write_note  # noqa: E402
from projectdata import atomic_write

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 -]{2,40}$")
LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{1,20}$")
ORCH_LABEL = "Orchestrator"

STAGES = (
    ("start", ""),
    ("discover", r"research|reference|\bproduct\b|discover"),
    ("plan", r"architect|planner|plan\b"),
    ("design", r"design|brand|ux"),
    ("build", r"build|engineer|frontend|backend|develop"),
    ("verify", r"\bqa\b|test|review|security|audit"),
    ("launch", r"devops|production|deploy|release|ops\b"),
    ("grow", r"seo|market|content|growth|sales|support"),
)
GATE_LOCK = threading.RLock()


def agent_stages(names, orchestrator):
    others = [name for name in names if name != orchestrator]
    result = {orchestrator: "start"}
    for index, name in enumerate(others):
        fallback = STAGES[1 + index * (len(STAGES) - 1) // len(others)][0]
        result[name] = next((stage for stage, pattern in STAGES[1:] if re.search(pattern, name, re.I)), fallback)
    return result


def _gate_data():
    try:
        data = json.loads((SYS / "stage-gates.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def set_gate(stage_id, locked, project=""):
    if stage_id not in [stage for stage, _ in STAGES[:-1]] or not isinstance(locked, bool):
        raise ValueError("choose a valid gate and a boolean lock state")
    with GATE_LOCK:
        data = _gate_data()
        data.setdefault(project, {})[stage_id] = locked
        atomic_write(SYS / "stage-gates.json", json.dumps(data))
    return {"ok": True, "stage": stage_id, "locked": locked, "project": project}


def get_gates(project=""):
    with GATE_LOCK:
        return _gate_data().get(project, {})


def rename_project_gates(old, new):
    with GATE_LOCK:
        data = _gate_data()
        if old in data:
            data[new] = data.pop(old)
            atomic_write(SYS / "stage-gates.json", json.dumps(data))


def blocking_gate(project, stage):
    if not project or not stage or stage == "start":
        return None
    gates = get_gates(project)
    for earlier, _ in STAGES:
        if earlier == stage:
            return None
        if gates.get(earlier):
            return earlier
    return None


def catalog():
    f = WORKFLOW_DIR / "catalog.json"
    return json.loads(f.read_text()) if f.exists() else {"tools": [], "placeholders": {}}


def tool_models():
    """Models that run through the Antigravity CLI (no external APIs)."""
    return [
        "agy/gemini-3.8-flash",
        "agy/gemini-3-flash",
        "agy/gemini-3-pro",
        "agy/auto",
    ]


def skills():
    root = SYS / "Skills"
    return sorted(d.name for d in root.iterdir() if (d / "SKILL.md").exists()) if root.exists() else []


def notes():
    out = []
    for f in AGENT_NOTES.glob("*.md"):
        meta, sec = read_note(f)
        out.append({"file": f.name, "name": meta.get("agent", f.stem), "label": meta.get("label", f.stem),
                    "order": meta.get("order", 99), "model": meta.get("model", ""),
                    "max_iterations": meta.get("max_iterations", 40), "color": meta.get("color", "gray"),
                    "role": meta.get("role", ""), "skills": meta.get("skills", []) or [],
                    "tools": meta.get("tools", []) or [], "description": sec.get("Description", ""),
                    "prompt": sec.get("Prompt", ""), "orchestrator": meta.get("label") == ORCH_LABEL})
    return sorted(out, key=lambda a: a["order"])


def mesh():
    cat = catalog()
    return {"agents": notes(), "tools": cat["tools"], "placeholders": cat["placeholders"], "models": tool_models(),
            "skills": skills(), "colors": COLORS}


def _find(name):
    for a in notes():
        if a["name"] == name:
            return a
    return None


def _validate(a, existing=None):
    errors = []
    for field in ("model", "color", "role", "prompt", "description"):
        if not isinstance(a.get(field), str):
            errors.append(f"{field} must be text")
    for field in ("tools", "skills"):
        if not isinstance(a.get(field), list) or any(not isinstance(x, str) for x in a[field]):
            errors.append(f"{field} must be a list of names")
    if errors:
        return errors
    tool_ids = {t["id"] for t in catalog()["tools"]}
    unknown = [t for t in a["tools"] if t not in tool_ids]
    if unknown:
        errors.append(f"unknown tools: {', '.join(unknown)}")
    if not a["tools"]:
        errors.append("pick at least one tool")
    try:
        steps = int(a["max_iterations"])
        if not 1 <= steps <= 200:
            errors.append("max steps must be 1-200")
    except (TypeError, ValueError):
        errors.append("max steps must be a number")
    if not a["model"]:
        errors.append("pick a model")
    if a["color"] not in COLORS:
        errors.append("unknown colour")
    if not a["prompt"].strip():
        errors.append("prompt is empty")
    if not a.get("orchestrator") and not a["description"].strip():
        errors.append("description is empty (the Orchestrator reads it to decide when to delegate)")
    return errors


def _write(a, path):
    meta = {"agent": a["name"], "label": a["label"], "order": a["order"], "model": a["model"],
            "max_iterations": int(a["max_iterations"]), "color": a["color"], "role": a["role"].replace("\n", " "),
            "skills": a["skills"], "tools": a["tools"], "tags": ["devpilot/agent"]}
    sections = [("Prompt", a["prompt"])] if a.get("orchestrator") else [("Description", a["description"]),
                                                                          ("Prompt", a["prompt"])]
    write_note(path, meta, a["name"], note_intro(a["label"], a["skills"]), sections)


def rebuild():
    try:
        r = subprocess.run([sys.executable, "-I", str(WORKFLOW_DIR / "build_workflow.py")], capture_output=True,
                           text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "output": f"workflow rebuild failed: {e}"}
    return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()[-2000:]}


def save(data):
    current = _find(data.get("name", ""))
    if not current:
        return {"ok": False, "errors": ["unknown agent"]}
    a = {**current, **{k: data[k] for k in ("model", "max_iterations", "color", "role", "skills", "tools",
                                            "description", "prompt") if k in data}}
    errors = _validate(a)
    if errors:
        return {"ok": False, "errors": errors}
    path = AGENT_NOTES / current["file"]
    backup = path.read_text()
    _write(a, path)
    result = rebuild()
    if not result["ok"]:
        path.write_text(backup)          # never leave the mesh in a broken state
        rebuild()
        return {"ok": False, "errors": ["rebuild failed, change reverted"], "output": result["output"]}
    return {"ok": True, "output": result["output"]}


def create(data):
    name, label = str(data.get("name", "")).strip(), str(data.get("label", "")).strip()
    existing = notes()
    errors = []
    if not NAME_RE.match(name):
        errors.append("name: 3-41 letters, digits, spaces or dashes, starting with a letter")
    if not LABEL_RE.match(label):
        errors.append("short label: one word, letters/digits/dashes (used in node names)")
    if any(a["name"].lower() == name.lower() for a in existing):
        errors.append("an agent with this name exists")
    if any(a["label"].lower() == label.lower() for a in existing) or label == ORCH_LABEL:
        errors.append("this short label is taken")
    if errors:
        return {"ok": False, "errors": errors}
    a = {"name": name, "label": label, "order": max([x["order"] for x in existing] + [0]) + 1,
         "model": data.get("model") or (tool_models()[:1] or ["nvidia/nemotron-3.5-super-vl-120b-a12b"])[0],
         "max_iterations": int(data.get("max_iterations") or 40), "color": data.get("color") or "yellow",
         "role": data.get("role") or "new specialist", "skills": data.get("skills") or ["project-standards"],
         "tools": data.get("tools") or ["pc_read_file", "pc_write_file", "list_skills", "read_skill"],
         "description": data.get("description") or f"{name}: describe when the Orchestrator should delegate to it "
                                                   "and what to pass in the task.",
         "prompt": data.get("prompt") or f"You are the {name}. {{SKILLS_NOTE}} Work only in {{P}}. "
                                         "Describe this agent's job, inputs, outputs and rules here. {HANDOFF}",
         "orchestrator": False}
    errors = _validate(a)
    if errors:
        return {"ok": False, "errors": errors}
    path = AGENT_NOTES / f"{name}.md"
    _write(a, path)
    result = rebuild()
    if not result["ok"]:
        path.unlink()
        rebuild()
        return {"ok": False, "errors": ["rebuild failed, agent not created"], "output": result["output"]}
    return {"ok": True, "output": result["output"], "name": name}


def archive(data):
    a = _find(data.get("name", ""))
    if not a:
        return {"ok": False, "errors": ["unknown agent"]}
    if a["orchestrator"]:
        return {"ok": False, "errors": ["the Orchestrator can't be removed"]}
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    src = AGENT_NOTES / a["file"]
    dst = ARCHIVE / f"{time.strftime('%Y%m%d-%H%M%S')} {a['file']}"
    src.rename(dst)
    result = rebuild()
    if not result["ok"]:
        dst.rename(src)
        rebuild()
        return {"ok": False, "errors": ["rebuild failed, agent restored"], "output": result["output"]}
    return {"ok": True, "archived": str(dst.relative_to(SYS.parent)), "output": result["output"]}
