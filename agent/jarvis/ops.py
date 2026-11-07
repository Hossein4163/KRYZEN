"""Operations for the dashboard: approval inbox, deep health checks and project overview."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

import control

# ----------------------------------------------------------------------------- approval inbox (review mode)
APPROVALS = {}
APPROVALS_LOCK = threading.Lock()


class Rejected(Exception):
    pass


def request_approval(session, data, stop):
    """Block the calling agent thread until the user approves/rejects (or the run is stopped)."""
    aid = uuid.uuid4().hex[:12]
    item = {"id": aid, "session": session.id, "project": session.project, "t": time.time(), **data,
            "event": threading.Event(), "decision": None}
    with APPROVALS_LOCK:
        APPROVALS[aid] = item
    session.emit({"type": "approval_request", "id": aid, "agent": data.get("agent"), "path": data.get("path"),
                  "kind": data.get("kind"), "added": data.get("added"), "new_file": data.get("new_file"),
                  "diff_preview": data.get("diff", "")[:3000]})
    try:
        while not item["event"].wait(0.3):
            if stop.is_set():
                import engine
                raise engine.Stopped()
        return item["decision"]
    finally:
        with APPROVALS_LOCK:
            APPROVALS.pop(aid, None)
        session.emit({"type": "approval_done", "id": aid,
                      "approved": bool(item["decision"] and item["decision"].get("approved"))})


def resolve_approval(aid, approved, note=""):
    with APPROVALS_LOCK:
        item = APPROVALS.get(aid)
    if not item:
        return {"ok": False, "error": "this approval is no longer pending"}
    item["decision"] = {"approved": bool(approved), "note": str(note or "")[:500]}
    item["event"].set()
    return {"ok": True}


def pending_approvals(include_diff=False):
    with APPROVALS_LOCK:
        items = list(APPROVALS.values())
    keys = ("id", "session", "project", "t", "kind", "agent", "path", "added", "new_file") + (("diff",) if include_diff else ())
    return [{k: i.get(k) for k in keys} for i in sorted(items, key=lambda x: x["t"])]


# ----------------------------------------------------------------------------- deep health
_health_cache = {"t": 0, "data": None}


def _sh(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def deep_health(force=False):
    if not force and _health_cache["data"] and time.time() - _health_cache["t"] < 20:
        return _health_cache["data"]
    checks = []
    for s in control.services()["services"]:
        checks.append({"id": s["id"], "title": s["title"], "ok": s["up"],
                       "detail": "responding" if s["up"] else "not responding"})
    for label, path in (("Workspace disk", os.environ.get("KRYZEN_WORKSPACE", str(Path.home() / "Projects"))),
                        ("App disk", str(Path(__file__).parent))):
        try:
            du = shutil.disk_usage(path)
            free = du.free / du.total
            checks.append({"id": "disk-" + label.split()[0].lower(), "title": label, "ok": free > .05,
                           "detail": f"{du.free / 1e9:.1f} GB free ({free:.0%})"})
        except OSError:
            pass
    data = {"checks": checks, "ok": all(c["ok"] for c in checks), "t": time.time()}
    _health_cache.update(t=time.time(), data=data)
    return data


# ----------------------------------------------------------------------------- projects overview
_projects_cache = {"t": 0, "data": None}


def projects_overview(bridge, plan_get, limit=12):
    if _projects_cache["data"] is not None and time.time() - _projects_cache["t"] < 15:
        return _projects_cache["data"]
    out = []
    try:
        folders = (bridge("/project/list", {}) or {}).get("folders", [])[:limit]
    except Exception:  # noqa: BLE001
        folders = []
    for slug in folders:
        item = {"slug": slug, "done": 0, "total": 0, "state": "", "next": ""}
        try:
            plan = plan_get(bridge, slug)
            tasks = plan.get("tasks") or []
            item["total"] = len(tasks)
            item["done"] = sum(1 for t in tasks if t.get("done"))
            nxt = next((t for t in tasks if not t.get("done")), None)
            item["next"] = ((nxt or {}).get("title") or (nxt or {}).get("text") or "")[:140]
            st = plan.get("state") or {}
            item["state"] = (st.get("status") or st.get("phase") or "") if isinstance(st, dict) else str(st)[:40]
            item["approval"] = (plan.get("approval") or {}).get("status", "") if isinstance(plan.get("approval"), dict) else ""
        except Exception as e:  # noqa: BLE001
            item["error"] = str(e)[:120]
        out.append(item)
    _projects_cache.update(t=time.time(), data=out)
    return out
