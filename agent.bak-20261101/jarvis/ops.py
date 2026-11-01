"""Operations for the dashboard: approval inbox, deep health checks, backend repair and project overview."""
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
COMPOSE_PROJECT = os.environ.get("KRYZEN_COMPOSE_PROJECT", "n8n")
N8N_CONTAINER = os.environ.get("N8N_CONTAINER", f"{COMPOSE_PROJECT}-n8n-1")


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
    code, out = _sh(["docker", "info", "--format", "{{.ServerVersion}}"])
    checks.append({"id": "docker", "title": "Docker", "ok": code == 0,
                   "detail": f"engine {out}" if code == 0 else out[:200]})
    if code == 0:
        _, gw = _sh(["docker", "network", "inspect", f"{COMPOSE_PROJECT}_default", "-f",
                     "{{range .IPAM.Config}}{{.Gateway}}{{end}}"])
        _, addrs = _sh(["ip", "-4", "-br", "addr"])
        gw = gw.split()[0] if gw else ""
        has_gw = bool(gw) and re.search(rf"\b{re.escape(gw)}/", addrs) is not None
        checks.append({"id": "network", "title": "Backend network", "ok": has_gw,
                       "detail": f"gateway {gw} present" if has_gw else
                       f"gateway {gw or '?'} has no address on the host — Repair backend recreates it",
                       "fix": None if has_gw else "repair"})
        docker0 = re.search(r"^docker0\s+\S+\s+(\d+\.\d+\.\d+\.\d+)", addrs, re.M)
        checks.append({"id": "docker0", "title": "Docker default bridge", "ok": bool(docker0),
                       "detail": "address present" if docker0 else
                       "docker0 has no address; containers relying on daemon DNS fail. Fix: sudo systemctl restart docker"})
        code, out = _sh(["docker", "exec", N8N_CONTAINER, "nslookup", "registry.npmjs.org"], timeout=8)
        dns_ok = code == 0 and re.search(r"Address:?\s*\d+\.\d+\.\d+\.\d+", out.split("Name:", 1)[-1]) is not None
        checks.append({"id": "dns", "title": "Container DNS", "ok": dns_ok,
                       "detail": "resolving" if dns_ok else "lookups fail inside the backend containers",
                       "fix": None if dns_ok else "repair"})
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


# ----------------------------------------------------------------------------- backend repair
REPAIR = {"state": "idle", "log": "", "t": 0}


def repair_backend():
    if REPAIR["state"] == "running":
        return {"ok": False, "error": "a repair is already running"}
    REPAIR.update(state="running", log="", t=time.time())

    def work():
        root = str(control.N8N_DIR)
        log = []
        for cmd in (["docker", "compose", "-p", COMPOSE_PROJECT, "down"],
                    ["docker", "compose", "-p", COMPOSE_PROJECT, "up", "-d"]):
            try:
                r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600)
                code, out = r.returncode, r.stdout + r.stderr
            except (OSError, subprocess.TimeoutExpired) as e:
                code, out = 1, str(e)
            log.append("$ " + " ".join(cmd) + "\n" + out[-3000:])
            if code:
                REPAIR.update(state="failed", log="\n".join(log))
                return
        _sh(["systemctl", "--user", "restart", os.environ.get("KRYZEN_BRIDGE_UNIT", "pc-bridge")], timeout=30)
        _health_cache["data"] = None
        REPAIR.update(state="done", log="\n".join(log))
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "state": "running"}


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
