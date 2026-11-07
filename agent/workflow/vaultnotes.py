"""Read and write DevPilot agent notes (Obsidian markdown with frontmatter). Shared by build_workflow.py and Jarvis."""
import os
from pathlib import Path
from projectdata import atomic_write

VAULT = Path(os.environ.get("KRYZEN_VAULT") or Path.home() / "Projects" / "devpilot").expanduser()
if not (VAULT / "_DevPilot").exists() and (Path.home() / "Projects" / "devpilot" / "_DevPilot").exists():
    VAULT = Path.home() / "Projects" / "devpilot"
SYS = VAULT / "_DevPilot"
AGENT_NOTES = SYS / "Agents"
ARCHIVE = SYS / "Archive"
COLORS = ["gray", "red", "orange", "yellow", "green", "blue", "purple"]


def write_note(path, meta, title, intro, sections):
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines += [f"  - {x}" for x in v]
        else:
            lines.append(f"{k}: {v}")
    lines += ["---", f"# {title}", "", intro, ""]
    for h, body in sections:
        lines += [f"## {h}", body.strip(), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, "\n".join(lines))


def read_note(path):
    text = path.read_text()
    _, fm, body = text.split("---", 2)
    meta, key = {}, None
    for line in fm.strip().splitlines():
        if line.startswith("  - ") and key:
            meta[key].append(line[4:].strip())
        elif ":" in line:
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] == val[-1] == '"':
                val = val[1:-1]          # only strip quotes that wrap the whole value
            meta[key] = [] if val == "" else (int(val) if val.isdigit() else val)
    sections, cur = {}, None
    for line in body.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            sections[cur] = []
        elif cur:
            sections[cur].append(line)
    return meta, {k: "\n".join(v).strip() for k, v in sections.items()}


def note_intro(label, skills):
    links = " · ".join(f"[[Skills/{s}/SKILL|{s}]]" for s in skills)
    return ("> [!tip] Edit the **Description** and **Prompt** sections (and `model`, `max_iterations`, `tools` in the "
            "properties above), then save from the agent editor in K.R.Y.Z.E.N to apply it.\n"
            "> Placeholders: `{SKILLS_NOTE}` `{UNTRUSTED}` `{HANDOFF}` `{CHECKPOINT}` `{P}` (= project folder) "
            "`{WORKSPACE}`. Tool names: see [[Tools]].\n\n"
            f"**Flow:** [[DevPilot Flow.canvas|DevPilot Flow]] · [[Orchestrator]] · [[Home]]  \n**Skills:** {links}")


SETTINGS = SYS / "Settings.md"
TOOL_NOTES = SYS / "Tools"
FRAGMENT_KEYS = ["SKILLS_NOTE", "UNTRUSTED", "HANDOFF", "CHECKPOINT"]


def read_settings(defaults):
    """Shared prompt blocks from _DevPilot/Settings.md (created from `defaults` on first run)."""
    if not SETTINGS.exists():
        intro = ("> [!tip] These blocks are inserted wherever an agent prompt uses `{NAME}`. Edit them, then run "
                 "save from the Control Center in K.R.Y.Z.E.N to rebuild every agent.\n\n"
                 "See [[Home]] · [[Tools]]")
        write_note(SETTINGS, {"tags": ["devpilot/settings"]}, "DevPilot settings", intro,
                   [(k, defaults[k]) for k in FRAGMENT_KEYS])
    _meta, sections = read_note(SETTINGS)
    return {k: sections.get(k, defaults[k]).strip() or defaults[k] for k in FRAGMENT_KEYS}


def load_custom_tools():
    """User-defined tools: _DevPilot/Tools/<id>.md with a shell command template (run in the sandbox).

    Frontmatter: id, title, command (with {param} slots), cwd (optional, may use {param}), timeout,
    params: list of "name | type | description | default" (no default = required). Body: ## Description.
    """
    tools = {}
    if not TOOL_NOTES.exists():
        return tools
    for f in sorted(TOOL_NOTES.glob("*.md")):
        try:
            meta, sec = read_note(f)
        except ValueError:
            continue
        tid = str(meta.get("id", f.stem)).strip()
        params = []
        for p in meta.get("params", []) or []:
            parts = [x.strip() for x in str(p).split("|")]
            if parts and parts[0]:
                # (name, description, type, default) — the same order the Jarvis engine uses
                params.append((parts[0], parts[2] if len(parts) > 2 else "",
                               parts[1] if len(parts) > 1 and parts[1] else "string",
                               ("" if parts[3] == "-" else parts[3]) if len(parts) > 3 else None))
        tools[tid] = {"id": tid, "title": meta.get("title", tid), "command": str(meta.get("command", "")),
                      "cwd": str(meta.get("cwd", "")), "timeout": int(meta.get("timeout", 300) or 300),
                      "description": sec.get("Description", meta.get("title", tid)), "params": params,
                      "file": f.name}
    return tools
