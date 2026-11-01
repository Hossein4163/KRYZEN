"""Skills v2: usage insights from traces, versions + rollback, imports, drafts from runs, test prompts.

Vault layout (all under _DevPilot/):
  Skills/<name>/SKILL.md                      live skills (unchanged format)
  Archive/skill-versions/<name>/<stamp>.md    previous versions, written before every save/rollback
  Archive/skill-drafts/<name>.json            proposed skills waiting for approval
  kryzen-skill-tests.json                     {skill: test prompt}
Per-project overrides: <project>/.devpilot/skills/<name>.md replaces the vault text for that project.
"""
import json
import re
import shutil
import time
from pathlib import Path

import mesh
from projectdata import atomic_write

SKILLS = mesh.SYS / "Skills"
VERSIONS = mesh.SYS / "Archive" / "skill-versions"
DRAFTS = mesh.SYS / "Archive" / "skill-drafts"
TESTS = mesh.SYS / "kryzen-skill-tests.json"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
STAMP = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
IMPORT_ROOTS = [Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills"]
_stats_cache = {"key": None, "data": None}


def _name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError("invalid skill name")
    return name


def _frontmatter(text):
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            m = re.search(r"^description:\s*(.+)$", parts[1], re.M)
            return (m.group(1).strip() if m else ""), parts[2].strip()
    return "", text.strip()


# ----------------------------------------------------------------------------- usage insights
def usage_stats(sessions_dir):
    """Count read_skill calls per skill across all traces (cached by trace mtimes)."""
    files = sorted(Path(sessions_dir).glob("*/trace.jsonl"))
    key = tuple((str(f), f.stat().st_mtime) for f in files)
    if _stats_cache["key"] == key:
        return _stats_cache["data"]
    stats = {}
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                if '"tool_call"' not in line or "kill" not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("kind") != "tool_call" or "skill" not in str(r.get("tool", "")).lower() \
                        or "list" in str(r.get("tool", "")).lower():
                    continue
                args = r.get("args") if isinstance(r.get("args"), dict) else {}
                name = str(args.get("name") or args.get("skill") or "")
                if not name:
                    continue
                s = stats.setdefault(name, {"reads": 0, "ok": 0, "last": 0, "agents": {}})
                s["reads"] += 1
                s["ok"] += int(bool(r.get("ok")))
                s["last"] = max(s["last"], r.get("t", 0))
                agent = r.get("agent", "?")
                s["agents"][agent] = s["agents"].get(agent, 0) + 1
    _stats_cache.update(key=key, data=stats)
    return stats


def insights(sessions_dir, skills_list):
    stats = usage_stats(sessions_dir)
    tests = load_tests()
    out = []
    for sk in skills_list:
        st = stats.get(sk["name"], {"reads": 0, "ok": 0, "last": 0, "agents": {}})
        out.append({"name": sk["name"], "description": sk["description"], "assigned": sk["agents"],
                    "reads": st["reads"], "ok_rate": round(st["ok"] / st["reads"], 2) if st["reads"] else None,
                    "last_used": st["last"], "used_by": st["agents"], "versions": len(versions(sk["name"])),
                    "test": tests.get(sk["name"], "")})
    out.sort(key=lambda x: (-x["reads"], x["name"]))
    unused = [x["name"] for x in out if x["assigned"] and not x["reads"]]
    return {"skills": out, "unused_assigned": unused, "drafts": drafts()}


# ----------------------------------------------------------------------------- versions
def snapshot(name):
    """Save the current SKILL.md before it changes. Returns the stamp or None if the skill does not exist yet."""
    try:
        name = _name(name)
    except ValueError:
        return None
    src = SKILLS / name / "SKILL.md"
    if not src.exists():
        return None
    folder = VERSIONS / name
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    n = 0
    while (folder / f"{stamp}{'-' + str(n) if n else ''}.md").exists():
        n += 1
    stamp = f"{stamp}{'-' + str(n) if n else ''}"
    shutil.copy2(src, folder / f"{stamp}.md")
    return stamp


def versions(name):
    folder = VERSIONS / _name(name)
    if not folder.exists():
        return []
    return [{"stamp": p.stem, "size": p.stat().st_size} for p in sorted(folder.glob("*.md"), reverse=True)]


def version_get(name, stamp):
    if not STAMP.fullmatch(stamp or ""):
        raise ValueError("invalid version")
    return (VERSIONS / _name(name) / f"{stamp}.md").read_text()


def rollback(name, stamp):
    text = version_get(name, stamp)
    dst = SKILLS / _name(name) / "SKILL.md"
    if not dst.exists():
        raise ValueError("unknown skill")
    snapshot(name)
    atomic_write(dst, text)
    return {"ok": True, "message": f"{name} restored to {stamp} (the previous text was saved as a version)"}


# ----------------------------------------------------------------------------- imports
def importable():
    have = set(mesh.skills())
    out = []
    for root in IMPORT_ROOTS:
        if not root.exists():
            continue
        for d in sorted(root.iterdir()):
            f = d / "SKILL.md"
            try:
                if not f.exists() or d.resolve().is_relative_to(SKILLS.resolve()):
                    continue
                desc, _ = _frontmatter(f.read_text()[:4000])
            except OSError:
                continue
            out.append({"name": d.name, "source": str(d), "description": desc[:300],
                        "installed": d.name in have, "valid_name": bool(NAME.fullmatch(d.name))})
    return {"skills": out}


def import_skill(source, name=None):
    src = Path(str(source)).expanduser().resolve()
    if not any(src.is_relative_to(r.resolve()) for r in IMPORT_ROOTS if r.exists()) or not (src / "SKILL.md").exists():
        raise ValueError("choose a skill from the importable list")
    name = _name(name or src.name)
    dst = SKILLS / name
    if dst.exists():
        raise ValueError("a skill with this name exists")
    def ignore(_dir, names):
        return [n for n in names if n in (".git", "node_modules", "__pycache__")]
    shutil.copytree(src, dst, ignore=ignore, symlinks=False)
    total = sum(p.stat().st_size for p in dst.rglob("*") if p.is_file())
    if total > 5_000_000:
        shutil.rmtree(dst)
        raise ValueError("skill folder is larger than 5 MB")
    return {"ok": True, "message": f"Imported {name}. Assign it to agents in Skills to use it."}


# ----------------------------------------------------------------------------- drafts from runs
DRAFT_PROMPT = (
    "You write reusable agent skills. From this successful agent run, extract ONE reusable procedure that would help "
    "next time (not project-specific facts). Reply with JSON only: "
    '{"name": "kebab-case-name", "description": "when to use it, one sentence", '
    '"body": "markdown instructions: when to use, steps, checks, pitfalls (max 40 lines)"}')


def run_digest(trace_records, reply=""):
    lines = []
    for r in trace_records:
        if r.get("kind") == "tool_call":
            args = r.get("args")
            a = json.dumps(args, ensure_ascii=False)[:160] if args is not None else ""
            lines.append(f"{r.get('agent', '')}: {r.get('tool')} {a} -> {'ok' if r.get('ok') else 'FAILED'}")
        elif r.get("kind") == "delegation":
            lines.append(f"{r.get('agent')} delegated to {r.get('to')}: {str(r.get('task', ''))[:200]}")
    text = "\n".join(lines)[-16000:]
    return text + ("\n\nFINAL RESULT:\n" + reply[:4000] if reply else "")


def save_draft(raw):
    m = re.search(r"\{[\s\S]*\}", raw or "")
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    name = re.sub(r"[^a-z0-9-]+", "-", str(d.get("name", "")).lower()).strip("-")[:60]
    if not NAME.fullmatch(name or "") or not d.get("description") or not d.get("body"):
        raise ValueError("the model did not return a usable skill draft; try again")
    DRAFTS.mkdir(parents=True, exist_ok=True)
    draft = {"name": name, "description": str(d["description"])[:300], "body": str(d["body"])[:12000],
             "created": time.time()}
    atomic_write(DRAFTS / f"{name}.json", json.dumps(draft, indent=2, ensure_ascii=False))
    return draft


def drafts():
    if not DRAFTS.exists():
        return []
    out = []
    for f in sorted(DRAFTS.glob("*.json")):
        try:
            out.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            pass
    return out


def discard_draft(name):
    f = DRAFTS / f"{_name(name)}.json"
    f.unlink(missing_ok=True)
    return {"ok": True}


# ----------------------------------------------------------------------------- test prompts
def load_tests():
    try:
        data = json.loads(TESTS.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def set_test(name, prompt):
    name = _name(name)
    prompt = str(prompt or "").strip()
    if len(prompt) > 2000:
        raise ValueError("test prompt must be under 2000 characters")
    tests = load_tests()
    if prompt:
        tests[name] = prompt
    else:
        tests.pop(name, None)
    atomic_write(TESTS, json.dumps(tests, indent=2, ensure_ascii=False))
    return {"ok": True}
