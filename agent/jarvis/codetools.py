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
import threading
import uuid
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workflow"))
from projectdata import atomic_write

WORKSPACE = os.environ.get("KRYZEN_WORKSPACE") or os.environ.get("PC_BRIDGE_WORKSPACE") or (str(Path.home() / "Space" / "Projects") if (Path.home() / "Space" / "Projects").exists() else str(Path.home() / "Projects" / "devpilot"))
SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-\.]{0,79}$")


def _root(slug):
    if not SLUG.fullmatch(slug or ""):
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
    ts = int(time.time())
    tag = f"vibe-checkpoint-{ts}-{uuid.uuid4().hex[:8]}"
    message = shlex.quote(f"{tag}: {str(label)[:120]}")
    root = Path(_root(slug)).resolve()
    cmd = (
        "git add -A -- . ':(exclude).devpilot' && "
        f"git -c core.hooksPath=/dev/null -c user.name=DevPilot -c user.email=devpilot@localhost "
        f"commit -m {message} --allow-empty -- . ':(exclude).devpilot' && "
        f"git tag {tag} && git rev-parse HEAD"
    )
    result = run(bridge, slug, cmd, timeout=30)
    if result.get("exit_code") != 0 or not result.get("stdout", "").strip():
        return {"ok": False, "error": result.get("error") or result.get("stderr") or "Checkpoint failed"}
    commit_hash = result["stdout"].strip().splitlines()[-1]
    meta_dir = _within(root, ".devpilot/vibe-checkpoints")
    meta = {
        "tag": tag,
        "hash": commit_hash,
        "timestamp": ts,
        "label": label or "Vibe checkpoint"
    }
    atomic_write(meta_dir / f"{tag}.json", json.dumps(meta, indent=2))
    return {"ok": True, **meta}


def vibe_rollback(bridge, slug, checkpoint_id):
    if not re.fullmatch(r"vibe-checkpoint-[A-Za-z0-9-]+", str(checkpoint_id)):
        raise ValueError("invalid checkpoint id")
    branch = f"restore/{uuid.uuid4().hex[:12]}"
    ref = f"refs/tags/{checkpoint_id}"
    cmd = f"""status=$(git status --porcelain -- . ':(exclude).devpilot') &&
        if test -n "$status"; then echo 'Commit or stash existing changes first.' >&2; exit 1; fi &&
        git -c core.hooksPath=/dev/null switch -c {branch} {ref}"""
    result = run(bridge, slug, cmd, timeout=30)
    if result.get("exit_code") != 0:
        raise RuntimeError(result.get("error") or result.get("stderr") or "Checkpoint restoration failed")
    return {"ok": True, "restored": checkpoint_id, "branch": branch}


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


BOX_LOCK = threading.RLock()
BOX_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")


def _within(root, rel):
    path = root / rel
    if not path.resolve().is_relative_to(root) or any(
        part.is_symlink() for part in (path, *path.parents) if part != root and root in part.parents
    ):
        raise ValueError("isolated files cannot use symlinks or leave the project")
    return path


def _box_dir(slug, box_id):
    if not isinstance(box_id, str) or not BOX_ID.fullmatch(box_id):
        raise ValueError("invalid isolated box ID")
    root = Path(_root(slug)).resolve()
    if not root.is_dir():
        raise ValueError("project does not exist")
    return _within(root, f".devpilot/isolated/{box_id}")


def _box_rel(rel):
    rel = _rel(rel)
    parts = Path(rel).parts
    if not parts or ".box-meta.json" in parts or parts[0] == ".git" or parts[:2] == (".devpilot", "isolated"):
        raise ValueError("invalid isolated file path")
    return rel


def _box_metadata(box):
    path = _within(box, ".box-meta.json")
    return json.loads(path.read_text()) if path.is_file() else {"baselines": {}}


def create_isolated_box(slug, box_id="default"):
    with BOX_LOCK:
        box = _box_dir(slug, box_id)
        box.mkdir(parents=True, exist_ok=True)
        path = _within(box, ".box-meta.json")
        if not path.exists():
            atomic_write(path, json.dumps({"box_id": box_id, "created": time.time(), "baselines": {}}))
        return {"ok": True, "box_id": box_id, "path": str(box)}


def write_isolated_box(slug, box_id, rel_path, content):
    rel = _box_rel(rel_path)
    with BOX_LOCK:
        box = _box_dir(slug, box_id)
        if not box.exists():
            create_isolated_box(slug, box_id)
        original = _within(Path(_root(slug)).resolve(), rel)
        target = _within(box, rel)
        metadata = _box_metadata(box)
        if rel not in metadata["baselines"]:
            metadata["baselines"][rel] = _file_hash(original)
            atomic_write(_within(box, ".box-meta.json"), json.dumps(metadata))
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, content)
        return {"ok": True, "path": str(target), "size": len(content)}


def read_isolated_box(slug, box_id, rel_path):
    rel = _box_rel(rel_path)
    with BOX_LOCK:
        box = _box_dir(slug, box_id)
        target = _within(box, rel)
        if target.is_file():
            return {"ok": True, "source": "isolated", "content": target.read_text(errors="replace")}
        original = _within(Path(_root(slug)).resolve(), rel)
        if original.is_file():
            return {"ok": True, "source": "project", "content": original.read_text(errors="replace")}
        return {"ok": False, "error": f"File not found: {rel}"}


def list_isolated_box(slug, box_id):
    with BOX_LOCK:
        box = _box_dir(slug, box_id)
        if not box.is_dir():
            return {"ok": False, "error": "Box not found", "files": []}
        files = []
        for path in box.rglob("*"):
            rel = str(path.relative_to(box))
            _within(box, rel)
            if path.is_file() and rel != ".box-meta.json":
                files.append(_box_rel(rel))
        return {"ok": True, "box_id": box_id, "files": sorted(files)}


def merge_isolated_box(slug, box_id, discard_on_success=True):
    with BOX_LOCK:
        listing = list_isolated_box(slug, box_id)
        if not listing["ok"]:
            return listing
        box = _box_dir(slug, box_id)
        root = Path(_root(slug)).resolve()
        baselines = _box_metadata(box)["baselines"]
        changes, conflicts = [], []
        for rel in listing["files"]:
            target = _within(root, rel)
            if rel not in baselines or _file_hash(target) != baselines[rel] or (target.exists() and not target.is_file()):
                conflicts.append(rel)
                continue
            source = _within(box, rel).read_bytes()
            original = target.read_bytes() if target.exists() else None
            changes.append((rel, target, source, original))
        if conflicts:
            return {"ok": False, "conflict": True, "error": "Project files changed or were not staged", "conflicts": conflicts}
        applied = []
        try:
            for rel, target, source, original in changes:
                _within(root, rel)
                if _file_hash(target) != baselines[rel]:
                    raise ValueError(f"Project file changed during merge: {rel}")
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(target, source)
                applied.append((target, source, original))
        except (OSError, ValueError):
            for target, source, original in reversed(applied):
                if target.is_symlink() or not target.is_file() or target.read_bytes() != source:
                    continue
                if original is None:
                    target.unlink()
                else:
                    atomic_write(target, original)
            raise
        if discard_on_success:
            shutil.rmtree(box)
        return {"ok": True, "merged_files": listing["files"]}


def list_isolated_boxes(slug):
    with BOX_LOCK:
        parent = _box_dir(slug, "default").parent
        if not parent.is_dir():
            return []
        boxes = []
        for entry in sorted(parent.iterdir()):
            if not BOX_ID.fullmatch(entry.name) or entry.is_symlink() or not entry.is_dir():
                continue
            listing = list_isolated_box(slug, entry.name)
            if listing["files"]:
                boxes.append(listing)
        return boxes


def discard_isolated_box(slug, box_id):
    with BOX_LOCK:
        box = _box_dir(slug, box_id)
        if box.exists():
            shutil.rmtree(box)
        return {"ok": True, "discarded": box_id}


# ---------------------------------------------------------------------------- Branch Per Change & Merge Approval Workflow
def _git_run(slug, args, check=False):
    root = _root(slug)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
    import pc_bridge
    try:
        result = pc_bridge.git_command(root, args)
    except (OSError, ValueError) as error:
        result = {"error": str(error)}
    res = subprocess.CompletedProcess(args, result.get("exit_code", 1) or (1 if result.get("error") else 0),
                                      result.get("stdout", ""), result.get("error") or result.get("stderr", ""))
    if check and res.returncode != 0:
        raise RuntimeError(res.stderr or f"git command failed: {args}")
    return res


def detect_default_branch(slug):
    # 1. Try remote origin HEAD
    r = _git_run(slug, ["symbolic-ref", "refs/remotes/origin/HEAD"])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().removeprefix("refs/remotes/origin/")
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


BRANCH_LOCK = threading.RLock()
BRANCH_TESTS = {}


def _branch_commit(slug, branch):
    result = _git_run(slug, ["rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}"])
    return result.stdout.strip() if result.returncode == 0 else ""


def _current_branch(slug):
    return _git_run(slug, ["branch", "--show-current"]).stdout.strip()


def _clean_branch(slug):
    result = _git_run(slug, ["status", "--porcelain", "--untracked-files=all", "--",
                             ".", ":(exclude).devpilot"])
    return result.returncode == 0 and not result.stdout.strip()


def _verification_file():
    import runtime_settings
    return runtime_settings.FILE.with_name("branch-verifications.json")


def _branch_verifications():
    try:
        records = json.loads(_verification_file().read_text())
        return records if isinstance(records, dict) else {}
    except (OSError, ValueError):
        return {}


def create_change_branch(slug, branch_name=None):
    with BRANCH_LOCK:
        primary = detect_default_branch(slug)
        if not _clean_branch(slug):
            return {"ok": False, "error": "Save or commit existing changes before starting a change branch."}
        branch = branch_name or f"agent/{slug}-{uuid.uuid4().hex[:10]}"
        if not isinstance(branch, str) or branch.startswith("-") or branch == primary:
            return {"ok": False, "error": "Choose a valid change branch."}
        result = _git_run(slug, ["switch", "-c", branch, primary])
        if result.returncode:
            return {"ok": False, "error": result.stderr or "Could not create the change branch"}
        return {"ok": True, "branch": branch, "default_branch": primary}


def commit_change_branch(slug, message="agent change", branch=None):
    with BRANCH_LOCK:
        current = _current_branch(slug)
        if not current or current == detect_default_branch(slug) or (branch and current != branch):
            return {"ok": False, "error": "Switch to the intended change branch before committing."}
        staged = _git_run(slug, ["add", "-A", "--", ".", ":(exclude).devpilot"])
        if staged.returncode:
            return {"ok": False, "error": staged.stderr}
        result = _git_run(slug, ["-c", "user.name=DevPilot", "-c", "user.email=devpilot@localhost",
                                "commit", "-m", message.strip() or "agent change", "--", ".", ":(exclude).devpilot"])
        if result.returncode:
            if "nothing to commit" in result.stdout + result.stderr:
                return {"ok": True, "committed": False, "message": "nothing to commit"}
            return {"ok": False, "error": result.stderr or "commit failed"}
        return {"ok": True, "committed": True, "commit": _branch_commit(slug, current)}


def get_branch_change_status(slug):
    with BRANCH_LOCK:
        primary = detect_default_branch(slug)
        current = _current_branch(slug)
        result = {"ok": True, "pending_approval": False, "current_branch": current,
                  "default_branch": primary, "commit_count": 0, "commits": []}
        if not current or current == primary:
            return result
        commit, base = _branch_commit(slug, current), _branch_commit(slug, primary)
        if not commit or not base or commit == base:
            return result
        commits = _git_run(slug, ["log", "--oneline", f"{base}..{commit}"]).stdout.splitlines()
        ancestor = _git_run(slug, ["merge-base", "--is-ancestor", base, commit]).returncode == 0
        clean = _clean_branch(slug)
        key = str(Path(_root(slug)).resolve())
        verified = _branch_verifications().get(key) == {"commit": commit, "base": base}
        return {**result, "pending_approval": bool(commits), "commit": commit, "base": base,
                "verified": verified, "can_merge": bool(commits and ancestor and verified and clean),
                "clean": clean, "based_on_primary": ancestor, "commit_count": len(commits), "commits": commits}


def verify_change_branch(slug, test):
    with BRANCH_LOCK:
        status = get_branch_change_status(slug)
        key = str(Path(_root(slug)).resolve())
        records = _branch_verifications()
        token = BRANCH_TESTS[key] = object()
        if key in records:
            del records[key]
            atomic_write(_verification_file(), json.dumps(records))
    import pc_bridge
    readonly = pc_bridge.RUN_READ_ONLY.set(bool(status.get("pending_approval")))
    try:
        result = test()
    except BaseException:
        with BRANCH_LOCK:
            if BRANCH_TESTS.get(key) is token:
                del BRANCH_TESTS[key]
        raise
    finally:
        pc_bridge.RUN_READ_ONLY.reset(readonly)
    with BRANCH_LOCK:
        if BRANCH_TESTS.get(key) is not token:
            return result
        del BRANCH_TESTS[key]
        after = get_branch_change_status(slug)
        if (result.get("ok") is True and status.get("pending_approval") and status.get("clean")
                and after.get("clean") and after.get("based_on_primary")
                and all(after.get(field) == status.get(field) for field in ("commit", "base", "current_branch"))):
            records = _branch_verifications()
            records[key] = {"commit": status["commit"], "base": status["base"]}
            atomic_write(_verification_file(), json.dumps(records))
            return {**result, "verified_commit": status["commit"]}
        return result


def merge_change_branch(slug, branch_name=None, approve=False, *, commit=None):
    if approve is not True or not isinstance(commit, str):
        return {"ok": False, "error": "Explicit approval for the tested commit is required."}
    with BRANCH_LOCK:
        status = get_branch_change_status(slug)
        branch = branch_name or status["current_branch"]
        if (str(Path(_root(slug)).resolve()) in BRANCH_TESTS or not status.get("can_merge")
                or branch != status["current_branch"] or commit != status.get("commit")):
            return {"ok": False, "error": "The current commit must pass tests against the current primary branch in a clean worktree."}
        primary = status["default_branch"]
        switched = _git_run(slug, ["switch", "--", primary])
        if switched.returncode:
            return {"ok": False, "error": switched.stderr}
        if _branch_commit(slug, primary) != status["base"] or _branch_commit(slug, branch) != commit:
            _git_run(slug, ["switch", "--", branch])
            return {"ok": False, "error": "A branch changed after verification. Test it again."}
        merged = _git_run(slug, ["merge", "--ff-only", commit])
        if merged.returncode:
            _git_run(slug, ["switch", "--", branch])
            return {"ok": False, "error": merged.stderr or "Fast-forward merge failed"}
        return {"ok": True, "merged": True, "branch": branch, "default_branch": primary, "commit": commit}
