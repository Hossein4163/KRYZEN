"""Coding utilities for the Jarvis Code workspace. Everything runs through the PC bridge, so it stays inside
~/Projects/devpilot and every shell command runs in the bubblewrap sandbox."""
import json
import os
import re
import shlex

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

