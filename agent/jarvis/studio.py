"""Obsidian Canvas editing, canonical Markdown plans and run context for Jarvis Studio.

Generated canvases remain read-only; user canvases are never regenerated. Content hashes
protect edits made concurrently in Obsidian. All project access uses the sandboxed bridge.
"""
import copy
import hashlib
import json
import math
import re
import threading
import time
import uuid
from pathlib import PurePosixPath

import codetools
import mesh
from projectdata import parse_tasks

LOCK = threading.RLock()
GENERATED = {"DevPilot Flow.canvas", "Auto-Resume Flow.canvas"}
NAME = re.compile(r"^[\w][\w .()-]{0,90}\.canvas$", re.UNICODE)
SIDES = {"top", "right", "bottom", "left"}
PLAN_PATH = "docs/plan/PLAN.md"
APPROVAL_PATH = ".devpilot/plan-approval.json"


def revision(text):
    return hashlib.sha256(text.encode()).hexdigest()


def fail(message, **extra):
    return {"ok": False, "errors": [message], **extra}


def _flow_path(name):
    if not isinstance(name, str) or not NAME.fullmatch(name) or ".." in name:
        raise ValueError("use a canvas name containing letters, numbers, spaces or dashes")
    base = (mesh.SYS / "Flows").resolve()
    path = (base / name).resolve()
    if path.parent != base:
        raise ValueError("canvas must stay inside Flows")
    return path


def _atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(text)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def settings():
    path = mesh.SYS / "jarvis-studio.json"
    return json.loads(path.read_text()) if path.exists() else {"active_flow": ""}


def validate_canvas(canvas):
    if not isinstance(canvas, dict) or not isinstance(canvas.get("nodes"), list) or not isinstance(canvas.get("edges"), list):
        raise ValueError("canvas needs nodes and edges arrays")
    if len(canvas["nodes"]) > 500 or len(canvas["edges"]) > 1500:
        raise ValueError("canvas limit: 500 nodes and 1500 connections")
    ids = set()
    for node in canvas["nodes"]:
        if not isinstance(node, dict):
            raise ValueError("each node must be an object")
        nid = node.get("id")
        if not isinstance(nid, str) or not nid or nid in ids:
            raise ValueError("every node needs a unique, nonempty id")
        ids.add(nid)
        kind = node.get("type")
        if kind not in ("text", "file", "group", "link"):
            raise ValueError("unknown node type")
        for key in ("x", "y", "width", "height"):
            value = node.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{key} must be a finite number")
            if abs(value) > 1000000 or (key in ("width", "height") and value <= 0):
                raise ValueError(f"invalid {key}")
        key = {"text": "text", "file": "file", "link": "url", "group": "label"}[kind]
        if not isinstance(node.get(key, ""), str):
            raise ValueError(f"{key} must be text")
        if kind == "file":
            path = PurePosixPath(node.get("file", ""))
            if path.is_absolute() or ".." in path.parts or "\\" in str(path):
                raise ValueError("file cards must reference relative vault paths")
    edge_ids = set()
    for edge in canvas["edges"]:
        if not isinstance(edge, dict):
            raise ValueError("each connection must be an object")
        eid = edge.get("id")
        if not isinstance(eid, str) or not eid or eid in edge_ids:
            raise ValueError("every connection needs a unique id")
        edge_ids.add(eid)
        if edge.get("fromNode") not in ids or edge.get("toNode") not in ids:
            raise ValueError("connection refers to a missing node")
        for key in ("fromSide", "toSide"):
            if edge.get(key, "right" if key == "fromSide" else "left") not in SIDES:
                raise ValueError("invalid connection side")
        if not isinstance(edge.get("label", ""), str):
            raise ValueError("connection labels must be text")
    # Also reject NaN / Infinity in extension fields, while preserving extensions.
    json.dumps(canvas, allow_nan=False)
    return canvas


def flows_get():
    active = settings().get("active_flow", "")
    flows_dir = mesh.SYS / "Flows"
    flows_dir.mkdir(parents=True, exist_ok=True)
    custom_flow = flows_dir / "Custom Flow.canvas"
    sys_flow = flows_dir / "DevPilot Flow.canvas"
    if sys_flow.exists() and not custom_flow.exists():
        try:
            custom_flow.write_text(sys_flow.read_text())
        except OSError:
            pass

    out = []
    for path in sorted(flows_dir.glob("*.canvas")):
        try:
            canvas = json.loads(path.read_text())
            out.append({"name": path.name, "readonly": path.name in GENERATED, "active": path.name == active,
                        "nodes": len(canvas.get("nodes", [])), "edges": len(canvas.get("edges", []))})
        except (OSError, ValueError):
            continue
    return {"flows": out, "active": active}


def flow_get(name):
    path = _flow_path(name)
    text = path.read_text()
    return {"name": name, "readonly": name in GENERATED, "revision": revision(text), "canvas": json.loads(text)}


def flow_save(data):
    name = data.get("name", "")
    path = _flow_path(name)
    if name in GENERATED:
        return fail("generated flow — duplicate it before editing")
    canvas = validate_canvas(data.get("canvas"))
    with LOCK:
        old = path.read_text() if path.exists() else ""
        if path.exists() and data.get("revision") != revision(old):
            return fail("This canvas changed in another window or Obsidian. Reload before saving.", conflict=True)
        if not path.exists() and data.get("revision"):
            return fail("This canvas was moved or removed. Create a new canvas.", conflict=True)
        text = json.dumps(canvas, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        _atomic(path, text)
    return {"ok": True, "name": name, "revision": revision(text)}


def flow_create(data):
    name = str(data.get("name", "")).strip()
    if not name.endswith(".canvas"):
        name += ".canvas"
    path = _flow_path(name)
    with LOCK:
        if path.exists() or name in GENERATED:
            return fail("a canvas with this name already exists")
        source = data.get("source")
        canvas = copy.deepcopy(flow_get(source)["canvas"]) if source else {"nodes": [], "edges": []}
        result = flow_save({"name": name, "canvas": canvas})
    return {**result, "flow": flow_get(name)}


def linked_agents(canvas):
    files = {"_DevPilot/Agents/" + a["file"]: a for a in mesh.notes()}
    return {n["id"]: files[n["file"]] for n in canvas.get("nodes", [])
            if n.get("type") == "file" and n.get("file") in files}


def flow_activate(data):
    name = str(data.get("name", ""))
    if name:
        canvas = validate_canvas(flow_get(name)["canvas"])
        if not any(not a["orchestrator"] for a in linked_agents(canvas).values()):
            return fail("add at least one linked specialist agent card before activating routing")
    with LOCK:
        _atomic(mesh.SYS / "jarvis-studio.json", json.dumps({**settings(), "active_flow": name}, indent=2))
    return {"ok": True, "active": name}


def routing():
    """Return active specialist allowlist and graph context, loaded afresh for each run."""
    name = settings().get("active_flow", "")
    if not name:
        return None
    # A removed/invalid active canvas must fail closed, not silently restore all tools.
    canvas = validate_canvas(flow_get(name)["canvas"])
    agents = linked_agents(canvas)
    allowed = {a["name"] for a in agents.values() if not a["orchestrator"]}
    if not allowed:
        raise ValueError("active canvas has no specialist cards; disable routing or repair the canvas")
    labels = {n["id"]: (agents[n["id"]]["name"] if n["id"] in agents else
               n.get("text", n.get("label", n.get("file", "")))[:500]) for n in canvas["nodes"]}
    graph = [{"from": labels[e["fromNode"]], "to": labels[e["toNode"]], "label": e.get("label", "")}
             for e in canvas["edges"]]
    return {"name": name, "allowed": sorted(allowed), "connections": graph,
            "notes": [n["text"][:1500] for n in canvas["nodes"] if n["type"] == "text"][:25]}



def _read(bridge, slug, path):
    result = codetools.read(bridge, slug, path)
    if result.get("error"):
        if "not found" in str(result["error"]).lower() or "no such file" in str(result["error"]).lower():
            return None
        raise ValueError(result["error"])
    return result.get("content", "")


def _write(bridge, slug, path, content, expected=None):
    result = codetools.save(bridge, slug, path, content, revision=expected)
    if result.get("error"):
        raise ValueError(result["error"])
    return result


def _project(bridge, slug):
    codetools._root(slug)
    projects = bridge("/project/list", {})
    if projects.get("error"):
        raise ValueError(projects["error"])
    if slug not in projects.get("folders", []):
        raise ValueError("select an existing project")


def _approval(bridge, slug, rev):
    raw = _read(bridge, slug, APPROVAL_PATH)
    try:
        approval = json.loads(raw) if raw else {"status": "pending"}
        if not isinstance(approval, dict):
            approval = {"status": "pending"}
    except ValueError:
        approval = {"status": "pending"}
    if approval.get("status") == "approved" and approval.get("revision") != rev:
        return {**approval, "status": "outdated"}
    return approval


def plan_get(bridge, slug):
    _project(bridge, slug)
    content = _read(bridge, slug, PLAN_PATH)
    exists = content is not None
    content = content or ""
    rev = revision(content)
    tasks = parse_tasks(content)
    raw = _read(bridge, slug, ".devpilot/STATE.json")
    try:
        state = json.loads(raw) if raw else {}
        if not isinstance(state, dict):
            state = {}
    except ValueError:
        state = {}
    return {"slug": slug, "content": content, "revision": rev, "exists": exists, "tasks": tasks,
            "progress": {"done": sum(t["done"] for t in tasks), "total": len(tasks)}, "state": state,
            "approval": _approval(bridge, slug, rev)}


def plan_save(bridge, data):
    slug, content = data.get("slug", ""), data.get("content", "")
    if not isinstance(content, str) or len(content) > 1000000:
        return fail("plan must be text under 1 MB")
    with LOCK:
        current = plan_get(bridge, slug)
        if data.get("revision") != current["revision"]:
            return fail("Plan changed in another window or Obsidian. Reload before saving.", conflict=True)
        _write(bridge, slug, PLAN_PATH, content, current["revision"])
    return {"ok": True, "revision": revision(content), "plan": plan_get(bridge, slug)}


def plan_task(bridge, data):
    with LOCK:
        current = plan_get(bridge, data.get("slug", ""))
        if data.get("revision") != current["revision"]:
            return fail("Plan changed. Reload before updating tasks.", conflict=True)
        task = next((t for t in current["tasks"] if t["line"] == data.get("line")), None)
        if not task or not isinstance(data.get("done"), bool):
            return fail("select a real task and a completion state")
        lines = current["content"].splitlines(keepends=True)
        index = task["line"] - 1
        line = lines[index]
        if re.match(r"^\s*[-*]\s+\[", line):
            lines[index] = re.sub(r"\[([ xX])\]", "[x]" if data["done"] else "[ ]", line, count=1)
        else:
            # Mark only the task ID cell; never alter acceptance criteria or task wording.
            line = re.sub(r"^(\s*\|\s*T\d+)\s*✅?\s*\|", r"\1 |", line, count=1)
            line = line.replace("✅", "")
            if data["done"]:
                line = re.sub(r"^(\s*\|\s*T\d+)", r"\1 ✅", line, count=1)
            lines[index] = line
        result = plan_save(bridge, {"slug": current["slug"], "revision": current["revision"],
                                    "content": "".join(lines)})
        return result


def plan_approval(bridge, data):
    with LOCK:
        plan = plan_get(bridge, data.get("slug", ""))
        if data.get("revision") != plan["revision"]:
            return fail("Plan changed. Review the current plan before approving.", conflict=True)
        if data.get("status") not in ("approved", "pending"):
            return fail("approval must be approved or pending")
        if data["status"] == "approved" and (not plan["content"].strip() or not plan["tasks"]):
            return fail("add a plan with actionable tasks before approving")
        approval = {"status": data["status"], "revision": plan["revision"],
                    "approved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "source": "Jarvis Plan control"}
        _write(bridge, plan["slug"], APPROVAL_PATH, json.dumps(approval, indent=2))
    return {"ok": True, "approval": approval}


def overview():
    return {"flows": len(flows_get()["flows"]), "skills": len(mesh.skills()), "agents": len(mesh.notes()),
            "tools": len(mesh.catalog().get("tools", [])), "active_flow": settings().get("active_flow", "")}
