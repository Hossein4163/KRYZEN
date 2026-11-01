"""Intelligence helpers: project memory, repo map, failure playbooks and the verify policy.

Project memory lives in each project at `.devpilot/memory.md` — one fact per line:
  - 2026-10-26 (decision) Use Prisma for the database layer
Agents add facts with `remember`, look them up with `recall`; relevant facts are injected into the coordinator's
context per turn, and a small model extracts new durable facts after each run (setting: auto_memory).
"""
import json
import re
import time

MEMORY_PATH = ".devpilot/memory.md"
MEMORY_HEADER = ("# Project memory\n\nDurable facts, decisions and conventions learned by the agents. "
                 "Edit freely — one fact per line.\n\n")
KINDS = ("decision", "convention", "fact", "gotcha", "preference", "todo")
ENTRY = re.compile(r"^- (\d{4}-\d{2}-\d{2}) \((\w+)\) (.+)$")
STOP = set("the a an and or of to in on for with is are be this that it as at by from use using into not no we you".split())

VERIFY_POLICY = (
    "\nPLAN → ACT → VERIFY: give every delegated task 1-3 concrete acceptance criteria. Before reporting DONE, check "
    "each criterion against evidence (file paths, command output, test result) and list any you could not verify "
    "under BLOCKERS. A handoff without evidence is not done; QA decides final completion.")

FANOUT_POLICY = (
    "\nTEAMWORK — USE EVERY USEFUL SPECIALIST IN PARALLEL: you coordinate; specialists do the work. For any request "
    "with more than one aspect, call the delegate tools of ALL relevant specialists in the SAME response (several tool "
    "calls at once) — they run concurrently. Typical fan-out: Research + Reference + Product for discovery; Planner "
    "after that; Build for code; QA to verify; Content, SEO, Marketing and Operations whenever text, discoverability, "
    "launch or deployment are involved. Give each a self-contained task (goal, project slug, inputs, acceptance "
    "criteria, where to write results) so they do not need each other mid-task. Only serialize when one result is "
    "truly required as input to another. For multi-file code work in a project prefer execute_parallel_tasks with "
    "disjoint files. Do not do specialist work yourself, and never call the same specialist twice in one response.")

MEMORY_POLICY = (
    "\nPROJECT MEMORY: call recall before broad research to reuse what is already known; call remember for durable "
    "decisions, conventions and gotchas (one short sentence each). Never store secrets.")

# (pattern, hint) — matched against failed tool output; first match wins.
PLAYBOOKS = [
    (r"Cannot find module|MODULE_NOT_FOUND|ModuleNotFoundError|No module named",
     "A dependency is missing: install the project's dependencies (install_deps or the package manager) before retrying."),
    (r"EADDRINUSE|address already in use",
     "The port is busy: stop the existing dev server/background job (pc_job_status) or use another port."),
    (r"command not found|: not found|No such file or directory: '?(npm|pnpm|yarn|node|python|cargo|go)",
     "The tool is not on PATH in the sandbox: check the toolchain exists or use the project's local binary."),
    (r"EACCES|Permission denied|is read-only",
     "Permission problem: write only inside the project; vault/_DevPilot is read-only for agents."),
    (r"error TS\d+|Type error:|TypeError:",
     "Type/runtime error: read the exact file:line from the output, fix that code, then re-run the same check."),
    (r"SyntaxError|Unexpected token|ParseError",
     "Syntax error: open the reported file at the reported line; do not rewrite unrelated code."),
    (r"expected_revision|revision mismatch|changed since",
     "The file changed since you read it: read it again and apply your edit to the current content."),
    (r"timed out|Timeout|ETIMEDOUT",
     "Timed out: run long commands in the background and poll with pc_job_status instead of retrying blindly."),
    (r"\b429\b|rate limit",
     "Rate limited: wait and retry less often; batch work instead of many small calls."),
    (r"ENOSPC|No space left",
     "Disk is full: report it under BLOCKERS; do not retry."),
]


def failure_hint(output):
    for pattern, hint in PLAYBOOKS:
        if re.search(pattern, output[:20000], re.I):
            return "\n[playbook] " + hint
    return ""


def repo_map_command(path="."):
    """Shell command (run in the bridge sandbox, project cwd) that lists symbol definitions per file."""
    safe = path if re.fullmatch(r"[\w./-]{1,200}", path or ".") and ".." not in path else "."
    return ("rg -n --no-heading --max-columns 160 -g '!node_modules' -g '!.git' -g '!dist' -g '!build' "
            "-g '!.next' -g '!*.min.*' -g '!*.lock' -g '!.devpilot' "
            r"-e '^\s*(export\s+)?(default\s+)?(async\s+)?(function|class|interface|type|enum)\s+\w+' "
            r"-e '^\s*(export\s+)?const\s+\w+\s*=\s*(async\s*)?(\(|function)' "
            r"-e '^\s*(async\s+)?def\s+\w+' -e '^\s*class\s+\w+' "
            r"-e '^\s*(pub\s+)?(fn|struct|enum|trait|impl)\b' -e '^\s*func\s' "
            f"-- {safe} 2>/dev/null | head -n 900")


def format_repo_map(raw, limit=9000):
    files = {}
    for line in raw.splitlines():
        m = re.match(r"^(.+?):(\d+):(.*)$", line)
        if not m:
            continue
        files.setdefault(m[1], []).append(f"  {m[2]}: {m[3].strip()[:110]}")
    if not files:
        return "No symbols found (empty project, or an unsupported language)."
    out = []
    for name in sorted(files):
        out.append(name)
        out.extend(files[name][:40])
        if len(files[name]) > 40:
            out.append(f"  … {len(files[name]) - 40} more")
    text = "\n".join(out)
    return text if len(text) <= limit else text[:limit] + "\n…[map truncated; pass a sub-folder path for detail]"


def parse_memory(text):
    out = []
    for line in (text or "").splitlines():
        m = ENTRY.match(line.strip())
        if m:
            out.append({"date": m[1], "kind": m[2], "text": m[3]})
    return out


def words(text):
    return {w for w in re.findall(r"[\w؀-ۿ]{3,}", (text or "").lower()) if w not in STOP}


def recall(entries, query, k=8):
    q = words(query)
    scored = []
    for i, e in enumerate(entries):
        overlap = len(q & words(e["text"]))
        bonus = 1 if e["kind"] in ("decision", "convention", "gotcha") else 0
        if overlap or not q:
            scored.append((overlap * 3 + bonus + i / max(len(entries), 1), e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:k]]


def format_entries(entries):
    return "\n".join(f"- {e['date']} ({e['kind']}) {e['text']}" for e in entries)


def memory_line(text, kind):
    kind = kind if kind in KINDS else "fact"
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not 4 <= len(text) <= 400:
        raise ValueError("a memory must be one sentence of 4-400 characters")
    if re.search(r"(api[_-]?key|password|secret|token)\s*[:=]\s*\S{8,}|nvapi-|sk-[A-Za-z0-9]{16,}", text, re.I):
        raise ValueError("refusing to store something that looks like a secret")
    return f"- {time.strftime('%Y-%m-%d')} ({kind}) {text}\n"


EXTRACT_PROMPT = (
    "From this agent run, list at most 5 DURABLE project facts worth remembering next time: decisions made, "
    "conventions, gotchas, user preferences. Skip anything temporary, obvious, or already in KNOWN. Never include secrets. "
    'Reply with JSON only: [{"kind": "decision|convention|fact|gotcha|preference", "text": "one sentence"}] or [].')


def parse_extracted(reply, known):
    try:
        m = re.search(r"\[[\s\S]*\]", reply or "")
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    have = {e["text"].lower() for e in known}
    out = []
    for it in items[:5]:
        if isinstance(it, dict) and isinstance(it.get("text"), str) and it["text"].lower() not in have:
            try:
                out.append(memory_line(it["text"], it.get("kind", "fact")))
            except ValueError:
                pass
    return out
