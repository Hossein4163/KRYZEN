"""Jarvis Control Center: edit every file that defines DevPilot and Jarvis, and manage the services.

Editable roots (the PC bridge is deliberately not one of them — it is the sandbox boundary):
  vault    ~/Projects/devpilot/_DevPilot   agents, settings, custom tools, skills, templates, flows
  jarvis   agent/jarvis                    this UI and engine (sessions excluded)
  builder  agent/workflow                  workflow generator + shared note helpers
Saving an agent / settings / tool note rebuilds the mesh and reverts the file if the rebuild fails.
Python files are syntax-checked before they are written.
"""
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import mesh
from projectdata import atomic_write, revision

HERE = Path(__file__).resolve().parent
REPO_DIR = mesh.AGENT_DIR.parent
ROOTS = {"vault": mesh.SYS, "jarvis": HERE, "builder": mesh.WORKFLOW_DIR}
SKIP = {"sessions", "__pycache__", ".git", "node_modules"}
TEXT = {".md", ".json", ".py", ".html", ".css", ".js", ".yml", ".yaml", ".txt", ".canvas", ".service", ".gitignore",
        ".gitkeep", ""}
REBUILD_PREFIXES = ("Agents/", "Tools/", "Settings.md")
UI_FILE = mesh.SYS / "jarvis.json"
UI_DEFAULTS = {
    "name": "K.R.Y.Z.E.N", "subtitle": "DevPilot", "accent": "#22d3ee",
    "greeting": "Good to see you. Describe a project, or say continue to resume the last one.",
    "quick": [{"label": "continue", "text": "continue"},
              {"label": "status", "text": "Where does the active project stand? What's done and what's next?"},
              {"label": "approve plan", "text": "plan approved, start the next milestone"},
              {"label": "autonomous", "text": "go fully autonomous"}],
}


def _path(root, rel):
    base = ROOTS[root].resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise PermissionError("path outside the editable root")
    if any(part in SKIP for part in p.relative_to(base).parts):
        raise PermissionError("this folder is not editable here")
    return p


def tree(root):
    base = ROOTS[root]
    out = []
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if any(part in SKIP for part in rel.parts) or p.is_symlink():
            continue
        if p.is_dir() or p.suffix in TEXT:
            out.append({"path": str(rel), "dir": p.is_dir()})
    return {"root": root, "base": str(base), "entries": out}


def read(root, rel):
    p = _path(root, rel)
    content = p.read_text(errors="replace")
    return {"root": root, "path": rel, "content": content, "size": p.stat().st_size, "revision": revision(content)}


def _check(root, rel, content):
    if rel.endswith(".py"):
        try:
            compile(content, rel, "exec")
        except SyntaxError as e:
            return f"Python syntax error line {e.lineno}: {e.msg}"
    if rel.endswith((".json", ".canvas")):
        try:
            json.loads(content)
        except ValueError as e:
            return f"invalid JSON: {e}"
    return None


def _hint(root, rel):
    if root == "vault" and rel.startswith(REBUILD_PREFIXES):
        return "rebuild"
    if root == "vault" and rel.startswith(("Skills/", "Templates/")):
        return "Applies immediately (agents read skills and templates live)."
    if root in ("jarvis", "builder") and rel.endswith(".py"):
        return "Restart Jarvis (Services) to load the new code."
    if root == "jarvis" and rel.endswith(".html"):
        return "Reload this page to see the change."
    if rel == "jarvis.json":
        return "Reload this page to see the change."
    return "Saved."


def save(root, rel, content, expected=None):
    p = _path(root, rel)
    err = _check(root, rel, content)
    if err:
        return {"ok": False, "errors": [err]}
    old = p.read_text() if p.exists() else None
    if expected is not None and expected != revision(old or ""):
        return {"ok": False, "conflict": True, "errors": ["file changed — reload before saving"]}
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, content)
    hint = _hint(root, rel)
    if hint == "rebuild":
        r = mesh.rebuild()
        if not r["ok"]:
            if old is None:
                p.unlink()
            else:
                p.write_text(old)
            mesh.rebuild()
            return {"ok": False, "errors": ["rebuild failed — change reverted"], "output": r["output"]}
        return {"ok": True, "message": "Saved and rebuilt. Agents use it from the next message.", "rebuilt": True, "revision": revision(content)}
    return {"ok": True, "message": hint, "revision": revision(content)}


def create(root, rel, kind="file"):
    p = _path(root, rel)
    if p.exists():
        return {"ok": False, "errors": ["already exists"]}
    if kind == "dir":
        p.mkdir(parents=True)
        return {"ok": True}
    template = ""
    if root == "vault" and rel.startswith("Skills/") and rel.endswith("SKILL.md"):
        name = p.parent.name
        template = f"---\nname: {name}\ndescription: When to use this skill.\n---\n\n# {name}\n\n## Steps\n1. \n"
    if root == "vault" and rel.startswith("Tools/") and rel.endswith(".md"):
        tid = p.stem
        template = (f"---\nid: {tid}\ntitle: {tid.replace('_', ' ').title()}\ncommand: echo {{project}}\n"
                    f"cwd: ~/Projects/devpilot/{{project}}\ntimeout: 300\nparams:\n  - project | string | project slug\n"
                    f"tags:\n  - devpilot/tool\n---\n# {tid}\n\n## Description\nWhat this tool does and when to use it.\n")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(template)
    return {"ok": True, "content": template}


def delete(root, rel):
    p = _path(root, rel)
    if p == ROOTS[root].resolve():
        return {"ok": False, "errors": ["can't delete the root"]}
    trash = mesh.SYS / "Archive" / "files" / time.strftime("%Y%m%d-%H%M%S") / root / rel
    trash.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(trash))
    if root == "vault" and rel.startswith(REBUILD_PREFIXES):
        r = mesh.rebuild()
        if not r["ok"]:
            shutil.move(str(trash), str(p))
            mesh.rebuild()
            return {"ok": False, "errors": ["rebuild failed — restored"], "output": r["output"]}
    return {"ok": True, "archived": str(trash.relative_to(mesh.SYS.parent))}


def rename(root, rel, to):
    src, dst = _path(root, rel), _path(root, to)
    if dst.exists():
        return {"ok": False, "errors": ["target exists"]}
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    if root == "vault" and (rel.startswith(REBUILD_PREFIXES) or to.startswith(REBUILD_PREFIXES)):
        r = mesh.rebuild()
        if not r["ok"]:
            dst.rename(src)
            mesh.rebuild()
            return {"ok": False, "errors": ["rebuild failed — rename undone"], "output": r["output"]}
    return {"ok": True}


# ---------------------------------------------------------------------------- UI settings
def ui():
    if not UI_FILE.exists():
        UI_FILE.write_text(json.dumps(UI_DEFAULTS, indent=2, ensure_ascii=False))
    try:
        data = json.loads(UI_FILE.read_text())
        if not isinstance(data, dict):
            return dict(UI_DEFAULTS)
        out = {**UI_DEFAULTS, **data}
        for key in ("name", "subtitle", "greeting", "accent"):
            if not isinstance(out[key], str):
                out[key] = UI_DEFAULTS[key]
        if not isinstance(out["quick"], list) or any(not isinstance(q, dict) or
                not isinstance(q.get("label"), str) or not isinstance(q.get("text"), str) for q in out["quick"]):
            out["quick"] = UI_DEFAULTS["quick"]
        if "glass" in out and (not isinstance(out["glass"], (int, float)) or isinstance(out["glass"], bool)):
            out["glass"] = 60
        return out
    except ValueError:
        return UI_DEFAULTS


# ---------------------------------------------------------------------------- services
def _http_ok(url):
    if url == "local":
        return subprocess.run(["which", "agy"], capture_output=True).returncode == 0
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            return r.status < 500
    except Exception:
        return False


def _run(cmd, cwd=None, timeout=120):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r


BRIDGE_URL = os.environ.get("KRYZEN_BRIDGE_URL", "http://127.0.0.1:8765")
BRIDGE_UNIT = os.environ.get("KRYZEN_BRIDGE_UNIT", "pc-bridge")

SERVICES = {
    "agy": {
        "title": "Antigravity CLI (agy)",
        "health": "local",
        "restart": ["agy", "--version"],
        "logs": ["journalctl", "--user", "-u", "jarvis", "-n", "100", "--no-pager"]
    },
    "bridge": {
        "title": "PC Bridge",
        "health": BRIDGE_URL + "/health",
        "restart": ["systemctl", "--user", "restart", BRIDGE_UNIT],
        "logs": ["journalctl", "--user", "-u", BRIDGE_UNIT, "-n", "150", "--no-pager"]
    },
    "jarvis": {
        "title": "K.R.Y.Z.E.N web app",
        "health": "http://127.0.0.1:" + os.environ.get("JARVIS_PORT", "8770") + "/health",
        "restart": ["systemctl", "--user", "restart", "jarvis"],
        "logs": ["journalctl", "--user", "-u", "jarvis", "-n", "150", "--no-pager"]
    },
}


def services():
    out = []
    for key, s in SERVICES.items():
        out.append({"id": key, "title": s["title"], "up": True if s["health"] is None else _http_ok(s["health"])})
    return {"services": out}


def service_action(key, action):
    s = SERVICES.get(key)
    if not s or action not in ("restart", "logs"):
        return {"ok": False, "errors": ["unknown service or action"]}
    try:
        result = _run(s[action], cwd=REPO_DIR, timeout=180)
    except Exception as e:
        return {"ok": False, "errors": [f"{type(e).__name__}: {e}"]}
    output = (result.stdout + result.stderr).strip()[-12000:]
    if result.returncode:
        return {"ok": False, "errors": [f"{action} failed (exit {result.returncode})"], "output": output}
    return {"ok": True, "output": output}
