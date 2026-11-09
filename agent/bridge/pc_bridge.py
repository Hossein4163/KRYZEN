#!/usr/bin/env python3
"""PC Bridge: lets the AI agents act on this PC through sandboxed tools.

Endpoints (all POST, JSON body, header `X-Bridge-Token: <token>`):
  /shell        {cmd, cwd?, timeout?, background?}        run a shell command inside a bubblewrap sandbox
  /fs/read      {path, offset?, limit?}                   read a text file      } all paths and cwds must be
  /fs/write     {path, content, append?}                  write a text file     } inside the workspace
  /fs/list      {path, depth?}                            list a directory      } (~/Projects)
  /agy          {prompt, cwd, mode?, model?, sandbox?, accept_all?, continue?, new_project?, timeout?, background?}
                                                          run the Antigravity CLI headless (--sandbox on by
                                                          default; accept_all needs PC_BRIDGE_ALLOW_AGY_ACCEPT_ALL=1)
  /browser      {args, cwd?, timeout?}                    run agent-browser (args: string or list)
  /skills/list  {}                                        list installed skills
  /skills/read  {name, file?}                             read a skill's SKILL.md (or another file in it)
  /web/fetch    {url, max_chars?}                         fetch a web page as plain text
  /jobs/get     {id, tail?}                               status/output of a background job
  /project/init {slug, title?, goal?}                      create a project from templates/project
  /project/list {}                                        list projects (INDEX.md + folders)
  /project/checkpoint {slug, phase?, status?, milestone?, task?, next_action?, notes?, agent?}
                                                          save resume state (.devpilot/STATE.json)
  /project/resume {slug?}                                 resume brief (default: last active project)
  /autoresume/attempt {error?}                            rate limiter for automatic resumes
Every /shell, /fs/write, /agy and /project/init call inside a project is journaled to
<project>/.devpilot/journal.jsonl.
  /health       (GET, no token)

It runs in-process with the web app; if you start it as a server, bind it to localhost only.
"""
import html
import json
import os
import re
import shlex
import subprocess
import sys
import signal
import threading
import time
import urllib.request
from urllib.parse import urlparse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_DIR = HERE.parent
sys.path.insert(0, str(AGENT_DIR / "workflow"))
sys.path.insert(0, str(AGENT_DIR / "jarvis"))
from projectdata import atomic_write, parse_tasks, revision, continuation
HOST = os.environ.get("PC_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("PC_BRIDGE_PORT", "8765"))
TOKEN_FILE = HERE / ".token"
TOKEN = os.environ.get("PC_BRIDGE_TOKEN") or (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "")
def get_default_workspace():
    env_ws = os.environ.get("PC_BRIDGE_WORKSPACE")
    if env_ws:
        return Path(env_ws).expanduser().resolve()
    space_proj = Path.home() / "Space" / "Projects"
    if space_proj.exists():
        return space_proj.resolve()
    return (Path.home() / "Projects" / "devpilot").expanduser().resolve()

WORKSPACE = get_default_workspace()
LINKS_FILE = ".linked-projects.json"
HIDDEN_FILE = ".hidden-projects.json"
MAX_OUT = int(os.environ.get("PC_BRIDGE_MAX_OUT", "20000"))
# agy's --dangerously-skip-permissions is always enabled for autonomous operation
ALLOW_AGY_ACCEPT_ALL = True
SKILL_ROOTS = [
    Path.home() / "Projects" / "devpilot" / "_DevPilot" / "Skills",
    AGENT_DIR / "skills",
    AGENT_DIR / "vendor",
    Path.home() / ".agents" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".gemini" / "antigravity-cli" / "builtin" / "skills",
]

JOBS = {}
JOBS_LOCK = threading.Lock()
FILES_LOCK = threading.RLock()
PROJECT_LOCK = threading.RLock()
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")


def clip(text, limit=MAX_OUT):
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n…[{len(text) - limit} chars truncated]…\n" + text[-half:]


def _linked_roots():
    """Folders outside the workspace that the user added as projects (Projects > +)."""
    try:
        return [Path(p) for p in json.loads((WORKSPACE / LINKS_FILE).read_text())]
    except (OSError, ValueError):
        return []


def _hidden_projects():
    """Workspace folders the user removed from the Projects list. Their files stay on disk."""
    try:
        return set(json.loads((WORKSPACE / HIDDEN_FILE).read_text()))
    except (OSError, ValueError):
        return set()


def _write_workspace_json(name, value):
    tmp = WORKSPACE / (name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(WORKSPACE / name)


def resolve(path, base=None):
    """Resolve a path and refuse anything outside the workspace and linked project folders (symlinks included)."""
    p = Path(os.path.expanduser(str(path or ".")))
    if not p.is_absolute():
        p = (base or WORKSPACE) / p
    p = p.resolve()
    if p != WORKSPACE and WORKSPACE not in p.parents and not any(p == r or r in p.parents for r in _linked_roots()):
        raise PermissionError(f"{p} is outside the workspace {WORKSPACE}")
    return p


HOME = Path.home()
SANDBOX_CACHE = WORKSPACE / ".sandbox-cache"
# The Obsidian vault's control folders: agents may read them but never change their own instructions.
PROTECTED = [WORKSPACE / "_DevPilot", WORKSPACE / ".obsidian"]


def writable(p):
    """Refuse writes inside protected folders (prompts, skills, templates, Obsidian config)."""
    for d in PROTECTED:
        if p == d or d in p.parents:
            raise PermissionError(f"{p} is read-only for agents (edit it in Obsidian)")
    return p


def sandboxed(cmd, cwd):
    """Wrap a shell command in bubblewrap: an empty home with only the workspace writable,
    toolchains read-only, Docker socket accessible, and no user sockets or removable drives."""
    SANDBOX_CACHE.mkdir(parents=True, exist_ok=True)
    argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--tmpfs", str(HOME), "--tmpfs", f"/run/user/{os.getuid()}", "--tmpfs", f"/run/media/{HOME.name}"]
    for sock in ("/run/docker.sock", "/var/run/docker.sock"):
        if os.path.exists(sock):
            argv += ["--bind", sock, sock]
    for ro in (".local/share/mise", ".local/bin", ".config/mise", ".gitconfig"):
        if (HOME / ro).exists():
            argv += ["--ro-bind", str(HOME / ro), str(HOME / ro)]
    argv += ["--bind", str(WORKSPACE), str(WORKSPACE)]
    for root in _linked_roots():
        if root.is_dir():
            argv += ["--bind", str(root), str(root)]
    for d in PROTECTED:
        if d.exists():
            argv += ["--ro-bind", str(d), str(d)]
    argv += ["--chdir", str(cwd),
             "--unshare-pid", "--unshare-ipc", "--die-with-parent", "--new-session",
             "sh", "-c", cmd]
    return argv


PRIVILEGE_ESCALATION = re.compile(r"\b(sudo|pkexec|su|doas)\b", re.IGNORECASE)


def clean_env():
    keep = ("PATH", "LANG", "LC_ALL", "USER", "LOGNAME", "SHELL")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update(HOME=str(HOME), NO_COLOR="1", TERM="dumb",
               XDG_CACHE_HOME=str(SANDBOX_CACHE), npm_config_cache=str(SANDBOX_CACHE / "npm"))
    if "SUDO_PASS" in os.environ:
        env["SUDO_PASS"] = os.environ["SUDO_PASS"]
    if "SUDO_PASSWORD" in os.environ:
        env["SUDO_PASSWORD"] = os.environ["SUDO_PASSWORD"]
    return env


def as_bool(v, default=False):
    if v is None or str(v).strip() == "":
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


def run(argv, cwd, timeout, background, shell=False):
    cwd = resolve(cwd)
    cwd.mkdir(parents=True, exist_ok=True)
    env = clean_env()
    if shell:
        if isinstance(argv, str) and PRIVILEGE_ESCALATION.search(argv):
            return {
                "error": "PermissionApprovalRequired",
                "approval_required": True,
                "kind": "command",
                "command": argv,
                "cwd": str(cwd),
                "reason": "Privilege escalation (sudo/pkexec) requires explicit user approval."
            }
        argv, shell = sandboxed(argv, cwd), False
    if background:
        job_id = uuid.uuid4().hex[:10]
        log = HERE / "jobs" / f"{job_id}.log"
        log.parent.mkdir(exist_ok=True)
        with open(log, "w") as fh:
            proc = subprocess.Popen(argv, cwd=cwd, shell=shell, stdout=fh, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        with JOBS_LOCK:
            JOBS[job_id] = {"proc": proc, "log": log, "started": time.time(), "cmd": argv, "cwd": str(cwd)}
            _save_job(job_id, JOBS[job_id])
        return {"job_id": job_id, "status": "running", "cwd": str(cwd),
                "hint": "poll /jobs/get with this id"}
    try:
        proc = subprocess.Popen(argv, cwd=cwd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        stdout, stderr = proc.communicate(timeout=timeout)
        return {"exit_code": proc.returncode, "stdout": clip(stdout), "stderr": clip(stderr, 6000),
                "cwd": str(cwd)}
    except subprocess.TimeoutExpired as e:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = proc.communicate()
        return {"exit_code": None, "error": f"timed out after {timeout}s (use background=true for long tasks)",
                "stdout": clip(stdout), "stderr": clip(stderr, 6000)}


def h_shell(b):
    cmd = str(b.get("cmd") or "")
    if PRIVILEGE_ESCALATION.search(cmd):
        return {
            "error": "PermissionApprovalRequired",
            "approval_required": True,
            "kind": "command",
            "command": cmd,
            "cwd": str(b.get("cwd") or ""),
            "reason": "Privilege escalation (sudo/pkexec) requires explicit user approval."
        }
    return run(cmd, b.get("cwd"), int(b.get("timeout") or 300), as_bool(b.get("background")),
               shell=True)


def h_read(b):
    p = resolve(b["path"])
    if not p.exists() or not p.is_file():
        return {"error": f"FileNotFoundError: [Errno 2] No such file or directory: '{p}'"}
    if as_bool(b.get("raw")):
        if p.stat().st_size > 2_000_000:
            return {"error": "file too large to open (over 2 MB)"}
        content = p.read_text(errors="replace")
        return {"path": str(p), "content": content, "size": p.stat().st_size, "revision": revision(content)}
    lines = p.read_text(errors="replace").splitlines()
    off, lim = int(b.get("offset") or 0), int(b.get("limit") or 400)
    body = "\n".join(f"{i + 1}\t{l}" for i, l in enumerate(lines[off:off + lim], start=off))
    return {"path": str(p), "total_lines": len(lines), "content": clip(body)}


def h_write(b):
    p = writable(resolve(b["path"]))
    content = b.get("content", "")
    if not isinstance(content, str):
        raise ValueError("file content must be text")
    with FILES_LOCK:
        exists = p.exists()
        old = p.read_text() if exists else ""
        if b.get("create_only") and exists:
            return {"error": "file already exists", "conflict": True}
        if "expected_revision" in b and b["expected_revision"] != revision(old):
            return {"error": "file changed since it was opened; reload before saving", "conflict": True}
        if as_bool(b.get("append")):
            content = old + content
        atomic_write(p, content)
    return {"path": str(p), "bytes": p.stat().st_size, "revision": revision(content)}


def h_list(b):
    root = resolve(b.get("path"))
    depth = int(b.get("depth") or 2)
    skip = {"node_modules", ".git", ".venv", "__pycache__", "dist", ".next", "build"}
    out = []
    for dirpath, dirs, files in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        if len(rel.parts) >= depth:
            dirs[:] = []
        dirs[:] = sorted(d for d in dirs if d not in skip)
        out += [str(rel / d) + "/" for d in dirs] + [str(rel / f) for f in sorted(files)]
        if len(out) > 800:
            break
    return {"path": str(root), "exists": root.exists(), "entries": out[:800]}


def h_agy(b):
    argv = ["agy", "-p", b["prompt"], "--output-format", b.get("output_format", "text")]
    if b.get("mode"):
        argv += ["--mode", b["mode"]]
    else:
        argv += ["--mode", "auto"]
    if b.get("agent"):
        argv += ["--agent", b["agent"]]
    if b.get("model"):
        argv += ["--model", b["model"]]
    if b.get("effort"):
        argv += ["--effort", b["effort"]]
    if as_bool(b.get("sandbox"), default=True):
        argv.append("--sandbox")
    
    allow_skip = False
    try:
        import runtime_settings
        allow_skip = runtime_settings.get().get("agy_skip_permissions", False)
    except Exception:
        allow_skip = False

    if allow_skip and as_bool(b.get("accept_all"), default=False):
        argv.append("--dangerously-skip-permissions")
    if as_bool(b.get("continue")):
        argv.append("--continue")
    if as_bool(b.get("new_project")):
        argv.append("--new-project")

    try:
        import telemetry
        telemetry.log_agy_invocation(b.get("agent"), b.get("prompt"), argv, b.get("cwd"))
    except Exception:
        pass

    return run(argv, b.get("cwd"), int(b.get("timeout") or 1800), as_bool(b.get("background")))


def h_browser(b):
    args = b.get("args") or ""
    args = shlex.split(args) if isinstance(args, str) else [str(a) for a in args]
    for a in args:
        if a.lower().startswith("file:"):
            raise PermissionError("file: URLs are not allowed")
        if a.startswith(("/", "~", "..")):
            resolve(a)  # screenshots/uploads must stay inside the workspace
    return run(["agent-browser", *args], b.get("cwd"), int(b.get("timeout") or 120), False)


def iter_skills():
    seen = set()
    for root in SKILL_ROOTS:
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            if "node_modules" in skill_md.parts:
                continue
            d = skill_md.parent
            if d.name in seen:
                continue
            seen.add(d.name)
            yield d, skill_md


def frontmatter_desc(text):
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    return m.group(1).strip()[:300] if m else text.strip().splitlines()[0][:300]


def h_skills_list(_b):
    return {"skills": [{"name": d.name, "path": str(d), "description": frontmatter_desc(md.read_text(errors="replace"))}
                       for d, md in iter_skills()]}


def h_skills_read(b):
    name = b["name"]
    for d, md in iter_skills():
        if d.name == name:
            target = (d / b["file"]).resolve() if b.get("file") else md
            if target != md and d.resolve() not in target.parents:
                return {"error": "file must be inside the skill folder"}
            files = [str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()][:200]
            return {"skill": name, "file": str(target), "content": clip(target.read_text(errors="replace"), 40000),
                    "other_files": files}
    return {"error": f"skill '{name}' not found; call /skills/list"}


def h_fetch(b):
    if urlparse(str(b.get("url", ""))).scheme.lower() not in ("http", "https"):
        raise ValueError("web fetch only supports http and https URLs")
    req = urllib.request.Request(b["url"], headers={"User-Agent": "Mozilla/5.0 (pc-bridge research)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    title = re.search(r"(?is)<title>(.*?)</title>", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return {"url": b["url"], "title": html.unescape(title.group(1).strip()) if title else "",
            "text": text[: int(b.get("max_chars") or 15000)]}


def h_job(b):
    with JOBS_LOCK:
        job = JOBS.get(b["id"])
    if not job:
        archived = _archived_jobs().get(b["id"])
        if not archived:
            return {"error": "unknown job id"}
        log = HERE / "jobs" / f"{b['id']}.log"
        return {**archived, "status": "finished" if archived.get("exit_code") is not None else "interrupted",
                "output": _log_tail(log, b.get("tail")),
                "hint": "Saved output from a previous bridge process; resume unfinished work from the project checkpoint."}
    code = job["proc"].poll()
    if code is not None:
        _save_job(b["id"], job)
    return {"id": b["id"], "status": "running" if code is None else "finished", "exit_code": code,
            "elapsed_s": int(time.time() - job["started"]), "output": _log_tail(job["log"], b.get("tail")),
            "cwd": job.get("cwd", "")}


def _log_tail(path, tail):
    tail = max(1, min(1000000, int(tail or MAX_OUT)))
    with path.open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - tail))
        return stream.read().decode("utf-8", "replace")


def _save_job(job_id, job):
    atomic_write(HERE / "jobs" / f"{job_id}.json", json.dumps({
        "id": job_id, "cwd": job.get("cwd", ""), "started": job["started"],
        "cmd": " ".join(map(str, job["cmd"]))[-1000:], "exit_code": job["proc"].poll()}, ensure_ascii=False))


def _archived_jobs():
    out = {}
    for path in sorted((HERE / "jobs").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]:
        if not re.fullmatch(r"[a-f0-9]{10}", path.stem):
            continue
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or data.get("id") != path.stem:
                continue
            out[path.stem] = {**data, "running": False, "elapsed_s": 0,
                              "status": "finished" if data.get("exit_code") is not None else "interrupted"}
        except (OSError, ValueError):
            continue
    return out


TEMPLATE_DIR = AGENT_DIR / "templates" / "project"
INDEX_FILE = "INDEX.md"
INDEX_HEADER = ("# DevPilot projects\n\n"
                "| Project | Title | Status | Created | Goal |\n|---|---|---|---|---|\n")


def h_project_init(b):
    with PROJECT_LOCK:
        return _project_init(b)


def _project_init(b):
    """Create a project from the standard template (never overwrites) and register it in INDEX.md."""
    slug = str(b["slug"]).strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,48}", slug):
        return {"error": "slug must be 2-49 chars of a-z, 0-9 and '-' (e.g. 'todo-app')"}
    title = str(b.get("title") or slug.replace("-", " ").title()).strip()
    goal = str(b.get("goal") or "_tbd_").strip()
    today = time.strftime("%Y-%m-%d")
    root = resolve(slug)
    writable(root)
    if b.get("create_only") and root.exists():
        return {"error": "project folder already exists; choose another name"}
    if not TEMPLATE_DIR.is_dir():
        return {"error": "project template is unavailable"}
    root.mkdir(parents=True, exist_ok=True)
    created, kept = [], []
    for src in sorted(TEMPLATE_DIR.rglob("*")):
        if not src.is_file():
            continue
        dst = writable(resolve(root / src.relative_to(TEMPLATE_DIR)))
        if dst.exists():
            kept.append(str(dst.relative_to(root)))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text()
        for k, v in {"{{SLUG}}": slug, "{{TITLE}}": title, "{{GOAL}}": goal, "{{DATE}}": today}.items():
            text = text.replace(k, v)
        dst.write_text(text)
        created.append(str(dst.relative_to(root)))
    for d in ("src", "public", "tests"):
        (root / d).mkdir(exist_ok=True)
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, env=clean_env())
        subprocess.run(["git", "add", "-A"], cwd=root, env=clean_env())
        subprocess.run(["git", "-c", "user.name=DevPilot", "-c", "user.email=devpilot@localhost", "commit", "-qm",
                        "chore: project skeleton"], cwd=root, env=clean_env())
    index = WORKSPACE / INDEX_FILE
    rows = index.read_text() if index.exists() else INDEX_HEADER
    if f"| [{slug}](" not in rows:
        rows = rows.rstrip("\n") + f"\n| [{slug}]({slug}/PROJECT.md) | {title} | 🟡 intake | {today} | {goal[:80]} |\n"
        atomic_write(index, rows)
    return {"project": str(root), "created": created, "kept_existing": kept,
            "next": "fill PROJECT.md, then run research into docs/research/BRIEF.md"}


def h_project_list(_b):
    index = WORKSPACE / INDEX_FILE
    dirs = []
    if WORKSPACE.exists():
        for p in WORKSPACE.iterdir():
            if not p.is_dir() or p.name.startswith((".", "_")):
                continue
            if (p / "PROJECT.md").exists() or p.is_symlink():
                dirs.append(p.name)
    dirs = sorted(set(dirs))
    hidden = _hidden_projects()
    dirs = [d for d in dirs if d not in hidden]
    return {"workspace": str(WORKSPACE), "index": index.read_text() if index.exists() else "", "folders": dirs}


# ---------------------------------------------------------------------------- resume support
STATE_DIR = ".devpilot"
JOURNALED = {"/shell", "/fs/write", "/agy", "/project/init"}
AUTORESUME_FILE = HERE / "autoresume.json"
AUTORESUME_MAX, AUTORESUME_WINDOW = 3, 30 * 60


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def slug_of(body):
    """Which project a request touches, from its slug / path / cwd (None if outside a project)."""
    if body.get("slug"):
        slug = str(body["slug"]).strip().lower()
        if not SLUG_RE.fullmatch(slug):
            raise ValueError("invalid project slug")
        writable(resolve(slug))
        return slug
    for key in ("path", "cwd"):
        if body.get(key):
            try:
                rel = resolve(body[key]).relative_to(WORKSPACE)
            except (PermissionError, ValueError):
                continue
            if rel.parts and not rel.parts[0].startswith((".", "_")) and (WORKSPACE / rel.parts[0]).is_dir():
                return rel.parts[0]
    return None


def journal(slug, entry):
    root = writable(resolve(slug))
    if not slug or not root.is_dir():
        return
    d = writable(resolve(root / STATE_DIR))
    d.mkdir(exist_ok=True)
    with open(d / "journal.jsonl", "a") as f:
        f.write(json.dumps({"ts": now_iso(), **entry}, ensure_ascii=False) + "\n")


def journal_request(route, body, result):
    slug = slug_of(body)
    if not slug:
        return
    ok = "error" not in result and result.get("exit_code") in (0, None)
    entry = {"tool": route.strip("/").replace("/", "_"), "ok": ok}
    if route == "/shell":
        entry.update(cmd=str(body.get("cmd", ""))[:300], exit=result.get("exit_code"), job=result.get("job_id"))
    elif route == "/fs/write":
        entry.update(path=str(result.get("path", body.get("path", ""))), bytes=result.get("bytes"))
    elif route == "/agy":
        entry.update(prompt=str(body.get("prompt", ""))[:300], mode=body.get("mode"), exit=result.get("exit_code"),
                     job=result.get("job_id"))
    if "error" in result:
        entry["error"] = str(result["error"])[:300]
    journal(slug, entry)


def read_state(slug):
    f = writable(resolve(WORKSPACE / slug / STATE_DIR / "STATE.json"))
    try:
        data = json.loads(f.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def set_index_status(slug, status):
    index = WORKSPACE / INDEX_FILE
    if not index.exists():
        return
    lines = index.read_text().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith(f"| [{slug}]("):
            cells = line.rstrip("\n").split("|")
            if len(cells) > 4:
                cells[3] = f" {status} "
                lines[i] = "|".join(cells) + "\n"
    atomic_write(index, "".join(lines))


def h_project_checkpoint(b):
    with PROJECT_LOCK:
        return _project_checkpoint(b)


def _project_checkpoint(b):
    """Save where a project stands so any later run can resume exactly there."""
    slug = slug_of(b)
    if not slug or not (WORKSPACE / slug).is_dir():
        return {"error": "unknown project; pass slug of an existing project"}
    state = read_state(slug)
    update = {k: str(b[k]).strip() for k in ("phase", "status", "milestone", "task", "next_action", "notes", "agent")
              if str(b.get(k) or "").strip()}
    history = state.get("history", [])[-19:] + [{"ts": now_iso(), **update}]
    state.update(update, slug=slug, updated=now_iso(), history=history)
    d = writable(resolve(WORKSPACE / slug / STATE_DIR))
    d.mkdir(exist_ok=True)
    atomic_write(d / "STATE.json", json.dumps(state, indent=2, ensure_ascii=False))
    journal(slug, {"tool": "checkpoint", **update})
    if update.get("status"):
        set_index_status(slug, update["status"])
    return {"saved": True, "state": {k: v for k, v in state.items() if k != "history"}}


def last_active_project():
    best, best_t = None, 0
    for d in WORKSPACE.iterdir():
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        for f in (d / STATE_DIR / "journal.jsonl", d / STATE_DIR / "STATE.json", d / "PROJECT.md"):
            if f.exists() and f.stat().st_mtime > best_t:
                best, best_t = d.name, f.stat().st_mtime
    return best


def section(text, start, stop_prefix="## "):
    out, on = [], False
    for line in text.splitlines():
        if line.startswith(start):
            on = True
        elif on and line.startswith(stop_prefix):
            break
        if on:
            out.append(line)
    return "\n".join(out)


def h_project_resume(b):
    """Everything a fresh run needs to continue a project where the last one stopped."""
    slug = slug_of(b) or last_active_project()
    if not slug or not (WORKSPACE / slug).is_dir():
        return {"error": "no project to resume; call List Projects"}
    root = writable(resolve(slug))
    state = read_state(slug)
    project_path = resolve(root / "PROJECT.md")
    plan_path = resolve(root / "docs/plan/PLAN.md")
    project = project_path.read_text() if project_path.exists() else ""
    plan = plan_path.read_text() if plan_path.exists() else ""
    tasks = parse_tasks(plan)
    lines = plan.splitlines()
    open_tasks = [lines[t["line"] - 1] for t in tasks if not t["done"]]
    jfile = resolve(root / STATE_DIR / "journal.jsonl")
    recent = jfile.read_text().splitlines()[-25:] if jfile.exists() else []
    git = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, env=clean_env()).stdout
    docs = {}
    for rel in ("docs/research/BRIEF.md", "docs/references/REFERENCES.md", "docs/design/DESIGN.md",
                "docs/plan/PLAN.md", "docs/qa/REPORT.md"):
        f = resolve(root / rel)
        if f.exists():
            m = re.search(r"Status:\s*([^·_\n]+)", f.read_text())
            docs[rel] = m.group(1).strip() if m else "present"
    with JOBS_LOCK:
        all_jobs = _archived_jobs()
        for k, v in JOBS.items():
            code = v["proc"].poll()
            all_jobs[k] = {"id": k, "running": code is None, "exit_code": code,
                           "status": "running" if code is None else "finished", "started": v.get("started", 0),
                           "cmd": str(v["cmd"])[-160:], "cwd": v.get("cwd", "")}
        project_jobs = sorted((j for j in all_jobs.values() if j.get("cwd") and Path(j["cwd"]).is_relative_to(root)),
                              key=lambda j: j.get("started", 0))
        # Retain every running job, even if many newer completed jobs exist.
        jobs = [j for j in project_jobs[:-10] if j.get("running")] + project_jobs[-10:]
    recent_entries = []
    for line in recent:
        try:
            entry = json.loads(line)
            if isinstance(entry, dict):
                recent_entries.append(entry)
        except ValueError:
            continue  # a crash can leave a partial journal tail
    uncommitted = git("status", "--short").strip().splitlines()[:30]
    return {
        "project": slug, "path": str(root),
        "state": {k: v for k, v in state.items() if k != "history"},
        "recent_checkpoints": state.get("history", [])[-5:] if isinstance(state.get("history"), list) else [],
        "project_status": section(project, "| Field") + "\n\n" + section(project, "## Phase checklist"),
        "plan_progress": f"{len(tasks) - len(open_tasks)}/{len(tasks)} tasks done",
        "next_open_tasks": open_tasks[:5],
        "docs_status": docs,
        "recent_journal": recent_entries,
        "git_log": git("log", "--oneline", "-10").strip().splitlines(),
        "uncommitted": uncommitted,
        "background_jobs": jobs,
        "continuation": continuation(state, tasks, jobs, uncommitted, revision(plan)),
        "how_to_continue": "Follow continuation.action after reading current files and authorization. "
                           "Reconcile stale checkpoints; do not redo finished tasks or duplicate running jobs.",
    }


def h_autoresume_attempt(b):
    with PROJECT_LOCK:
        return _autoresume_attempt(b)


def _autoresume_attempt(b):
    """Rate-limits automatic resumes: at most AUTORESUME_MAX within AUTORESUME_WINDOW seconds."""
    try:
        data = json.loads(AUTORESUME_FILE.read_text())
    except (OSError, ValueError):
        data = {"attempts": []}
    cutoff = time.time() - AUTORESUME_WINDOW
    attempts = [a for a in data.get("attempts", []) if isinstance(a, dict) and isinstance(a.get("t"), (int, float)) and a["t"] > cutoff]
    allow = len(attempts) < AUTORESUME_MAX
    slug = last_active_project()
    if allow:
        attempts.append({"t": time.time(), "error": str(b.get("error", ""))[:300], "slug": slug})
        if slug:
            journal(slug, {"tool": "autoresume", "error": str(b.get("error", ""))[:300],
                           "attempt": len(attempts)})
    atomic_write(AUTORESUME_FILE, json.dumps({"attempts": attempts}))
    return {"allow": allow, "attempts_in_window": len(attempts), "max": AUTORESUME_MAX, "project": slug}


def h_jobs_list(_b):
    with JOBS_LOCK:
        jobs = _archived_jobs()
        for k, v in JOBS.items():
            jobs[k] = {"id": k, "running": v["proc"].poll() is None, "exit_code": v["proc"].poll(), "started": v["started"],
                          "elapsed_s": int(time.time() - v["started"]), "cmd": " ".join(map(str, v["cmd"]))[-200:],
                          "cwd": v.get("cwd", "")}
            if not jobs[k]["running"]:
                _save_job(k, v)
        return {"jobs": sorted(jobs.values(), key=lambda j: j.get("started", 0))[-100:]}


def h_jobs_stop(b):
    import signal
    with JOBS_LOCK:
        job = JOBS.get(b["id"])
    if not job:
        return {"error": "unknown job id"}
    if job["proc"].poll() is None:
        try:
            os.killpg(job["proc"].pid, signal.SIGTERM)
            job["proc"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(job["proc"].pid, signal.SIGKILL)
            job["proc"].wait(timeout=5)
        except ProcessLookupError:
            pass
    _save_job(b["id"], job)
    return {"id": b["id"], "stopped": True, "exit_code": job["proc"].poll()}


def h_chat_completions(b):
    messages = b.get("messages", [])
    prompt = ""
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, list):
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        prompt += f"{m.get('role', 'user').upper()}: {c}\n\n"
    res = h_agy({"prompt": prompt.strip() or "Hello", "mode": "auto", "cwd": str(WORKSPACE)})
    text = res.get("stdout") or res.get("output") or "Done."
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": b.get("model", "agy/gemini-3.8-flash"),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100}
    }


def h_project_folders(b):
    """Folder picker: the sub-folders of a directory under the user's home."""
    home = HOME.resolve()
    p = Path(os.path.expanduser(str(b.get("path") or home))).resolve()
    if p != home and home not in p.parents:
        raise PermissionError("Choose a folder inside your home directory.")
    dirs = sorted((c for c in p.iterdir() if c.is_dir() and not c.name.startswith(".")), key=lambda c: c.name.lower())
    return {"path": str(p), "parent": str(p.parent) if p != home else "", "workspace": str(WORKSPACE),
            "dirs": [{"name": c.name, "path": str(c)} for c in dirs[:500]]}


def _init_project_spec(target, slug):
    spec_file = target / "PROJECT.md"
    if not spec_file.exists():
        today = time.strftime("%Y-%m-%d")
        title = target.name.replace("-", " ").replace("_", " ").title()
        content = f"""# {title}

**Slug**: `{slug}`
**Created**: {today}
**Status**: 🟢 active
**Goal**: Project linked from {target.name}

## Architecture & Standards
- Simplicity first, surgical changes, goal-driven verification.
- Automated tests for all features and bug fixes.
"""
        try:
            spec_file.write_text(content, encoding="utf-8")
        except OSError:
            pass
    devpilot_dir = target / STATE_DIR
    try:
        devpilot_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def h_project_link(b):
    """Add a folder as a project. Folders outside the workspace become agent-writable, so only the user's own click reaches this."""
    home = HOME.resolve()
    target = Path(os.path.expanduser(str(b.get("path") or ""))).resolve()
    if not target.is_dir() or home not in target.parents:
        raise ValueError("Choose a folder inside your home directory.")
    if any(part.startswith(".") for part in target.relative_to(home).parts):
        raise ValueError("Hidden folders cannot be projects.")
    if target == WORKSPACE or target in WORKSPACE.parents:
        raise ValueError("That folder contains the whole workspace. Choose a project folder inside it.")
    if any(target == d or d in target.parents for d in PROTECTED):
        raise ValueError("That folder is protected.")
    if target.parent == WORKSPACE:
        hidden = _hidden_projects()
        if target.name in hidden:
            hidden.discard(target.name)
            _write_workspace_json(HIDDEN_FILE, sorted(hidden))
        _init_project_spec(target, target.name)
        return {"ok": True, "slug": target.name, "linked": False}
    for child in WORKSPACE.iterdir():
        if child.is_symlink() and child.resolve() == target:
            _init_project_spec(target, child.name)
            return {"ok": True, "slug": child.name, "linked": True}
    base = re.sub(r"[^a-z0-9-]+", "-", target.name.lower()).strip("-")[:40]
    base = base if len(base) >= 2 else "project"
    slug, n = base, 2
    while (WORKSPACE / slug).exists() or (WORKSPACE / slug).is_symlink():
        slug, n = f"{base}-{n}", n + 1
    if WORKSPACE not in target.parents:
        roots = _linked_roots()
        if target not in roots:
            _write_workspace_json(LINKS_FILE, [str(r) for r in roots] + [str(target)])
    (WORKSPACE / slug).symlink_to(target, target_is_directory=True)
    _init_project_spec(target, slug)
    return {"ok": True, "slug": slug, "linked": True}


def _project_entry(slug):
    name = str(slug or "")
    if not name or name != Path(name).name or name.startswith((".", "_")):
        raise ValueError("Choose a project.")
    p = WORKSPACE / name
    if not (p.is_dir() or p.is_symlink()):
        raise ValueError("That project no longer exists.")
    return p


def h_project_remove(b):
    """Take a project off the list. Never deletes project files: a link is unlinked, a folder is only hidden."""
    p = _project_entry(b.get("slug"))
    if p.is_symlink():
        target = p.resolve()
        p.unlink()
        still_linked = any(c.is_symlink() and c.resolve() == target for c in WORKSPACE.iterdir())
        roots = _linked_roots()
        if target in roots and not still_linked:
            _write_workspace_json(LINKS_FILE, [str(r) for r in roots if r != target])
        return {"ok": True, "unlinked": True}
    _write_workspace_json(HIDDEN_FILE, sorted(_hidden_projects() | {p.name}))
    return {"ok": True, "unlinked": False}


def h_project_rename(b):
    p, new = _project_entry(b.get("slug")), str(b.get("name") or "")
    if not SLUG_RE.fullmatch(new):
        raise ValueError("Use 2 to 49 lowercase letters, numbers and dashes.")
    dst = WORKSPACE / new
    if dst.exists() or dst.is_symlink():
        raise ValueError(f"A project named {new} already exists.")
    p.rename(dst)
    index = WORKSPACE / INDEX_FILE
    if index.exists():
        index.write_text(index.read_text().replace(f"[{p.name}]({p.name}/", f"[{new}]({new}/"))
    return {"ok": True, "slug": new}


def h_cli_agent(b):
    """Generic CLIAgentProvider adapter for invoking claude -p, aider, or agy inside the sandbox."""
    cli = str(b.get("cli") or "agy").lower()
    prompt = str(b.get("prompt") or "")
    cwd = b.get("cwd")
    if cli == "claude":
        argv = ["claude", "-p", prompt]
    elif cli == "aider":
        argv = ["aider", "--message", prompt, "--yes"]
    else:
        argv = ["agy", "-p", prompt, "--output-format", b.get("output_format", "text")]
    return run(argv, cwd, int(b.get("timeout") or 1800), as_bool(b.get("background")))


ROUTES = {
    "/shell": h_shell, "/fs/read": h_read, "/fs/write": h_write, "/fs/list": h_list,
    "/agy": h_agy, "/agent/cli": h_cli_agent, "/browser": h_browser, "/skills/list": h_skills_list,
    "/skills/read": h_skills_read, "/web/fetch": h_fetch, "/jobs/get": h_job, "/jobs/list": h_jobs_list, "/jobs/stop": h_jobs_stop,
    "/project/init": h_project_init, "/project/list": h_project_list,
    "/project/folders": h_project_folders, "/project/link": h_project_link,
    "/project/remove": h_project_remove, "/project/rename": h_project_rename,
    "/project/checkpoint": h_project_checkpoint, "/project/resume": h_project_resume,
    "/autoresume/attempt": h_autoresume_attempt,
    "/v1/chat/completions": h_chat_completions,
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "workspace": str(WORKSPACE)})
        if self.path == "/v1/models":
            return self._send(200, {"object": "list", "data": [{"id": "agy/gemini-3.8-flash", "object": "model", "owned_by": "antigravity"}]})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not TOKEN or self.headers.get("X-Bridge-Token") != TOKEN:
            return self._send(401, {"error": "bad token"})
        handler = ROUTES.get(self.path.rstrip("/"))
        if not handler:
            return self._send(404, {"error": f"unknown endpoint; have {sorted(ROUTES)}"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= 4000000:
                return self._send(413, {"error": "request too large"})
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                return self._send(400, {"error": "body must be an object"})
            result = handler(body)
            if self.path.rstrip("/") in JOURNALED:
                try:
                    journal_request(self.path.rstrip("/"), body, result)
                except Exception as e:  # journaling must never break the tool call
                    print(f"[pc-bridge] journal error: {e}", flush=True)
            self._send(200, result)
        except KeyError as e:
            self._send(400, {"error": f"missing field {e}"})
        except Exception as e:  # report errors back to the agent so it can recover
            self._send(200, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        print(f"[pc-bridge] {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(f"No token: create {TOKEN_FILE} or set PC_BRIDGE_TOKEN")
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    print(f"[pc-bridge] listening on http://{HOST}:{PORT} workspace={WORKSPACE}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
