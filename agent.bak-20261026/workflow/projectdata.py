"""Shared project file invariants for the bridge and Jarvis."""
import hashlib
import os
from pathlib import Path
import re
import tempfile


def revision(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            temp.chmod(path.stat().st_mode & 0o777)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def parse_tasks(content):
    """Read canonical table tasks and Markdown checkboxes, excluding fenced examples."""
    out, milestone, fence = [], "General", None
    for line_no, line in enumerate(content.splitlines(), 1):
        mark = re.match(r"^\s*(`{3,}|~{3,})", line)
        if mark:
            token = mark[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r"^#{1,6}\s+((?:M\d+\b|Milestone\s+\d+\b).*)", line, re.I)
        if heading:
            milestone = heading[1].strip()
        table = re.match(r"^\s*\|\s*(T\d+)\b[^|]*\|", line)
        check = re.match(r"^\s*[-*]\s+\[([ xX])\]\s+(.+)", line)
        if table:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append({"id": table[1], "milestone": cells[1] if len(cells) > 1 else milestone,
                        "title": cells[2] if len(cells) > 2 else cells[0], "done": "✅" in line,
                        "line": line_no})
        elif check:
            out.append({"id": f"L{line_no}", "milestone": milestone, "title": check[2],
                        "done": check[1].lower() == "x", "line": line_no})
    return out


def continuation(state, tasks, jobs, uncommitted, plan_revision):
    """A fresh, read-only resume decision; never executes a checkpoint as code."""
    open_tasks = [task for task in tasks if not task["done"]]
    active = [job["id"] for job in jobs if job.get("running")]
    next_task = open_tasks[0] if open_tasks else None
    checkpoint = str(state.get("next_action") or "").strip()
    completed = {t["id"] for t in tasks if t["done"]}
    mentioned = set(re.findall(r"\bT\d+\b", checkpoint))
    stale = bool(mentioned and mentioned <= completed)
    if active:
        action, reason = "inspect_jobs", "Inspect the existing background job before starting duplicate work."
    elif uncommitted:
        action, reason = "inspect_changes", "Inspect uncommitted changes and finish or verify interrupted work."
    elif re.search(r"\bblocked\b", str(state.get("status", "")), re.I):
        action, reason = "review_blocker", "Check whether the recorded blocker has changed before retrying."
    elif next_task:
        action, reason = "continue_task", "Read the next unfinished task, dependencies and current authorization."
    elif tasks:
        action, reason = "verify_completion", "All plan tasks are checked; verify acceptance criteria and QA before reporting completion."
    elif checkpoint:
        action, reason = "continue_checkpoint", "Reconcile the checkpoint with current project artifacts and continue the unfinished phase."
    else:
        action, reason = "review_intake", "Read PROJECT.md and establish the next unfinished lifecycle step."
    return {"action": action, "reason": reason, "next_task": next_task,
            "checkpoint_action": checkpoint, "checkpoint_needs_review": stale,
            "running_job_ids": active, "plan_revision": plan_revision,
            "rules": "Read current files and approval. Preserve authorized scope, completed work and user edits. Save a concrete checkpoint after each handoff. Do not launch duplicate jobs or claim completion without QA evidence."}
