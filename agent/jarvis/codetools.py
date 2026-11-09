"""Coding utilities for the Jarvis Code workspace. Everything runs through the PC bridge, so it stays inside
~/Projects/devpilot and every shell command runs in the bubblewrap sandbox."""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time

from pathlib import Path

WORKSPACE = os.environ.get("KRYZEN_WORKSPACE") or (str(Path.home() / "Space" / "Projects") if (Path.home() / "Space" / "Projects").exists() else str(Path.home() / "Projects" / "devpilot"))
SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,79}$")


def _root(slug):
    if not SLUG.match(slug or ""):
        raise ValueError("pick a project first")
    return f"{WORKSPACE}/{slug}"


def _rel(rel):
    rel = str(rel or "").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("invalid path")
    return rel


def tree(bridge, slug):
    d = bridge("/fs/list", {"path": _root(slug), "depth": 8})
    return {"slug": slug, "entries": d.get("entries", []), "error": d.get("error")}


def read(bridge, slug, rel):
    return bridge("/fs/read", {"path": f"{_root(slug)}/{_rel(rel)}", "raw": True})


def save(bridge, slug, rel, content, revision=None, create_only=False):
    args = {"path": f"{_root(slug)}/{_rel(rel)}", "content": content}
    if revision is not None:
        args["expected_revision"] = revision
    if create_only:
        args["create_only"] = True
    return bridge("/fs/write", args)


def run(bridge, slug, cmd, background=False, timeout=600):
    if not str(cmd).strip():
        raise ValueError("empty command")
    return bridge("/shell", {"cmd": cmd, "cwd": _root(slug), "background": bool(background), "timeout": timeout})


def scripts(bridge, slug):
    """package.json scripts plus the right install command for the project's package manager."""
    root = _root(slug)
    pkg = bridge("/fs/read", {"path": f"{root}/package.json", "raw": True})
    if "error" in pkg:
        return {"scripts": [], "install": None, "manager": None}
    try:
        data = json.loads(pkg["content"])
        if not isinstance(data, dict) or not isinstance(data.get("scripts", {}), dict):
            raise ValueError("scripts must be an object")
    except ValueError:
        return {"scripts": [], "install": None, "manager": None, "error": "package.json is not valid JSON"}
    files = set(bridge("/fs/list", {"path": root, "depth": 1}).get("entries", []))
    manager = ("pnpm" if "pnpm-lock.yaml" in files else "yarn" if "yarn.lock" in files
               else "bun" if {"bun.lockb", "bun.lock"} & files else "npm")
    run_prefix = {"npm": "npm run", "pnpm": "pnpm run", "yarn": "yarn", "bun": "bun run"}[manager]
    return {"manager": manager, "install": f"{manager} install",
            "scripts": [{"name": k, "cmd": v, "run": f"{run_prefix} {shlex.quote(k)}"}
                        for k, v in (data.get("scripts") or {}).items() if isinstance(v, str)]}


def search(bridge, slug, query, regex=False, case=False, glob=""):
    if not str(query).strip():
        raise ValueError("type something to search for")
    args = ["rg", "-n", "--no-heading", "--color", "never", "--max-count", "40", "--max-columns", "220",
            "--max-columns-preview", "-g", "!node_modules", "-g", "!dist", "-g", "!.next", "-g", "!*.lock",
            "-g", "!package-lock.json"]
    args += [] if regex else ["-F"]
    args += ["-s"] if case else ["-i"]
    if glob:
        args += ["-g", glob]
    args += ["--", query, "."]
    r = run(bridge, slug, " ".join(shlex.quote(a) for a in args), timeout=60)
    if r.get("error") or r.get("exit_code") not in (0, 1):
        return {"hits": [], "error": r.get("error") or r.get("stderr") or "search failed"}
    hits = []
    for line in (r.get("stdout") or "").splitlines():
        m = re.match(r"^\./?(.+?):(\d+):(.*)$", line)
        if m:
            hits.append({"file": m.group(1), "line": int(m.group(2)), "text": m.group(3)})
    return {"hits": hits[:400], "truncated": len(hits) >= 400, "error": r.get("error")}


def git(bridge, slug, action, message="", file=""):
    q = shlex.quote
    cmds = {
        "status": "git status --short --branch",
        "diff": f"git --no-pager diff --stat; echo; git --no-pager diff -- {q(_rel(file))}" if file
                else "git --no-pager diff --stat; echo; git --no-pager diff | head -1500",
        "log": "git --no-pager log --graph --date=short --pretty='%h %ad %s' -40",
        "commit": None,
    }
    if action not in cmds:
        raise ValueError("unknown git action")
    if action == "commit":
        if not message.strip():
            raise ValueError("write a commit message")
        m = q(message.strip())
        # use the user's git identity when it exists, otherwise commit as DevPilot
        cmd = ("git add -A && "
               "if git var GIT_AUTHOR_IDENT >/dev/null 2>&1 && git var GIT_COMMITTER_IDENT >/dev/null 2>&1; then "
               f"git commit -m {m}; else git -c user.name=DevPilot -c user.email=devpilot@localhost commit -m {m}; fi")
    else:
        cmd = cmds[action]
    return run(bridge, slug, cmd, timeout=60)


def jobs(bridge):
    return bridge("/jobs/list", {})


def job(bridge, job_id, tail=20000):
    return bridge("/jobs/get", {"id": job_id, "tail": tail})


def agy(bridge, slug, prompt, mode="auto", model="", effort="high", background=True, timeout=1800):
    if not str(prompt).strip():
        raise ValueError("prompt cannot be empty")
    args = {
        "prompt": prompt.strip(),
        "cwd": _root(slug),
        "mode": mode or "auto",
        "accept_all": True,
        "background": bool(background),
        "timeout": timeout,
    }
    if model:
        args["model"] = model
    if effort:
        args["effort"] = effort
    return bridge("/agy", args)


def stop(bridge, job_id):
    return bridge("/jobs/stop", {"id": job_id})


def vibe_config_path(slug):
    return Path(_root(slug)) / ".devpilot" / "vibe-config.json"


def vibe_config_get(slug):
    p = vibe_config_path(slug)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {
        "aesthetic": "Swiss Grid",
        "density": 3,
        "motion": 3,
        "stack": "Vanilla Zero-Dep"
    }


def vibe_config_save(slug, config):
    p = vibe_config_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = vibe_config_get(slug)
    cfg.update(config or {})
    p.write_text(json.dumps(cfg, indent=2))
    return cfg


def vibe_checkpoint(bridge, slug, label="vibe"):
    import time
    ts = int(time.time())
    tag = f"vibe-checkpoint-{ts}"
    safe_label = shlex.quote(str(label or "checkpoint").replace('"', ''))
    root = _root(slug)

    # Commit with tag
    cmd = (
        f"git add -A && "
        f"if git var GIT_AUTHOR_IDENT >/dev/null 2>&1; then "
        f"git commit -m \"{tag}: {safe_label}\" --allow-empty; "
        f"else git -c user.name=DevPilot -c user.email=devpilot@localhost commit -m \"{tag}: {safe_label}\" --allow-empty; fi && "
        f"git tag -f {tag} && git rev-parse HEAD"
    )
    r = run(bridge, slug, cmd, timeout=30)
    commit_hash = (r.get("stdout") or "").strip().splitlines()[-1] if r.get("stdout") else tag

    # Save metadata
    meta_dir = Path(root) / ".devpilot" / "vibe-checkpoints"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "tag": tag,
        "hash": commit_hash,
        "timestamp": ts,
        "label": label or "Vibe checkpoint"
    }
    (meta_dir / f"{tag}.json").write_text(json.dumps(meta, indent=2))
    return {"ok": True, **meta}


def vibe_rollback(bridge, slug, checkpoint_id):
    if not checkpoint_id or not re.match(r"^[a-zA-Z0-9_\-\.]+$", str(checkpoint_id)):
        raise ValueError("invalid checkpoint id")
    cmd = f"git reset --hard {shlex.quote(str(checkpoint_id))}"
    r = run(bridge, slug, cmd, timeout=30)
    if r.get("exit_code") != 0:
        raise RuntimeError(f"rollback failed: {r.get('stderr') or r.get('error')}")
    return {"ok": True, "restored": checkpoint_id}


def vibe_checkpoints(bridge, slug):
    root = _root(slug)
    meta_dir = Path(root) / ".devpilot" / "vibe-checkpoints"
    checkpoints = []
    if meta_dir.exists():
        for f in meta_dir.glob("vibe-checkpoint-*.json"):
            try:
                checkpoints.append(json.loads(f.read_text()))
            except Exception:
                pass
    if not checkpoints:
        # Fallback to git tags
        r = run(bridge, slug, "git tag -l 'vibe-checkpoint-*' --sort=-creatordate", timeout=15)
        if r.get("stdout"):
            for t in r.get("stdout").splitlines()[:20]:
                t = t.strip()
                if t:
                    checkpoints.append({"tag": t, "hash": t, "timestamp": 0, "label": t})
    checkpoints.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return {"ok": True, "checkpoints": checkpoints}


# ---------------------------------------------------------------------------- Isolated Agent Box & Conflict-Free Merge
def _file_hash(p):
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _box_dir(slug, box_id):
    root = Path(_root(slug))
    clean_box = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(box_id or "default"))
    return root / ".devpilot" / "isolated" / clean_box


def create_isolated_box(slug, box_id="default"):
    bdir = _box_dir(slug, box_id)
    bdir.mkdir(parents=True, exist_ok=True)
    meta_path = bdir / ".box-meta.json"
    if not meta_path.exists():
        meta = {
            "box_id": box_id,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "baselines": {}
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, "box_id": box_id, "path": str(bdir)}


def write_isolated_box(slug, box_id, rel_path, content):
    clean_rel = _rel(rel_path)
    bdir = _box_dir(slug, box_id)
    if not bdir.exists():
        create_isolated_box(slug, box_id)
    meta_path = bdir / ".box-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"baselines": {}}

    root = Path(_root(slug))
    orig_file = root / clean_rel
    if clean_rel not in meta.get("baselines", {}):
        meta.setdefault("baselines", {})[clean_rel] = _file_hash(orig_file)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    target = bdir / clean_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(target), "size": len(content)}


def read_isolated_box(slug, box_id, rel_path):
    clean_rel = _rel(rel_path)
    bdir = _box_dir(slug, box_id)
    target = bdir / clean_rel
    if target.exists() and target.is_file():
        return {"ok": True, "source": "isolated", "content": target.read_text(encoding="utf-8", errors="replace")}
    root = Path(_root(slug))
    orig = root / clean_rel
    if orig.exists() and orig.is_file():
        return {"ok": True, "source": "project", "content": orig.read_text(encoding="utf-8", errors="replace")}
    return {"ok": False, "error": f"File not found: {rel_path}"}


def list_isolated_box(slug, box_id):
    bdir = _box_dir(slug, box_id)
    if not bdir.exists():
        return {"ok": False, "error": "Box not found", "files": []}
    files = []
    for p in bdir.rglob("*"):
        if p.is_file() and p.name != ".box-meta.json":
            files.append(str(p.relative_to(bdir)))
    return {"ok": True, "box_id": box_id, "files": sorted(files)}


def merge_isolated_box(slug, box_id, discard_on_success=True):
    bdir = _box_dir(slug, box_id)
    if not bdir.exists():
        return {"ok": False, "error": "Box not found"}
    meta_path = bdir / ".box-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"baselines": {}}
    baselines = meta.get("baselines", {})
    root = Path(_root(slug))

    conflicts = []
    staged_files = []
    for p in bdir.rglob("*"):
        if p.is_file() and p.name != ".box-meta.json":
            rel = str(p.relative_to(bdir))
            staged_files.append((rel, p))
            base_hash = baselines.get(rel)
            curr_orig = root / rel
            curr_hash = _file_hash(curr_orig)
            if curr_hash != base_hash:
                conflicts.append(rel)

    if conflicts:
        return {
            "ok": False,
            "conflict": True,
            "error": f"Cannot merge: {len(conflicts)} conflicting file(s) modified concurrently",
            "conflicts": conflicts
        }

    applied = []
    for rel, src in staged_files:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp_" + str(int(time.time())))
        tmp.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        tmp.replace(dest)
        applied.append(rel)

    if discard_on_success:
        shutil.rmtree(bdir, ignore_errors=True)

    return {"ok": True, "merged_files": applied}


def discard_isolated_box(slug, box_id):
    bdir = _box_dir(slug, box_id)
    if bdir.exists():
        shutil.rmtree(bdir, ignore_errors=True)
    return {"ok": True, "discarded": box_id}


# ---------------------------------------------------------------------------- Branch Per Change & Merge Approval Workflow
def _git_run(slug, args, check=False):
    root = _root(slug)
    res = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(res.stderr or f"git command failed: {args}")
    return res


def detect_default_branch(slug):
    # 1. Try remote origin HEAD
    r = _git_run(slug, ["symbolic-ref", "refs/remotes/origin/HEAD"])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("/")[-1]
    # 2. Check local main
    r_main = _git_run(slug, ["rev-parse", "--verify", "refs/heads/main"])
    if r_main.returncode == 0:
        return "main"
    # 3. Check local master
    r_master = _git_run(slug, ["rev-parse", "--verify", "refs/heads/master"])
    if r_master.returncode == 0:
        return "master"
    # 4. Check git default branch config
    r_cfg = _git_run(slug, ["config", "init.defaultBranch"])
    if r_cfg.returncode == 0 and r_cfg.stdout.strip():
        return r_cfg.stdout.strip()
    return "main"


def create_change_branch(slug, branch_name=None):
    default_branch = detect_default_branch(slug)
    if not branch_name:
        ts = int(time.time())
        branch_name = f"agent/{slug}-{ts}"
    branch_name = re.sub(r"[^a-zA-Z0-9_\-\./]", "-", str(branch_name)).strip("-")

    # Checkout new branch
    r = _git_run(slug, ["checkout", "-b", branch_name])
    if r.returncode != 0:
        r = _git_run(slug, ["checkout", branch_name])
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr or "failed to checkout branch"}

    return {"ok": True, "branch": branch_name, "default_branch": default_branch}


def commit_change_branch(slug, message="agent change"):
    _git_run(slug, ["add", "-A"])
    m = message.strip() or "agent change"
    r = _git_run(slug, ["commit", "-m", m])
    if r.returncode != 0:
        if "nothing to commit" in (r.stdout + r.stderr):
            return {"ok": True, "committed": False, "message": "nothing to commit"}
        r = _git_run(slug, ["-c", "user.name=DevPilot", "-c", "user.email=devpilot@localhost", "commit", "-m", m])
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr or "commit failed"}
    return {"ok": True, "committed": True, "message": m}


def get_branch_change_status(slug):
    default_branch = detect_default_branch(slug)
    r_head = _git_run(slug, ["rev-parse", "--abbrev-ref", "HEAD"])
    curr = r_head.stdout.strip() if r_head.returncode == 0 else ""

    if curr and curr != default_branch:
        r_log = _git_run(slug, ["log", f"{default_branch}..{curr}", "--oneline"])
        commits = [line.strip() for line in r_log.stdout.splitlines() if line.strip()]
        return {
            "ok": True,
            "pending_approval": True,
            "current_branch": curr,
            "default_branch": default_branch,
            "commits": commits,
            "commit_count": len(commits)
        }
    return {
        "ok": True,
        "pending_approval": False,
        "current_branch": curr,
        "default_branch": default_branch,
        "commits": [],
        "commit_count": 0
    }


def merge_change_branch(slug, branch_name=None, approve=True):
    if not approve:
        return {"ok": False, "error": "User approval is required to merge into primary branch."}

    default_branch = detect_default_branch(slug)
    if not branch_name:
        status = get_branch_change_status(slug)
        branch_name = status.get("current_branch")
        if not branch_name or branch_name == default_branch:
            return {"ok": False, "error": f"Already on default branch '{default_branch}', nothing to merge."}

    r_co = _git_run(slug, ["checkout", default_branch])
    if r_co.returncode != 0:
        return {"ok": False, "error": f"Failed to switch to {default_branch}: {r_co.stderr}"}

    r_merge = _git_run(slug, ["merge", "--no-ff", branch_name, "-m", f"Merge agent branch '{branch_name}' into {default_branch}"])
    if r_merge.returncode != 0:
        _git_run(slug, ["merge", "--abort"])
        return {
            "ok": False,
            "conflict": True,
            "error": f"Merge conflict encountered: {r_merge.stderr}",
            "default_branch": default_branch
        }

    return {
        "ok": True,
        "merged": True,
        "branch": branch_name,
        "default_branch": default_branch
    }



