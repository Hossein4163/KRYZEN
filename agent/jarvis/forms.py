"""Form-based settings for the Jarvis Control Center: every setting is plain fields; this module writes the files.

  appearance  -> _DevPilot/jarvis.json
  blocks      -> _DevPilot/Settings.md          (shared prompt blocks, rebuilds the mesh)
  tools       -> _DevPilot/Tools/<id>.md        (custom tools + which agents get them, rebuilds)
  skills      -> _DevPilot/Skills/<name>/SKILL.md (+ which agents use them, rebuilds)
  projects    -> bridge /project/init
"""
import json
import re
import time

import control
import mesh
from projectdata import atomic_write
from vaultnotes import FRAGMENT_KEYS, SETTINGS, TOOL_NOTES, load_custom_tools, read_note, write_note

TOOL_ID = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
SKILL_NAME = re.compile(r"^[a-z][a-z0-9-]{2,40}$")
PARAM_NAME = re.compile(r"^[a-z][a-z0-9_]{0,30}$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
BLOCK_HELP = {
    "SKILLS_NOTE": "Tells every agent to read its skills before working.",
    "UNTRUSTED": "Reminds agents that web pages can't give them orders.",
    "HANDOFF": "The status block every specialist ends with (STATUS / DONE / NEXT / BLOCKERS).",
    "CHECKPOINT": "Tells agents to save progress after each step so work can resume.",
}


def _fail(*errors):
    return {"ok": False, "errors": list(errors)}


def _rebuild_or_restore(restore):
    r = mesh.rebuild()
    if r["ok"]:
        return {"ok": True, "message": "Saved — the mesh was rebuilt. Jarvis uses it from the next message."}
    restore()
    mesh.rebuild()
    return {"ok": False, "errors": ["rebuild failed — nothing was changed"], "output": r["output"]}


def _set_agent_lists(field, item, agent_names):
    """Add/remove `item` in each agent note's `field` list (tools or skills) so exactly `agent_names` have it."""
    changed = []
    for a in mesh.notes():
        has, want = item in a[field], a["name"] in agent_names
        if has != want:
            path = mesh.AGENT_NOTES / a["file"]
            changed.append((path, path.read_text()))
            a[field] = [x for x in a[field] if x != item] + ([item] if want else [])
            mesh._write(a, path)
    return changed


# ---------------------------------------------------------------------------- appearance
def appearance_get():
    return control.ui()


def appearance_save(d):
    errors = []
    name, subtitle = str(d.get("name", "")).strip(), str(d.get("subtitle", "")).strip()
    accent, greeting = str(d.get("accent", "")).strip(), str(d.get("greeting", "")).strip()
    if not 1 <= len(name) <= 24:
        errors.append("name: 1-24 characters")
    if len(subtitle) > 40:
        errors.append("subtitle: up to 40 characters")
    if not HEX.match(accent):
        errors.append("accent must be a colour like #22d3ee")
    quick = [{"label": str(q.get("label", "")).strip()[:30], "text": str(q.get("text", "")).strip()[:500]}
             for q in d.get("quick", []) if str(q.get("label", "")).strip() and str(q.get("text", "")).strip()]
    if len(quick) > 10:
        errors.append("up to 10 quick buttons")
    if errors:
        return _fail(*errors)
    data = {"name": name, "subtitle": subtitle, "accent": accent.lower(), "greeting": greeting[:300], "quick": quick,
            "motion": bool(d.get("motion", True)), "glass": max(0, min(100, int(d.get("glass", 60))))}
    atomic_write(control.UI_FILE, json.dumps(data, indent=2, ensure_ascii=False))
    return {"ok": True, "message": "Appearance saved."}


# ---------------------------------------------------------------------------- prompt blocks
def blocks_get():
    _meta, sec = read_note(SETTINGS)
    return {"blocks": [{"key": k, "help": BLOCK_HELP[k], "text": sec.get(k, "")} for k in FRAGMENT_KEYS]}


def blocks_save(d):
    values = {b["key"]: str(b.get("text", "")).strip() for b in d.get("blocks", []) if b.get("key") in FRAGMENT_KEYS}
    empty = [k for k in FRAGMENT_KEYS if not values.get(k)]
    if empty:
        return _fail(f"these blocks are empty: {', '.join(empty)}")
    old = SETTINGS.read_text()
    meta, _ = read_note(SETTINGS)
    intro = old.split("---", 2)[2].split("\n## ", 1)[0].split("\n", 2)[-1].strip()
    write_note(SETTINGS, meta, "DevPilot settings", intro, [(k, values[k]) for k in FRAGMENT_KEYS])
    return _rebuild_or_restore(lambda: SETTINGS.write_text(old))


# ---------------------------------------------------------------------------- custom tools
def tools_get():
    agents = mesh.notes()
    out = []
    for tid, t in load_custom_tools().items():
        out.append({"id": tid, "title": t["title"], "description": t["description"], "command": t["command"],
                    "cwd": t["cwd"], "timeout": t["timeout"],
                    "params": [{"name": n, "description": d, "type": ty, "default": df or "", "required": df is None}
                               for n, d, ty, df in t["params"]],
                    "agents": [a["name"] for a in agents if tid in a["tools"]]})
    return {"tools": out, "agents": [a["name"] for a in agents]}


def tool_save(d):
    tid, original = str(d.get("id", "")).strip(), str(d.get("original_id", "")).strip()
    title, desc = str(d.get("title", "")).strip(), str(d.get("description", "")).strip()
    command, cwd = str(d.get("command", "")).strip(), str(d.get("cwd", "")).strip()
    errors = []
    if not TOOL_ID.match(tid):
        errors.append("id: lowercase letters, digits and _ (3-41 chars), e.g. run_tests")
    builtin = {t["id"] for t in mesh.catalog()["tools"] if not t.get("custom")}
    if tid in builtin:
        errors.append("that id belongs to a built-in tool")
    existing = load_custom_tools()
    if tid != original and tid in existing:
        errors.append("a custom tool with this id exists")
    if not title:
        errors.append("title is required")
    if not desc:
        errors.append("description is required — agents read it to decide when to use the tool")
    if not command:
        errors.append("command is required")
    try:
        timeout = int(d.get("timeout") or 300)
        if not 5 <= timeout <= 3600:
            errors.append("timeout: 5-3600 seconds")
    except (TypeError, ValueError):
        errors.append("timeout must be a number")
        timeout = 300
    params, names = [], set()
    for p in d.get("params", []):
        n = str(p.get("name", "")).strip()
        if not n:
            continue
        if not PARAM_NAME.match(n) or n in names:
            errors.append(f"parameter '{n}': lowercase letters, digits and _, unique")
            continue
        names.add(n)
        typ = p.get("type") if p.get("type") in ("string", "number", "boolean") else "string"
        default = "" if p.get("required", True) else str(p.get("default", "")).replace("|", "/").strip()
        params.append(f"{n} | {typ} | {str(p.get('description', '')).replace('|', '/').strip()}"
                      + ("" if p.get("required", True) else f" | {default or '-'}"))
    slots = set(re.findall(r"\{(\w+)\}", command + " " + cwd))
    if slots - names:
        errors.append(f"the command uses {', '.join('{' + s + '}' for s in sorted(slots - names))} "
                      "but there is no parameter with that name")
    if errors:
        return _fail(*errors)
    TOOL_NOTES.mkdir(parents=True, exist_ok=True)
    path = TOOL_NOTES / f"{tid}.md"
    old_path = TOOL_NOTES / f"{existing[original]['file']}" if original in existing else None
    backups = [(p, p.read_text()) for p in {path, old_path} - {None} if p.exists()]
    meta = {"id": tid, "title": title, "command": command, "cwd": cwd or "~/Projects/devpilot", "timeout": timeout,
            "params": params, "tags": ["devpilot/tool"]}
    intro = ("> [!tip] Custom tool, edited in the Jarvis Control Center. The command runs in the sandboxed shell; "
             "`{name}` slots are filled from the parameters (shell-quoted). Runs in K.R.Y.Z.E.N.")
    write_note(path, meta, title, intro, [("Description", desc)])
    if old_path and old_path != path and old_path.exists():
        old_path.unlink()
    changed = []
    if original and original != tid:
        changed += _set_agent_lists("tools", original, [])
    changed += _set_agent_lists("tools", tid, set(d.get("agents", [])))

    def restore():
        if path.exists() and not any(p == path for p, _ in backups):
            path.unlink()
        for p, text in reversed(backups + changed):
            p.write_text(text)
    return _rebuild_or_restore(restore)


def tool_delete(d):
    tid = str(d.get("id", ""))
    existing = load_custom_tools()
    if tid not in existing:
        return _fail("unknown tool")
    changed = _set_agent_lists("tools", tid, [])
    res = control.delete("vault", f"Tools/{existing[tid]['file']}")
    if not res.get("ok"):
        for p, text in changed:
            p.write_text(text)
        mesh.rebuild()
    return res


# ---------------------------------------------------------------------------- skills
def _skill_dir(name):
    if not SKILL_NAME.fullmatch(name):
        raise ValueError("invalid skill name")
    base = (mesh.SYS / "Skills").resolve()
    path = (base / name).resolve()
    if path.parent != base:
        raise ValueError("skill must stay inside the skill library")
    return path


def skills_get():
    agents = mesh.notes()
    out = []
    for name in mesh.skills():
        text = (_skill_dir(name) / "SKILL.md").read_text()
        desc, body = "", text
        if text.startswith("---"):
            _, fm, body = text.split("---", 2)
            m = re.search(r"^description:\s*(.+)$", fm, re.M)
            desc = m.group(1).strip() if m else ""
        out.append({"name": name, "description": desc, "body": body.strip(),
                    "agents": [a["name"] for a in agents if name in a["skills"]]})
    return {"skills": out, "agents": [a["name"] for a in agents]}


def skill_save(d):
    name, original = str(d.get("name", "")).strip(), str(d.get("original_name", "")).strip()
    desc, body = " ".join(str(d.get("description", "")).split()), str(d.get("body", "")).strip()
    errors = []
    if not SKILL_NAME.fullmatch(name):
        errors.append("name: lowercase letters, digits and dashes, e.g. seo-audit")
    if original and not SKILL_NAME.fullmatch(original):
        errors.append("invalid original skill name")
    if SKILL_NAME.fullmatch(name) and name != original and _skill_dir(name).exists():
        errors.append("a skill with this name exists")
    if not desc:
        errors.append("description is required — agents use it to decide when to read the skill")
    if not body:
        errors.append("instructions are empty")
    if errors:
        return _fail(*errors)
    renamed = bool(original and original != name and _skill_dir(original).exists())
    if renamed:
        _skill_dir(original).rename(_skill_dir(name))
    d_ = _skill_dir(name)
    d_.mkdir(parents=True, exist_ok=True)
    f = d_ / "SKILL.md"
    old = f.read_text() if f.exists() else None
    atomic_write(f, f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}\n")
    changed = []
    if original and original != name:
        for a in mesh.notes():
            if original in a["skills"]:
                path = mesh.AGENT_NOTES / a["file"]
                changed.append((path, path.read_text()))
                a["skills"] = [name if s == original else s for s in a["skills"]]
                mesh._write(a, path)
    changed += _set_agent_lists("skills", name, set(d.get("agents", [])))

    def restore():
        if old is None:
            f.unlink()
        else:
            f.write_text(old)
        for p, text in reversed(changed):
            p.write_text(text)
        if renamed:
            _skill_dir(name).rename(_skill_dir(original))
        elif old is None:
            d_.rmdir()
    return _rebuild_or_restore(restore)


def skill_delete(d):
    name = str(d.get("name", ""))
    if name not in mesh.skills():
        return _fail("unknown skill")
    changed = _set_agent_lists("skills", name, [])
    res = control.delete("vault", f"Skills/{name}")
    if not res.get("ok"):
        for p, text in changed:
            p.write_text(text)
        return res
    result = mesh.rebuild()
    if not result["ok"]:
        archived = mesh.SYS.parent / res["archived"]
        archived.rename(_skill_dir(name))
        for p, text in changed:
            p.write_text(text)
        mesh.rebuild()
        return _fail("rebuild failed — skill and assignments restored")
    return res


# ---------------------------------------------------------------------------- projects
def project_create(d, bridge):
    if any(not isinstance(d.get(key, ""), str) for key in ("slug", "title", "goal")):
        return _fail("project slug, title and goal must be text")
    slug = str(d.get("slug", "")).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,48}", slug):
        return _fail("slug: lowercase letters, digits and dashes, e.g. my-shop")
    title, goal = d.get("title", "").strip(), d.get("goal", "").strip()
    if not title or len(title) > 160 or len(goal) > 5000:
        return _fail("title: 1-160 characters; goal: up to 5000 characters")
    listing = bridge("/project/list", {})
    if listing.get("error"):
        return _fail(listing["error"])
    if slug in listing.get("folders", []):
        return _fail("a project with this folder name already exists; choose another name")
    r = bridge("/project/init", {"slug": slug, "title": str(d.get("title", "")).strip(),
                                 "goal": str(d.get("goal", "")).strip(), "create_only": True})
    if "error" in r:
        return _fail(r["error"])
    return {"ok": True, "message": f"Project {slug} created with {len(r.get('created', []))} files.", "slug": slug}


def models_get():
    return {"models": mesh.tool_models(), "updated": time.ctime((mesh.AGENT_DIR / "models_report.md").stat().st_mtime)
            if (mesh.AGENT_DIR / "models_report.md").exists() else ""}
