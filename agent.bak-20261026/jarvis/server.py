#!/usr/bin/env python3
"""Jarvis: local web UI + standalone engine for the DevPilot agents.

  http://127.0.0.1:8770        HUD (chat, live agent graph, project / files / activity panels)
  GET  /api/config             agents, models, tools (for the graph)
  GET  /api/sessions           saved conversations
  GET  /api/session?id=        one conversation (messages + recent events)
  GET  /api/events?id=&from=   server-sent events for a session (live run)
  POST /api/chat {id?, text}   start a turn (returns session id)
  POST /api/stop {id}          stop the running turn
  GET  /api/projects | /api/project?slug= | /api/tree?path= | /api/file?path=   read-only views via the bridge

Listens on localhost only. POSTs need the `X-Jarvis: 1` header and a same-origin Origin (blocks other sites).
"""
import json
import os
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402
import mesh  # noqa: E402
import control  # noqa: E402
import forms  # noqa: E402
import codetools  # noqa: E402
import studio  # noqa: E402
from projectdata import atomic_write

HERE = Path(__file__).resolve().parent
HOST, PORT = "127.0.0.1", int(os.environ.get("JARVIS_PORT", "8770"))
SESSIONS = HERE / "sessions"
SESSIONS.mkdir(exist_ok=True)
MAX_EVENTS = 4000
MAX_HISTORY = 3000
# Agent/tool events kept for the whole conversation so a page reload can rebuild the work cards and Activity log
# (raw token/thinking events are only kept for the most recent part of the stream).
HISTORY_TYPES = {"turn_start", "turn_end", "agent_start", "agent_end", "tool_start", "tool_end", "retry"}
SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


class Session:
    def __init__(self, sid=None, title="New session"):
        self.id = sid or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.title, self.messages, self.events = title, [], []
        self.cond = threading.Condition()
        self.running, self.engine = False, None
        self.stop_requested = threading.Event()
        self.pause_requested = threading.Event()
        self.next_seq, self.project, self._saved_at = 0, "", 0
        self.history = []
        self.save_lock, self._written_seq = threading.Lock(), -1
        self.created = time.strftime("%Y-%m-%d %H:%M")

    @classmethod
    def load(cls, sid):
        f = SESSIONS / f"{sid}.json"
        d = json.loads(f.read_text())
        if not isinstance(d, dict) or d.get("id") != sid:
            raise ValueError("invalid saved session")
        s = cls(sid, d.get("title", "Session"))
        s.messages, s.events, s.created = d.get("messages", []), d.get("events", [])[-800:], d.get("created", "")
        s.next_seq = max(d.get("next_seq", 0), max((e.get("seq", -1) + 1 for e in s.events), default=0))
        s.project = d.get("project", "")
        s.history = d.get("history") or [e for e in s.events if e.get("type") in HISTORY_TYPES]
        if d.get("running"):
            text = "The previous run was interrupted when K.R.Y.Z.E.N restarted. Say continue to resume from the project checkpoint."
            s.messages.append({"role": "assistant", "content": text, "t": time.time()})
            s.emit({"type": "turn_end", "text": text, "interrupted": True})
            s.save()
        return s

    def save(self):
        # Snapshot under the lock, encode + write outside it so live event streams are never blocked by disk I/O.
        with self.cond:
            snap = {"id": self.id, "title": self.title, "created": self.created, "messages": list(self.messages),
                    "events": self.events[-800:], "history": self.history[-MAX_HISTORY:], "next_seq": self.next_seq,
                    "project": self.project, "running": self.running}
            self._saved_at = time.monotonic()
        with self.save_lock:
            if snap["next_seq"] < self._written_seq or (snap["next_seq"] == self._written_seq and snap["running"]):
                return
            atomic_write(SESSIONS / f"{self.id}.json", json.dumps(snap, ensure_ascii=False))
            self._written_seq = snap["next_seq"]

    def emit(self, ev):
        with self.cond:
            ev = {**ev, "seq": self.next_seq, "t": time.time()}
            self.next_seq += 1
            self.events.append(ev)
            if ev["type"] in HISTORY_TYPES:
                self.history.append(_compact(ev))
                if len(self.history) > MAX_HISTORY:
                    self.history = self.history[-MAX_HISTORY:]
            if len(self.events) > MAX_EVENTS:
                self.events = self.events[-MAX_EVENTS:]
            self.cond.notify_all()
            due = ev["type"] in ("turn_start", "turn_end", "tool_end", "run_state") or time.monotonic() - self._saved_at >= 1
            if due:
                self._saved_at = time.monotonic()
        if due:
            self.save()
        return ev

    def run(self, text, project=""):
        self.running = True
        self.project = project
        if self.title == "New session":
            self.title = text.strip().splitlines()[0][:60]
        self.messages.append({"role": "user", "content": text, "t": time.time()})
        self.emit({"type": "turn_start", "text": text})
        try:
            with CONFIG_LOCK:
                self.engine = engine.Engine(self.emit, project=project)
            if self.stop_requested.is_set():
                self.engine.stop.set()
            if self.pause_requested.is_set():
                self.engine.pause_requested.set()
            history = [{"role": m["role"], "content": m["content"]} for m in self.messages[:-1]]
            reply = self.engine.respond(text, history)
            self.messages.append({"role": "assistant", "content": reply, "t": time.time()})
            self.emit({"type": "turn_end", "text": reply})
        except engine.Stopped:
            self.messages.append({"role": "assistant", "content": "⏹ Stopped. Say *continue* to resume.", "t": time.time()})
            self.emit({"type": "turn_end", "text": "⏹ Stopped. Say continue to resume.", "stopped": True})
        except Exception as e:
            msg = f"⚠️ {type(e).__name__}: {e}\n\nSay *continue* to resume from the last checkpoint."
            self.messages.append({"role": "assistant", "content": msg, "t": time.time()})
            self.emit({"type": "turn_end", "text": msg, "error": True})
        finally:
            with self.cond:
                self.running = False
                self.save()
                self.cond.notify_all()


def _compact(ev):
    ev = dict(ev)
    for k in ("text", "preview", "task"):
        if isinstance(ev.get(k), str) and len(ev[k]) > 4000:
            ev[k] = ev[k][:4000] + "…"
    if "args" in ev:
        a = ev["args"] if isinstance(ev["args"], str) else json.dumps(ev["args"], ensure_ascii=False)
        ev["args"] = a[:600]
    return ev


LIVE = {}
LIVE_LOCK = threading.Lock()
CONFIG_LOCK = threading.RLock()
START_LOCK = threading.Lock()


def get_session(sid, create=False):
    if sid is not None and (not isinstance(sid, str) or not SESSION_ID.fullmatch(sid)):
        raise ValueError("invalid session id")
    with LIVE_LOCK:
        if sid in LIVE:
            return LIVE[sid]
        if sid and (SESSIONS / f"{sid}.json").exists():
            LIVE[sid] = Session.load(sid)
            return LIVE[sid]
        if create and not sid:
            s = Session()
            LIVE[s.id] = s
            return s
    return None


def bridge(path, body):
    e = engine.Engine.__new__(engine.Engine)
    e.bridge_token = engine.secret(engine.AGENT_DIR / "bridge" / ".token")
    return json.loads(engine.Engine.bridge(e, path, body))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if code >= 400:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if "/api/events" not in str(args[0] if args else ""):
            print(f"[jarvis] {fmt % args}", flush=True)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/favicon.ico":
                return self.send(204, b"", "image/x-icon")
            if u.path == "/assets/user-avatar.svg":
                return self.send(200, (HERE / "assets/user-avatar.svg").read_bytes(), "image/svg+xml")
            if u.path == "/health":
                return self.send(200, {"ok": True, "active_runs": sum(s.running for s in list(LIVE.values()))})
            if u.path in ("/studio.js", "/studio.css", "/reference-theme.css", "/panel-resize.js", "/panel-resize.css"):
                return self.send(200, (HERE / u.path[1:]).read_bytes(),
                                 "text/javascript; charset=utf-8" if u.path.endswith(".js") else "text/css; charset=utf-8")
            if u.path.startswith("/api/studio/"):
                action = u.path.rsplit("/", 1)[1]
                getter = {"flows": studio.flows_get, "flow": lambda: studio.flow_get(q.get("name", "")),
                          "plan": lambda: studio.plan_get(bridge, q.get("slug", "")),
                          "overview": studio.overview}.get(action)
                if not getter:
                    return self.send(404, {"error": "unknown studio action"})
                try:
                    return self.send(200, getter())
                except (ValueError, FileNotFoundError) as e:
                    return self.send(400, {"error": str(e)})
            if u.path == "/api/config":
                agents = engine.load_agents()
                info = {n["name"]: n for n in mesh.notes()}
                info[engine.ORCHESTRATOR] = next((n for n in info.values() if n["orchestrator"]), {})
                return self.send(200, {"agents": [{
                    "name": a.name, "model": a.model.split("/")[-1], "steps": a.max_iter, "description": a.description,
                    "color": info.get(a.name, {}).get("color", "gray"), "role": info.get(a.name, {}).get("role", ""),
                    "skills": info.get(a.name, {}).get("skills", []),
                    "tools": [{"name": t.name, "title": t.title, "kind": t.kind} for t in a.tools]}
                    for a in agents.values()]})
            if u.path == "/api/mesh":
                return self.send(200, mesh.mesh())
            if u.path.startswith("/api/form/"):
                getter = {"appearance": forms.appearance_get, "blocks": forms.blocks_get, "tools": forms.tools_get,
                          "skills": forms.skills_get, "models": forms.models_get}.get(u.path.rsplit("/", 1)[1])
                return self.send(200, getter()) if getter else self.send(404, {"error": "unknown form"})
            if u.path.startswith("/api/code/"):
                act, slug = u.path.rsplit("/", 1)[1], q.get("slug", "")
                try:
                    if act == "tree":
                        return self.send(200, codetools.tree(bridge, slug))
                    if act == "file":
                        return self.send(200, codetools.read(bridge, slug, q.get("path", "")))
                    if act == "scripts":
                        return self.send(200, codetools.scripts(bridge, slug))
                    if act == "jobs":
                        return self.send(200, codetools.jobs(bridge))
                    if act == "job":
                        return self.send(200, codetools.job(bridge, q.get("id", ""), int(q.get("tail", 20000))))
                except ValueError as e:
                    return self.send(200, {"error": str(e)})
                return self.send(404, {"error": "unknown code action"})
            if u.path == "/api/ui":
                return self.send(200, control.ui())
            if u.path == "/api/control/tree":
                return self.send(200, control.tree(q.get("root", "vault")))
            if u.path == "/api/control/file":
                return self.send(200, control.read(q.get("root", "vault"), q["path"]))
            if u.path == "/api/control/services":
                return self.send(200, control.services())
            if u.path == "/api/sessions":
                target_project = q.get("project")
                items = []
                for f in sorted(SESSIONS.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
                    try:
                        d = json.loads(f.read_text())
                        proj = d.get("project") or ""
                        if target_project and proj != target_project:
                            continue
                        items.append({"id": d["id"], "title": d.get("title", ""), "created": d.get("created", ""),
                                      "messages": len(d.get("messages", [])), "project": proj,
                                      "running": bool(LIVE.get(d["id"]) and LIVE[d["id"]].running)})
                        if len(items) >= 50:
                            break
                    except (OSError, ValueError):
                        pass
                return self.send(200, {"sessions": items})
            if u.path == "/api/session":
                s = get_session(q.get("id"))
                if not s:
                    return self.send(404, {"error": "no such session"})
                active_from = max(s.events[0]["seq"] if s.events else s.next_seq,
                                  next((e["seq"] for e in reversed(s.events) if e["type"] == "turn_start"), s.next_seq))
                cut = active_from if s.running else s.next_seq
                return self.send(200, {"id": s.id, "title": s.title, "running": s.running, "messages": s.messages,
                                       "next_seq": s.next_seq, "project": s.project, "active_from": active_from,
                                       "history": [e for e in s.history if e.get("seq", 0) < cut],
                                       "paused": bool(s.engine and s.engine.paused.is_set()),
                                       "pause_requested": s.pause_requested.is_set() or bool(s.engine and s.engine.pause_requested.is_set())})
            if u.path == "/api/events":
                return self.stream(q.get("id"), int(q.get("from", 0)))
            if u.path == "/api/projects":
                return self.send(200, bridge("/project/list", {}))
            if u.path == "/api/project":
                return self.send(200, bridge("/project/resume", {"slug": q.get("slug", "")}))
            if u.path == "/api/tree":
                return self.send(200, bridge("/fs/list", {"path": q.get("path", ""), "depth": int(q.get("depth", 3))}))
            if u.path == "/api/file":
                return self.send(200, bridge("/fs/read", {"path": q["path"], "limit": 2000}))
            self.send(404, {"error": "not found"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def stream(self, sid, start):
        s = get_session(sid)
        if not s:
            return self.send(404, {"error": "no such session"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last_id = self.headers.get("Last-Event-ID")
        i = max(0, int(last_id) + 1 if last_id and last_id.isdigit() else start)
        try:
            while True:
                with s.cond:
                    if i >= s.next_seq:
                        s.cond.wait(timeout=15)
                    if s.events and i < s.events[0]["seq"]:
                        self.wfile.write(b'data: {"type":"resync"}\n\n')
                        self.wfile.flush()
                        return
                    batch = [ev for ev in s.events if ev["seq"] >= i]
                if not batch:
                    self.wfile.write(b": ping\n\n")
                for ev in batch:
                    self.wfile.write(f"id: {ev['seq']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                    i = ev["seq"] + 1
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            if self.path.startswith(("/api/mesh/", "/api/form/", "/api/control/")):
                with CONFIG_LOCK:
                    self.post()
            elif self.path in ("/api/chat", "/api/continue"):
                with START_LOCK:
                    self.post()
            else:
                self.post()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, TypeError, KeyError) as e:
            self.send(400, {"ok": False, "error": str(e), "errors": [str(e)]})
        except Exception as e:
            self.send(500, {"ok": False, "error": f"{type(e).__name__}: {e}", "errors": [str(e)]})

    def post(self):
        origin = self.headers.get("Origin", "")
        if self.headers.get("X-Jarvis") != "1" or (origin and origin not in (f"http://{HOST}:{PORT}",
                                                                            f"http://localhost:{PORT}")):
            return self.send(403, {"error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= 4000000:
                return self.send(413, {"error": "request too large"})
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be a JSON object")
        except (ValueError, json.JSONDecodeError) as e:
            return self.send(400, {"error": str(e)})
        u = urlparse(self.path).path
        if u.startswith("/api/studio/"):
            act = u.rsplit("/", 1)[1]
            action = {"flow": studio.flow_save, "flow-create": studio.flow_create,
                      "flow-active": studio.flow_activate,
                      "plan": lambda b: studio.plan_save(bridge, b),
                      "plan-task": lambda b: studio.plan_task(bridge, b),
                      "plan-approval": lambda b: studio.plan_approval(bridge, b)}.get(act)
            if not action:
                return self.send(404, {"error": "unknown studio action"})
            if any(s.running for s in list(LIVE.values())) and act in ("flow-active", "plan-approval"):
                return self.send(409, studio.fail("wait until the current run finishes before changing routing or approval"))
            try:
                return self.send(200, action(body))
            except (ValueError, TypeError, KeyError, OSError) as e:
                return self.send(400, studio.fail(str(e)))
        if u == "/api/run-control":
            s = get_session(body.get("id"))
            if not s or not s.running:
                return self.send(409, studio.fail("no active run to control"))
            action = body.get("action")
            if action not in ("pause", "resume"):
                return self.send(400, studio.fail("action must be pause or resume"))
            if action == "pause":
                s.pause_requested.set()
                if s.engine:
                    s.engine.pause_requested.set()
                state = "pause_requested"
            else:
                s.pause_requested.clear()
                if s.engine:
                    s.engine.pause_requested.clear()
                state = "running"
            event = s.emit({"type": "run_state", "state": state})
            return self.send(200, {"ok": True, "state": state, "seq": event["seq"]})
        if u in ("/api/chat", "/api/continue"):
            if not isinstance(body.get("project", ""), str):
                return self.send(400, {"error": "project must be a slug"})
            if u == "/api/continue":
                if not body.get("project"):
                    return self.send(400, {"error": "choose a project to continue"})
                body["text"] = f"Continue project {body['project']} from its saved checkpoint."
            text = body.get("text", "")
            if not isinstance(text, str) or len(text) > 100000:
                return self.send(400, {"error": "message must be text under 100 KB"})
            text = text.strip()
            if not text:
                return self.send(400, {"error": "empty message"})
            project = str(body.get("project") or "")
            if project:
                try:
                    studio._project(bridge, project)
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
            s = get_session(body.get("id"), create=True)
            if s is None:
                return self.send(404, {"error": "session no longer exists; start a new session", "missing_session": True})
            with s.cond:
                if s.running:
                    return self.send(409, {"error": "a turn is already running", "id": s.id})
                if s.project and project and s.project != project:
                    return self.send(409, {"error": "start a new session for a different project", "project_mismatch": True})
                s.stop_requested.clear()
                s.pause_requested.clear()
                s.engine = None
                s.running = True
                project = project or s.project
                other = next((run for run in list(LIVE.values()) if run is not s and run.running and project and run.project == project), None)
                if other:
                    s.running = False
                    return self.send(409, {"error": "this project already has an active run; open its chat to pause, resume or stop it", "active_session": other.id})
                s.project = project
                start = s.next_seq
            threading.Thread(target=s.run, args=(text, project), daemon=True).start()
            return self.send(200, {"id": s.id, "from_seq": start, "project": project})
        if u.startswith("/api/mesh/"):
            action = {"save": mesh.save, "create": mesh.create, "archive": mesh.archive,
                      "sync": lambda _b: mesh.sync()}.get(u.rsplit("/", 1)[1])
            if not action:
                return self.send(404, {"error": "unknown mesh action"})
            if any(s.running for s in list(LIVE.values())) and u.endswith(("archive", "create")):
                return self.send(409, {"ok": False, "errors": ["wait until the current run finishes"]})
            return self.send(200, action(body))
        if u.startswith("/api/code/"):
            act, slug = u.rsplit("/", 1)[1], str(body.get("slug", ""))
            try:
                if act == "save":
                    return self.send(200, codetools.save(bridge, slug, body.get("path", ""), str(body.get("content", "")),
                                                         body.get("revision"), bool(body.get("create_only"))))
                if act == "run":
                    return self.send(200, codetools.run(bridge, slug, str(body.get("cmd", "")), body.get("background", False)))
                if act == "search":
                    return self.send(200, codetools.search(bridge, slug, str(body.get("q", "")), bool(body.get("regex")),
                                                           bool(body.get("case")), str(body.get("glob", ""))))
                if act == "git":
                    return self.send(200, codetools.git(bridge, slug, str(body.get("action", "")),
                                                        str(body.get("message", "")), str(body.get("file", ""))))
                if act == "stop":
                    return self.send(200, codetools.stop(bridge, str(body.get("id", ""))))
            except ValueError as e:
                return self.send(200, {"error": str(e)})
            return self.send(404, {"error": "unknown code action"})
        if u.startswith("/api/form/"):
            act = u.rsplit("/", 1)[1]
            fn = {"appearance": forms.appearance_save, "blocks": forms.blocks_save, "tool": forms.tool_save,
                  "tool-delete": forms.tool_delete, "skill": forms.skill_save, "skill-delete": forms.skill_delete,
                  "project": lambda b: forms.project_create(b, bridge)}.get(act)
            if not fn:
                return self.send(404, {"error": "unknown form"})
            if any(s.running for s in list(LIVE.values())) and act not in ("appearance", "project"):
                return self.send(200, {"ok": False, "errors": ["wait until the current run finishes"]})
            try:
                return self.send(200, fn(body))
            except Exception as e:
                return self.send(200, {"ok": False, "errors": [f"{type(e).__name__}: {e}"]})
        if u.startswith("/api/control/"):
            act = u.rsplit("/", 1)[1]
            root, path = body.get("root", "vault"), str(body.get("path", ""))
            try:
                if act == "save":
                    return self.send(200, control.save(root, path, str(body.get("content", "")), body.get("revision")))
                if act == "create":
                    return self.send(200, control.create(root, path, body.get("kind", "file")))
                if act == "delete":
                    return self.send(200, control.delete(root, path))
                if act == "rename":
                    return self.send(200, control.rename(root, path, str(body.get("to", ""))))
                if act == "service":
                    return self.send(200, control.service_action(body.get("id"), body.get("action")))
            except (PermissionError, KeyError, FileNotFoundError) as e:
                return self.send(200, {"ok": False, "errors": [str(e)]})
            return self.send(404, {"error": "unknown control action"})
        if u == "/api/stop":
            s = get_session(body.get("id"))
            if s and s.running:
                s.stop_requested.set()
                if s.engine:
                    s.engine.stop.set()
            return self.send(200, {"stopping": bool(s and s.running)})
        self.send(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"[jarvis] http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
