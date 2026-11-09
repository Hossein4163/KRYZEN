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
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
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
import ops  # noqa: E402
import media  # noqa: E402
import runtime_settings  # noqa: E402
import skills2  # noqa: E402
import telemetry  # noqa: E402
import project_logic  # noqa: E402
from orchestration import REQUESTS  # noqa: E402
from projectdata import atomic_write

HERE = Path(__file__).resolve().parent


def get_bind_host():
    if "JARVIS_HOST" in os.environ:
        return os.environ["JARVIS_HOST"]
    try:
        cfg = runtime_settings.get(mask_secrets=False)
        if cfg.get("allow_tailscale", True) or cfg.get("allow_lan", True):
            return "0.0.0.0"
    except Exception:
        pass
    return "127.0.0.1"


HOST, PORT = get_bind_host(), int(os.environ.get("JARVIS_PORT", "8770"))
LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1", "jarvis.local", "agy.local", "studio.local", "devpilot.local"}


def is_allowed_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_loopback:
            return True
        cfg = runtime_settings.get(mask_secrets=False)
        # Tailscale CGNAT range 100.64.0.0/10
        if cfg.get("allow_tailscale", True) and ip in ipaddress.ip_network("100.64.0.0/10"):
            return True
        # Private LAN RFC 1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
        if cfg.get("allow_lan", True) and ip.is_private:
            return True
    except Exception:
        pass
    return False


def is_local_host(host_header):
    if not host_header:
        return False
    h = host_header.strip().lower()
    hostname = h.split(":", 1)[0]
    if hostname in LOCAL_HOSTNAMES or hostname.endswith(".local"):
        return True
    cfg = runtime_settings.get(mask_secrets=False)
    # Tailscale MagicDNS (*.ts.net)
    if cfg.get("allow_tailscale", True) and hostname.endswith(".ts.net"):
        return True
    # Custom allowed hosts
    custom = [c.strip().lower() for c in cfg.get("custom_allowed_hosts", "").split(",") if c.strip()]
    if hostname in custom:
        return True
    return is_allowed_ip(hostname)


def is_local_origin(origin_header):
    if not origin_header:
        return True
    try:
        parsed = urlparse(origin_header)
        hostname = (parsed.hostname or "").lower()
        if hostname in LOCAL_HOSTNAMES or hostname.endswith(".local"):
            return True
        cfg = runtime_settings.get(mask_secrets=False)
        if cfg.get("allow_tailscale", True) and hostname.endswith(".ts.net"):
            return True
        custom = [c.strip().lower() for c in cfg.get("custom_allowed_hosts", "").split(",") if c.strip()]
        if hostname in custom:
            return True
        return is_allowed_ip(hostname)
    except Exception:
        return False


def get_network_status():
    import shutil
    tailscale_bin = shutil.which("tailscale") or "/usr/bin/tailscale"
    installed = Path(tailscale_bin).exists()
    running = False
    ts_ip = ""
    ts_name = ""
    ts_auth_url = ""
    ts_status_text = "Tailscale not installed"
    if installed:
        try:
            res = subprocess.run([tailscale_bin, "status", "--json"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                js = json.loads(res.stdout)
                running = js.get("BackendState") == "Running"
                self_node = js.get("Self", {})
                ts_ips = self_node.get("TailscaleIPs", [])
                ts_ip = ts_ips[0] if ts_ips else ""
                ts_name = self_node.get("DNSName", "").rstrip(".")
                ts_auth_url = js.get("AuthURL", "")
                ts_status_text = js.get("BackendState", "Stopped")
            else:
                ts_status_text = res.stderr.strip() or "Stopped"
        except Exception as ex:
            ts_status_text = str(ex)

    lan_ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    cfg = runtime_settings.get(mask_secrets=True)
    return {
        "ok": True,
        "tailscale_installed": installed,
        "tailscale_running": running,
        "tailscale_ip": ts_ip,
        "tailscale_hostname": ts_name,
        "tailscale_auth_url": ts_auth_url,
        "tailscale_status": ts_status_text,
        "lan_ips": lan_ips,
        "port": PORT,
        "allow_tailscale": cfg.get("allow_tailscale", True),
        "allow_lan": cfg.get("allow_lan", True),
        "tailscale_serve": cfg.get("tailscale_serve", False),
        "bound_host": HOST,
    }


def tailscale_action(action, args=None):
    import shutil
    tailscale_bin = shutil.which("tailscale") or "/usr/bin/tailscale"
    if not Path(tailscale_bin).exists():
        return {"ok": False, "error": "Tailscale is not installed on this machine."}
    try:
        if action == "start_service":
            res = subprocess.run(["sudo", "-n", "systemctl", "start", "tailscaled"], capture_output=True, text=True, timeout=5)
            return {"ok": res.returncode == 0, "output": res.stdout or res.stderr}
        elif action == "up":
            res = subprocess.run(["sudo", "-n", "tailscale", "up", "--reset"], capture_output=True, text=True, timeout=5)
            return {"ok": res.returncode == 0, "output": res.stdout or res.stderr}
        elif action == "down":
            res = subprocess.run(["sudo", "-n", "tailscale", "down"], capture_output=True, text=True, timeout=5)
            return {"ok": res.returncode == 0, "output": res.stdout or res.stderr}
        elif action == "serve":
            port = str(PORT)
            res = subprocess.run(["sudo", "-n", "tailscale", "serve", "--bg", port], capture_output=True, text=True, timeout=5)
            return {"ok": res.returncode == 0, "output": res.stdout or res.stderr}
        return {"ok": False, "error": "Unknown tailscale action"}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


def test_model_provider(data):
    provider = data.get("provider", "openai")
    cfg = runtime_settings.get(mask_secrets=False)
    base_url = data.get("base_url") or cfg.get("openai_base_url") or "https://generativelanguage.googleapis.com/v1beta/openai/"
    api_key = data.get("api_key") or ""
    if not api_key or api_key == "••••••••":
        api_key = cfg.get("openai_api_key", "")
    model = data.get("model") or cfg.get("tier_reasoning", "gemini-3.8-flash")

    t0 = time.time()
    try:
        if provider == "ollama" or "11434" in str(base_url):
            host = str(base_url).rstrip("/").replace("/v1", "")
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as r:
                tags = json.loads(r.read())
                models = [m.get("name") for m in tags.get("models", [])]
                latency = round((time.time() - t0) * 1000)
                return {"ok": True, "provider": "ollama", "latency_ms": latency, "available_models": models,
                        "message": f"Ollama online ({len(models)} models available)"}
        elif provider == "agy":
            import shutil
            agy_bin = shutil.which("agy") or str(Path.home() / ".local/bin/agy")
            if not Path(agy_bin).exists():
                return {"ok": False, "error": "agy CLI executable not found"}
            res = subprocess.run([agy_bin, "--version"], capture_output=True, text=True, timeout=2)
            latency = round((time.time() - t0) * 1000)
            return {"ok": True, "provider": "agy", "latency_ms": latency, "message": f"Antigravity CLI available: {res.stdout.strip()}"}
        else:
            url = str(base_url).rstrip("/")
            if not url.endswith("/chat/completions"):
                url += "/chat/completions"
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5
            }).encode()
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                res_data = json.loads(resp.read())
                latency = round((time.time() - t0) * 1000)
                resp_model = res_data.get("model", model)
                return {"ok": True, "provider": "openai", "latency_ms": latency, "model": resp_model,
                        "message": f"API endpoint responded in {latency}ms (model: {resp_model})"}
    except urllib.error.HTTPError as e:
        latency = round((time.time() - t0) * 1000)
        try:
            err_body = json.loads(e.read()).get("error", {})
            msg = err_body.get("message", str(e))
        except Exception:
            msg = str(e)
        return {"ok": False, "latency_ms": latency, "status": e.code, "error": f"HTTP {e.code}: {msg}"}
    except Exception as ex:
        latency = round((time.time() - t0) * 1000)
        return {"ok": False, "latency_ms": latency, "error": str(ex)}


def test_browser_engine(body=None):
    t0 = time.time()
    try:
        r = bridge("/browser/status", {})
        if not r or not isinstance(r, dict) or r.get("error"):
            cfg = runtime_settings.get()
            obs_path = cfg.get("obscura_path", "/usr/local/bin/obscura")
            res = subprocess.run([obs_path, "-V"], capture_output=True, text=True, timeout=2)
            obs_ok = res.returncode == 0
            ver = res.stdout.strip() if obs_ok else ""
            r = {
                "active_engine": "obscura" if obs_ok else "none",
                "obscura": {"available": obs_ok, "version": ver, "path": obs_path, "memory": "~30MB V8 DOM"}
            }

        target_url = (body or {}).get("url") or "https://example.com"
        test_res = bridge("/browser", {"args": ["fetch", target_url, "--dump", "text", "--timeout", "10"]})
        latency = round((time.time() - t0) * 1000)
        out = test_res.get("output", "") or test_res.get("stdout", "")
        if test_res.get("exit_code") == 0 or "Example Domain" in out or "Fetching" in out:
            return {"ok": True, "latency_ms": latency, "status": r, "message": f"Engine {r.get('active_engine', 'obscura')} responded in {latency}ms"}
        else:
            return {"ok": False, "latency_ms": latency, "status": r, "error": test_res.get("stderr") or test_res.get("error") or "Test failed"}
    except Exception as ex:
        latency = round((time.time() - t0) * 1000)
        return {"ok": False, "latency_ms": latency, "error": str(ex)}

SESSIONS = HERE / "sessions"
SESSIONS.mkdir(exist_ok=True)
MAX_EVENTS = 4000
MAX_HISTORY = 3000
# Agent/tool events kept for the whole conversation so a page reload can rebuild the work cards and Activity log
# (raw token/thinking events are only kept for the most recent part of the stream).
HISTORY_TYPES = {"screenshot", "auto_continue", "fanout", "model_call", "budget", "memory", "approval_request", "approval_done", "rate_limit", "context",
                 "turn_start", "turn_end", "agent_start", "agent_end", "tool_start", "tool_end", "retry", "parallel_run", "task_state", "request_state"}
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
        self.summaries = {}                      # folded-history summaries by prefix hash (token diet)
        self.touched, self.streams = time.time(), 0
        self.auto_count, self._auto_token = 0, None    # automatic continues in a row / pending countdown
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
        s.summaries = d.get("summaries") or {}
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
                    "project": self.project, "running": self.running,
                    "summaries": dict(list(self.summaries.items())[-20:])}
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
            due = ev["type"] in ("turn_start", "turn_end", "tool_end", "run_state", "parallel_run", "task_state") or time.monotonic() - self._saved_at >= 1
            if due:
                self._saved_at = time.monotonic()
        if due:
            self.save()
        return ev

    def run(self, text, project="", images=None):
        self.running = True
        self.project = project
        if self.title == "New session":
            self.title = text.strip().splitlines()[0][:60]
        self.messages.append({"role": "user", "content": text, "t": time.time(), **({"images": images} if images else {})})
        self.emit({"type": "turn_start", "text": text, **({"images": images} if images else {})})
        try:
            turn = sum(1 for m in self.messages if m["role"] == "user")
            trace = telemetry.Trace(SESSIONS / self.id, session=self.id, project=project,
                                    usage_file=SESSIONS / "_usage.jsonl", turn=turn)
            with CONFIG_LOCK:
                self.engine = engine.Engine(self.emit, project=project, trace=trace,
                                            approvals=lambda data, stop: ops.request_approval(self, data, stop),
                                            history_cache=self.summaries)
            if self.stop_requested.is_set():
                self.engine.stop.set()
            if self.pause_requested.is_set():
                self.engine.pause_requested.set()
            history = [{"role": m["role"], "content": m["content"] + (f"\n[{len(m['images'])} image(s) were attached]"
                                                                      if m.get("images") else "")} for m in self.messages[:-1]]
            outcome = "ok"
            paths = [str(media.upload_path(SESSIONS, i)) for i in (images or [])]
            reply = self.engine.respond(text, history, images=paths) if paths else self.engine.respond(text, history)
            if reply.startswith("Reached the limit of"):
                outcome = "limit"
            self.messages.append({"role": "assistant", "content": reply, "t": time.time()})
            self.emit({"type": "turn_end", "text": reply, "usage": trace.snapshot()})
            if project and outcome == "ok" and runtime_settings.get().get("auto_screenshot", True):
                threading.Thread(target=self._finished_screenshot, args=(project, len(self.messages) - 1), daemon=True).start()
        except engine.Stopped:
            outcome = "stopped"
            self.messages.append({"role": "assistant", "content": "⏹ Stopped. Say *continue* to resume.", "t": time.time()})
            self.emit({"type": "turn_end", "text": "⏹ Stopped. Say continue to resume.", "stopped": True})
        except Exception as e:
            outcome = "transient" if _transient(e) else "error"
            msg = f"⚠️ {type(e).__name__}: {e}\n\nSay *continue* to resume from the last checkpoint."
            self.messages.append({"role": "assistant", "content": msg, "t": time.time()})
            self.emit({"type": "turn_end", "text": msg, "error": True})
        finally:
            with self.cond:
                self.running = False
                self.save()
                self.cond.notify_all()
            try:
                self._maybe_auto_continue(locals().get("outcome", "error"))
            except Exception as e:  # noqa: BLE001 - scheduling must never break the run thread
                print(f"[kryzen] auto-continue: {type(e).__name__}: {e}", flush=True)

    def _maybe_auto_continue(self, outcome):
        """After a step limit or a temporary failure, continue the project by itself (bounded, cancellable)."""
        if outcome == "ok":
            self.auto_count = 0
            return
        settings = runtime_settings.get()
        if outcome not in ("limit", "transient") or not settings.get("auto_continue") or not self.project:
            return
        limit = int(settings.get("auto_continue_max", 3))
        if self.auto_count >= limit:
            self.emit({"type": "auto_continue", "state": "exhausted", "attempt": self.auto_count, "max": limit})
            return
        self.auto_count += 1
        delay = 20 if outcome == "limit" else 60
        token = self._auto_token = object()
        self.emit({"type": "auto_continue", "state": "scheduled", "in": delay, "attempt": self.auto_count, "max": limit,
                   "reason": "step limit reached" if outcome == "limit" else "temporary failure"})

        def fire():
            if self._auto_token is not token:
                return
            self._auto_token = None
            with START_LOCK:
                if self.running:
                    return
                code, body = start_turn(self, f"Continue project {self.project} from its saved checkpoint.",
                                        self.project, auto=True)
            if code != 200:
                self.emit({"type": "auto_continue", "state": "failed", "error": body.get("error", "")})
        t = threading.Timer(delay, fire)
        t.daemon = True
        t.start()

    def _finished_screenshot(self, project, msg_index):
        """After a project run finishes, capture its running preview (if any) and attach it to the reply."""
        try:
            url = self.preview_url if getattr(self, "preview_url", "") else find_preview(project)
            if not url:
                return
            root = codetools._root(project)
            path = media.screenshot(bridge, root, url, "finished", meta={"kind": "finished", "session": self.id})
            with self.cond:
                if msg_index < len(self.messages):
                    self.messages[msg_index].setdefault("shots", []).append({"slug": project, "path": path, "url": url})
            self.emit({"type": "screenshot", "kind": "finished", "slug": project, "path": path, "url": url})
            self.save()
        except Exception as e:  # noqa: BLE001 - a screenshot is a bonus, never a failure
            print(f"[kryzen] finished screenshot: {type(e).__name__}: {e}", flush=True)

    def cancel_auto_continue(self):
        had = self._auto_token is not None
        self._auto_token = None
        if had:
            self.emit({"type": "auto_continue", "state": "cancelled"})
        return had


def find_preview(project):
    """A reachable local dev server started by this project's background jobs (newest first)."""
    import urllib.request
    root = codetools._root(project)
    jobs = [j for j in (bridge("/jobs/list", {}).get("jobs") or [])
            if j.get("running") and str(j.get("cwd", "")).startswith(root)]
    for j in sorted(jobs, key=lambda j: j.get("started", 0), reverse=True)[:6]:
        out = bridge("/jobs/get", {"id": j["id"], "tail": 20000})
        for url in reversed(media.preview_urls(str(out.get("output") or ""))):
            try:
                with urllib.request.urlopen(url, timeout=3) as r:
                    if r.status < 500:
                        return url
            except Exception:  # noqa: BLE001
                continue
    return ""


def _transient(e):
    """Failures worth retrying automatically (network, rate limits, provider hiccups) — not auth or bad input."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (408, 409, 425, 429, 500, 502, 503, 504)
    if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, engine.IncompleteStream, engine.OutputLimit)):
        return True
    text = str(e)
    return any(k in text for k in ("model call failed after retries", "empty response", "timed out",
                                   "Connection reset", "Remote end closed"))


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
            LIVE[sid].touched = time.time()
            return LIVE[sid]
        if sid and (SESSIONS / f"{sid}.json").exists():
            LIVE[sid] = Session.load(sid)
            return LIVE[sid]
        if create and not sid:
            s = Session()
            LIVE[s.id] = s
            return s
    return None


IDLE_EVICT = 15 * 60
QUEUE, QUEUE_LOCK = [], threading.Lock()


def evict_idle():
    """Free memory: drop idle sessions (saved on disk, reloaded on demand)."""
    now = time.time()
    with LIVE_LOCK:
        for sid, s in list(LIVE.items()):
            if not s.running and s.streams == 0 and now - s.touched > IDLE_EVICT:
                del LIVE[sid]


def start_turn(s, text, project, auto=False, images=None):
    """Start a run in session s. Returns (code, body). Caller holds START_LOCK."""
    if not auto:
        # A message from the user replaces any pending automatic continue and resets the streak.
        s._auto_token, s.auto_count = None, 0
    with s.cond:
        if s.running:
            return 409, {"error": "a turn is already running", "id": s.id}
        if s.project and project and s.project != project:
            return 409, {"error": "start a new session for a different project", "project_mismatch": True}
        project = project or s.project
        other = next((run for run in list(LIVE.values()) if run is not s and run.running and project and run.project == project), None)
        if other:
            return 409, {"error": "this project already has an active run; open its chat to pause, resume or stop it",
                         "active_session": other.id}
        s.stop_requested.clear()
        s.pause_requested.clear()
        s.engine = None
        s.running = True
        s.project = project
        start = s.next_seq
    threading.Thread(target=s.run, args=(text, project, images), daemon=True).start()
    return 200, {"id": s.id, "from_seq": start, "project": project}


def enqueue(text, project, sid, images=None):
    item = {"qid": uuid.uuid4().hex[:10], "text": text, "project": project, "session": sid, "t": time.time(),
            "images": images or []}
    with QUEUE_LOCK:
        if len(QUEUE) >= 50:
            raise ValueError("the run queue is full")
        QUEUE.append(item)
    return item


def dispatch_queue():
    """Start queued runs as soon as their session and project are free (FIFO, skipping blocked items)."""
    with QUEUE_LOCK:
        items = list(QUEUE)
    for item in items:
        with START_LOCK:
            try:
                s = get_session(item["session"], create=not item["session"])
            except ValueError:
                s = None
            if s is None:
                with QUEUE_LOCK:
                    QUEUE.remove(item) if item in QUEUE else None
                continue
            busy = s.running or any(r.running and item["project"] and r.project == item["project"]
                                    for r in list(LIVE.values()) if r is not s)
            if busy:
                continue
            code, body = start_turn(s, item["text"], item["project"], images=item.get("images") or None)
            if code == 200 or body.get("project_mismatch"):
                with QUEUE_LOCK:
                    if item in QUEUE:
                        QUEUE.remove(item)
                if code == 200:
                    s.emit({"type": "queue_started", "qid": item["qid"]})


def housekeeping():
    while True:
        time.sleep(1)
        try:
            dispatch_queue()
            if int(time.time()) % 60 == 0:
                evict_idle()
        except Exception as e:  # noqa: BLE001 - never let the maintenance loop die
            print(f"[kryzen] housekeeping: {type(e).__name__}: {e}", flush=True)


def dashboard():
    sessions = []
    for s in list(LIVE.values()):
        if s.running:
            e = s.engine
            sessions.append({"id": s.id, "title": s.title, "project": s.project,
                             "paused": bool(e and e.paused.is_set()),
                             "usage": e.trace.snapshot() if e and e.trace else None,
                             "budget": e.budget.state(e.tokens_used()) if e else None,
                             "lanes": _lanes(s)})
    with QUEUE_LOCK:
        queue = [{k: i[k] for k in ("qid", "project", "session", "t")} | {"text": i["text"][:160]} for i in QUEUE]
    recent = []
    for f in sorted(SESSIONS.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:8]:
        try:
            d = json.loads(f.read_text())
            last = next((m for m in reversed(d.get("messages", [])) if m["role"] == "assistant"), None)
            recent.append({"id": d["id"], "title": d.get("title", ""), "project": d.get("project", ""),
                           "t": f.stat().st_mtime, "last": (last or {}).get("content", "")[:200],
                           "error": bool(last and str(last.get("content", "")).startswith("⚠️"))})
        except (OSError, ValueError, KeyError):
            pass
    return {"running": sessions, "queue": queue, "recent": recent, "approvals": ops.pending_approvals(),
            "gate": REQUESTS.snapshot(), "usage": telemetry.usage_summary(SESSIONS / "_usage.jsonl"),
            "projects": ops.projects_overview(bridge, studio.plan_get), "settings": runtime_settings.get()}


def _lanes(s):
    lanes = {}
    for ev in s.history[-400:]:
        if ev.get("type") == "task_state":
            lanes[ev.get("task_id")] = {"id": ev.get("id"), "task_id": ev.get("task_id"), "agent": ev.get("agent"),
                                        "state": ev.get("state")}
    return list(lanes.values())[-24:]


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
                # Opened as an unknown alias: move to the real address.
                if not is_local_host(self.headers.get("Host", "")):
                    self.send_response(302)
                    self.send_header("Location", f"http://{HOST}:{PORT}{self.path}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/favicon.ico":
                return self.send(204, b"", "image/x-icon")
            if u.path.startswith("/assets/"):
                asset_path = HERE / u.path[1:]
                if asset_path.is_file():
                    ext = asset_path.suffix.lower()
                    mimes = {
                        ".js": "text/javascript; charset=utf-8",
                        ".css": "text/css; charset=utf-8",
                        ".svg": "image/svg+xml",
                        ".json": "application/json; charset=utf-8",
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".woff2": "font/woff2"
                    }
                    return self.send(200, asset_path.read_bytes(), mimes.get(ext, "application/octet-stream"))
                return self.send(404, {"error": "asset not found"})
            if u.path.startswith("/ui/"):
                name = u.path[4:]
                if not re.fullmatch(r"[a-z0-9-]+\.(js|css)", name) or not (HERE / "ui" / name).is_file():
                    return self.send(404, {"error": "not found"})
                return self.send(200, (HERE / "ui" / name).read_bytes(),
                                 "text/javascript; charset=utf-8" if name.endswith(".js") else "text/css; charset=utf-8")
            if u.path == "/health":
                return self.send(200, {"ok": True, "active_runs": sum(s.running for s in list(LIVE.values()))})
            if u.path == "/api/ax/status":
                import shutil
                import subprocess
                ax_bin = shutil.which("ax") or str(Path.home() / ".local/bin/ax")
                ax_exists = Path(ax_bin).exists()
                ver_str = "not found"
                if ax_exists:
                    try:
                        res = subprocess.run([ax_bin, "version"], capture_output=True, text=True, timeout=2)
                        ver_str = res.stdout.strip() if res.returncode == 0 else "installed"
                    except Exception as ex:
                        ver_str = str(ex)
                return self.send(200, {"available": ax_exists, "version": ver_str, "bin": ax_bin})
            if u.path in ("/studio.js", "/panel-resize.js", "/execution.js"):
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
            if u.path == "/api/execution":
                slug=q.get("slug", "")
                studio._project(bridge,slug)
                result=codetools.read(bridge,slug,".devpilot/execution.json")
                if result.get('error'):
                    if 'no such file' in str(result['error']).lower() or 'filenotfound' in str(result['error']).lower():
                        data={'tasks':{},'runs':[]}
                    else:return self.send(400,{'error':result['error']})
                else:data=json.loads(result['content'])
                tasks={key:{k:v for k,v in task.items() if k in ('id','agent','task','state','files','reads','depends_on','started','finished','updated','result','error','checkpoint')} for key,task in data.get('tasks',{}).items()}
                for task in tasks.values():
                    task['result']=str(task.get('result',''))[:1800]
                    if task.get('state')=='running' and not any(s.running and s.project==slug for s in list(LIVE.values())):
                        task['state']='interrupted'
                runs=data.get('runs',[])[-10:]
                if not any(s.running and s.project==slug for s in list(LIVE.values())):
                    for run in runs:
                        if run.get('state')=='running':
                            run['state']='interrupted'
                            for node in run.get('nodes',[]):
                                if node.get('state')=='running':node['state']='interrupted'
                return self.send(200,{'slug':slug,'tasks':tasks,'runs':runs,'requests':engine.REQUESTS.snapshot()})
            if u.path == "/api/image":
                path = media.upload_path(SESSIONS, q.get("id", ""))
                return self.send(200, path.read_bytes(), media.EXTS.get(path.suffix, "image/png"))
            if u.path == "/api/project-image":
                slug = q.get("slug", "")
                studio._project(bridge, slug)
                path = media.project_image(codetools._root(slug), q.get("path", ""))
                return self.send(200, path.read_bytes(), media.EXTS[path.suffix.lower()])
            if u.path == "/api/screenshots":
                slug = q.get("slug", "")
                studio._project(bridge, slug)
                return self.send(200, {"slug": slug, "shots": media.list_shots(codetools._root(slug))})
            if u.path == "/api/trace":
                s = get_session(q.get("id"))
                if not s:
                    return self.send(404, {"error": "no such session"})
                turn = int(q["turn"]) if q.get("turn", "").isdigit() else None
                return self.send(200, {"spans": telemetry.read_trace(SESSIONS / s.id, turn, int(q.get("since", 0) or 0)),
                                       "turns": sum(1 for m in s.messages if m["role"] == "user")})
            if u.path == "/api/blob":
                if not SESSION_ID.fullmatch(q.get("id", "")):
                    return self.send(400, {"error": "invalid session id"})
                try:
                    text = telemetry.read_blob(SESSIONS / q["id"], q.get("sha", ""))
                except FileNotFoundError:
                    text = telemetry.find_blob(SESSIONS, q.get("sha", ""))
                return self.send(200, text.encode(), "text/plain; charset=utf-8")
            if u.path == "/api/dashboard":
                return self.send(200, dashboard())
            if u.path == "/api/health/deep":
                return self.send(200, {**ops.deep_health(q.get("force") == "1")})
            if u.path == "/api/approvals":
                return self.send(200, {"approvals": ops.pending_approvals(include_diff=q.get("diff") == "1")})
            if u.path == "/api/network/status":
                return self.send(200, get_network_status())
            if u.path == "/api/browser/status":
                r = bridge("/browser/status", {})
                return self.send(200, r if isinstance(r, dict) and not r.get("error") else {"ok": False, "error": str(r)})
            if u.path == "/api/settings/runtime":
                return self.send(200, {"settings": runtime_settings.get(mask_secrets=True), "defaults": runtime_settings.DEFAULTS,
                                       "limits": runtime_settings.LIMITS})
            if u.path == "/api/queue":
                with QUEUE_LOCK:
                    return self.send(200, {"queue": [dict(i) for i in QUEUE]})
            if u.path == "/api/memory":
                slug = q.get("slug", "")
                studio._project(bridge, slug)
                root = codetools._root(slug)
                value = bridge("/fs/read", {"path": root + "/.devpilot/memory.md", "raw": True})
                return self.send(200, {"slug": slug, "exists": not value.get("error"),
                                       "content": value.get("content", ""), "revision": value.get("revision")})
            if u.path.startswith("/api/skills2/"):
                act = u.path.rsplit("/", 1)[1]
                if act == "insights":
                    return self.send(200, skills2.insights(SESSIONS, forms.skills_get()["skills"]))
                if act == "versions":
                    return self.send(200, {"versions": skills2.versions(q.get("name", ""))})
                if act == "version":
                    return self.send(200, {"text": skills2.version_get(q.get("name", ""), q.get("stamp", ""))})
                if act == "importable":
                    return self.send(200, skills2.importable())
                return self.send(404, {"error": "unknown skills action"})
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
            if u.path == "/api/mesh/gates":
                return self.send(200, {"ok": True, "gates": mesh.get_gates()})
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
            if u.path == "/api/project/folders":
                return self.send(200, bridge("/project/folders", {"path": q.get("path", "")}))
            if u.path == "/api/project":
                return self.send(200, bridge("/project/resume", {"slug": q.get("slug", "")}))
            if u.path == "/api/project/references":
                return self.send(200, project_logic.get_project_references(q.get("slug", "")))
            if u.path == "/api/vibe/config":
                slug = q.get("slug", "")
                return self.send(200, {"ok": True, "config": codetools.vibe_config_get(slug)})
            if u.path == "/api/vibe/checkpoints":
                slug = q.get("slug", "")
                return self.send(200, codetools.vibe_checkpoints(bridge, slug))
            if u.path == "/api/tree":
                return self.send(200, bridge("/fs/list", {"path": q.get("path", ""), "depth": int(q.get("depth", 3))}))
            if u.path == "/api/file":
                return self.send(200, bridge("/fs/read", {"path": q["path"], "limit": 2000}))
            if u.path == "/api/isolated/list":
                return self.send(200, codetools.list_isolated_box(q.get("slug", ""), q.get("box_id", "default")))
            if u.path == "/api/git/branch/status":
                return self.send(200, codetools.get_branch_change_status(q.get("slug", "")))
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
        s.streams += 1
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
        finally:
            s.streams -= 1
            s.touched = time.time()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Jarvis")
        self.end_headers()

    def do_POST(self):
        try:
            u = urlparse(self.path).path
            if u == "/v1/chat/completions":
                self.handle_openai_proxy()
                return
            if u == "/mcp":
                self.handle_mcp()
                return
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

    def handle_openai_proxy(self):
        """POST /v1/chat/completions: OpenAI Proxy Route to K.R.Y.Z.E.N specialist agents."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception as e:
            return self.send(400, {"error": {"message": f"Invalid JSON body: {e}", "type": "invalid_request_error"}})

        model_name = str(body.get("model") or "kryzen/orchestrator")
        target_name = model_name.split("/", 1)[1] if "/" in model_name else model_name
        target_slug = target_name.lower().replace("-", " ").replace("_", " ").strip()

        all_agents = engine.load_agents()
        selected_agent = None
        for a in all_agents.values():
            if a.name.lower() == target_slug or a.name.lower().startswith(target_slug) or target_slug in a.name.lower():
                selected_agent = a
                break
        if not selected_agent:
            selected_agent = all_agents.get(engine.ORCHESTRATOR) or list(all_agents.values())[0]

        messages = body.get("messages") or []
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content") or ""
                break
        if not user_text and messages:
            user_text = str(messages[-1].get("content") or "")

        stream = bool(body.get("stream", False))
        req_id = "chatcmpl-" + uuid.uuid4().hex[:12]
        created = int(time.time())

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            def emit_token(tok):
                chunk = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_name,
                    "choices": [{"index": 0, "delta": {"content": tok}, "finish_reason": None}]
                }
                self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()

            eng = engine.Engine(emit=lambda ev: emit_token(ev.get("text", "")) if ev.get("type") == "token" else None)
            reply = eng.run_agent(selected_agent, user_text, messages[:-1] if len(messages) > 1 else [])

            done_chunk = {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_name,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            }
            self.wfile.write(f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\ndata: [DONE]\n\n".encode("utf-8"))
            self.wfile.flush()
        else:
            eng = engine.Engine(emit=lambda ev: None)
            reply = eng.run_agent(selected_agent, user_text, messages[:-1] if len(messages) > 1 else [])
            resp = {
                "id": req_id,
                "object": "chat.completion",
                "created": created,
                "model": model_name,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": len(user_text) // 4, "completion_tokens": len(reply) // 4, "total_tokens": (len(user_text) + len(reply)) // 4}
            }
            self.send(200, resp)

    def handle_mcp(self):
        """POST /mcp: Model Context Protocol (MCP) JSON-RPC 2.0 endpoint."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
            rpc = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception as e:
            return self.send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}})

        req_id = rpc.get("id")
        method = rpc.get("method")
        params = rpc.get("params") or {}

        if method == "initialize":
            res = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "kryzen-mcp", "version": "1.0.0"},
                "capabilities": {"tools": {}}
            }
            return self.send(200, {"jsonrpc": "2.0", "id": req_id, "result": res})

        elif method == "tools/list":
            tools = [
                {
                    "name": "kryzen_delegate",
                    "description": "Delegate a task to a specialized K.R.Y.Z.E.N agent (product, architect, design, build, qa, devops, etc.)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "agent": {"type": "string", "description": "Agent name or role, e.g. 'Build Agent' or 'build'"},
                            "task": {"type": "string", "description": "Specific task instruction"},
                            "project": {"type": "string", "description": "Project slug (optional)"}
                        },
                        "required": ["agent", "task"]
                    }
                },
                {
                    "name": "kryzen_project_memory",
                    "description": "Query or record facts into K.R.Y.Z.E.N durable project memory",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["recall", "remember"]},
                            "query": {"type": "string", "description": "Search query for recall"},
                            "fact": {"type": "string", "description": "Fact to record for remember"},
                            "project": {"type": "string", "description": "Project slug (optional)"}
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "kryzen_skills",
                    "description": "List or read installed K.R.Y.Z.E.N engineering and design skills",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["list", "read"]},
                            "name": {"type": "string", "description": "Skill name for read action"}
                        },
                        "required": ["action"]
                    }
                }
            ]
            return self.send(200, {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})

        elif method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments") or {}
            out_text = ""
            try:
                if tool_name == "kryzen_delegate":
                    t_agent = args.get("agent", "build")
                    t_task = args.get("task", "")
                    all_agents = engine.load_agents()
                    target = None
                    for a in all_agents.values():
                        if t_agent.lower() in a.name.lower():
                            target = a
                            break
                    if not target:
                        target = list(all_agents.values())[0]
                    eng = engine.Engine(emit=lambda ev: None, project=args.get("project", ""))
                    out_text = eng.run_agent(target, t_task, [])

                elif tool_name == "kryzen_project_memory":
                    action = args.get("action")
                    if action == "remember":
                        fact = args.get("fact", "")
                        out_text = f"Stored memory fact: {fact}"
                    else:
                        query = args.get("query", "")
                        out_text = json.dumps(brain.recall(query, k=5), ensure_ascii=False)

                elif tool_name == "kryzen_skills":
                    action = args.get("action")
                    if action == "read":
                        sname = args.get("name", "")
                        out_text = json.dumps(bridge("/skills/read", {"name": sname}), ensure_ascii=False)
                    else:
                        out_text = json.dumps(bridge("/skills/list", {}), ensure_ascii=False)
                else:
                    return self.send(404, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}})

                return self.send(200, {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": str(out_text)}]}
                })
            except Exception as e:
                return self.send(200, {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
                })
        else:
            return self.send(404, {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})


    def post(self):
        origin = self.headers.get("Origin", "")
        if self.headers.get("X-Jarvis") != "1" or not is_local_origin(origin):
            print(f"[jarvis] refused POST {self.path}: origin={origin!r} x-jarvis={self.headers.get('X-Jarvis')!r}",
                  flush=True)
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
        if u == "/api/upload-image":
            try:
                if body.get("slug"):
                    studio._project(bridge, str(body["slug"]))
                    data = media.project_image(codetools._root(str(body["slug"])), str(body.get("path", ""))).read_bytes()
                else:
                    data = media.decode_data_url(body.get("data", ""))
                return self.send(200, {"ok": True, **media.save_upload(SESSIONS, data)})
            except (ValueError, PermissionError, FileNotFoundError) as e:
                return self.send(200, {"ok": False, "error": str(e)})
        if u == "/api/screenshot":
            slug, url = str(body.get("slug", "")), str(body.get("url", ""))
            try:
                studio._project(bridge, slug)
                root = codetools._root(slug)
                path = media.screenshot(bridge, root, url, str(body.get("label") or "preview"),
                                        meta={"kind": "manual"})
                up = media.save_upload(SESSIONS, (Path(root) / path).read_bytes())
                return self.send(200, {"ok": True, "path": path, "slug": slug, **up})
            except (ValueError, RuntimeError, PermissionError, FileNotFoundError) as e:
                return self.send(200, {"ok": False, "error": str(e)})
        if u == "/api/auto-continue/cancel":
            s = get_session(body.get("id"))
            return self.send(200, {"ok": bool(s and s.cancel_auto_continue())})
        if u == "/api/approval":
            return self.send(200, ops.resolve_approval(str(body.get("id", "")), body.get("approved") is True,
                                                       body.get("note", "")))
        if u == "/api/settings/runtime":
            result = runtime_settings.save(body.get("settings", {}))
            if result.get("ok"):
                REQUESTS.configure(result["settings"]["max_concurrency"])
            return self.send(200, result)
        if u == "/api/models/test":
            return self.send(200, test_model_provider(body))
        if u == "/api/browser/test":
            return self.send(200, test_browser_engine(body))
        if u == "/api/network/tailscale/action":
            return self.send(200, tailscale_action(body.get("action", ""), body.get("args")))
        if u == "/api/project/test":
            return self.send(200, project_logic.run_project_tests(str(body.get("slug", "")), str(body.get("framework", "auto"))))
        if u in ("/api/project/remove", "/api/project/rename"):
            if any(x.running for x in list(LIVE.values())):
                return self.send(409, {"error": "Finish or stop the current run first."})
            if u.endswith("remove"):
                return self.send(200, bridge("/project/remove", {"slug": str(body.get("slug", ""))}))
            old, new = str(body.get("slug", "")), str(body.get("name", "")).strip()
            result = bridge("/project/rename", {"slug": old, "name": new})
            if result.get("ok"):
                for live in list(LIVE.values()):
                    if live.project == old:
                        live.project = new
                for f in SESSIONS.glob("*.json"):
                    try:
                        raw = f.read_text()
                        if f'"project": {json.dumps(old)}' not in raw and f'"project":{json.dumps(old)}' not in raw:
                            continue
                        data = json.loads(raw)
                        if data.get("project") == old:
                            stamp = f.stat()
                            data["project"] = new
                            tmp = f.with_suffix(".tmp")
                            tmp.write_text(json.dumps(data, ensure_ascii=False))
                            tmp.replace(f)
                            os.utime(f, (stamp.st_atime, stamp.st_mtime))
                    except (OSError, ValueError):
                        pass
            return self.send(200, result)
        if u == "/api/project/link":
            return self.send(200, bridge("/project/link", {"path": str(body.get("path", ""))}))
        if u == "/api/project/create":
            return self.send(200, project_logic.create_project(str(body.get("slug", "")),
                                                               str(body.get("title", "")),
                                                               str(body.get("goal", "")),
                                                               str(body.get("template", "node"))))
        if u == "/api/project/reference/save":
            return self.send(200, project_logic.save_project_reference(str(body.get("slug", "")), str(body.get("title", "")),
                                                                      str(body.get("url", "")), str(body.get("category", "General"))))
        if u == "/api/code/slash":
            slug = str(body.get("slug", ""))
            cmd = str(body.get("command", "/goal"))
            prompt = str(body.get("prompt", ""))
            formatted = project_logic.format_slash_prompt(cmd, prompt, slug)
            return self.send(200, codetools.agy(bridge, slug, formatted, mode=body.get("mode", "auto"),
                                                effort=str(body.get("effort", "high")), background=True))
        if u == "/api/queue/cancel":
            with QUEUE_LOCK:
                before = len(QUEUE)
                QUEUE[:] = [i for i in QUEUE if i["qid"] != body.get("qid")]
                return self.send(200, {"ok": len(QUEUE) < before})
        if u == "/api/isolated/create":
            return self.send(200, codetools.create_isolated_box(str(body.get("slug", "")), str(body.get("box_id", "default"))))
        if u == "/api/isolated/merge":
            return self.send(200, codetools.merge_isolated_box(str(body.get("slug", "")), str(body.get("box_id", "default")),
                                                               discard_on_success=body.get("discard_on_success", True)))
        if u == "/api/isolated/discard":
            return self.send(200, codetools.discard_isolated_box(str(body.get("slug", "")), str(body.get("box_id", "default"))))
        if u == "/api/git/branch/create":
            return self.send(200, codetools.create_change_branch(str(body.get("slug", "")), body.get("branch")))
        if u == "/api/git/branch/commit":
            return self.send(200, codetools.commit_change_branch(str(body.get("slug", "")), str(body.get("message", "agent change"))))
        if u == "/api/git/branch/merge":
            return self.send(200, codetools.merge_change_branch(str(body.get("slug", "")), body.get("branch"), approve=bool(body.get("approve", True))))
        if u == "/api/lane":
            s = get_session(body.get("id"))
            if not s or not s.running or not s.engine:
                return self.send(409, {"ok": False, "error": "no active run"})
            task_id = str(body.get("task_id", ""))
            if body.get("action") != "cancel" or not task_id:
                return self.send(400, {"ok": False, "error": "action must be cancel with a task_id"})
            s.engine.cancelled_tasks.add(task_id)
            s.emit({"type": "lane_cancel", "task_id": task_id})
            return self.send(200, {"ok": True})
        if u == "/api/memory":
            slug = str(body.get("slug", ""))
            studio._project(bridge, slug)
            root = codetools._root(slug)
            args = {"path": root + "/.devpilot/memory.md", "content": str(body.get("content", ""))[:400000]}
            if body.get("revision"):
                args["expected_revision"] = body["revision"]
            else:
                args["create_only"] = True
            result = bridge("/fs/write", args)
            return self.send(200, {"ok": not result.get("error"), "error": result.get("error"),
                                   "revision": result.get("revision")})
        if u.startswith("/api/skills2/"):
            act = u.rsplit("/", 1)[1]
            try:
                with CONFIG_LOCK:
                    if act == "rollback":
                        return self.send(200, skills2.rollback(body.get("name", ""), body.get("stamp", "")))
                    if act == "import":
                        return self.send(200, skills2.import_skill(body.get("source", ""), body.get("name") or None))
                    if act == "test":
                        return self.send(200, skills2.set_test(body.get("name", ""), body.get("prompt", "")))
                    if act == "discard-draft":
                        return self.send(200, skills2.discard_draft(body.get("name", "")))
                    if act == "approve-draft":
                        d = next((x for x in skills2.drafts() if x["name"] == body.get("name")), None)
                        if not d:
                            return self.send(404, {"ok": False, "errors": ["draft not found"]})
                        result = forms.skill_save({"name": d["name"], "description": d["description"], "body": d["body"]})
                        if result.get("ok"):
                            skills2.discard_draft(d["name"])
                        return self.send(200, result)
                if act == "draft":
                    s = get_session(body.get("id"))
                    if not s:
                        return self.send(404, {"ok": False, "errors": ["no such session"]})
                    turn = int(body.get("turn") or sum(1 for m in s.messages if m["role"] == "user"))
                    spans = telemetry.read_trace(SESSIONS / s.id, turn)
                    if not spans:
                        return self.send(200, {"ok": False, "errors": ["this turn has no recorded trace yet"]})
                    reply = next((m["content"] for m in reversed(s.messages) if m["role"] == "assistant"), "")
                    helper = engine.Engine.__new__(engine.Engine)
                    helper.settings = runtime_settings.get()
                    helper.agents = {engine.ORCHESTRATOR: engine.AgentSpec(engine.ORCHESTRATOR,
                                     "agy/gemini-3.8-flash", "", 1, [])}
                    raw = helper.quick(skills2.DRAFT_PROMPT + "\n\nRUN:\n" + skills2.run_digest(spans, reply),
                                       max_tokens=1600, label="skill draft")
                    return self.send(200, {"ok": True, "draft": skills2.save_draft(raw)})
            except (ValueError, FileNotFoundError, RuntimeError) as e:
                return self.send(200, {"ok": False, "errors": [str(e)]})
            return self.send(404, {"error": "unknown skills action"})
        if u == "/api/run-control":
            s = get_session(body.get("id"))
            if not s or not s.running:
                return self.send(409, studio.fail("no active run to control"))
            action = body.get("action")
            if action not in ("pause", "resume", "hold"):
                return self.send(400, studio.fail("action must be pause, resume or hold"))
            if action == "hold":
                if s.engine:
                    s.engine.hold_auto_resume()
                return self.send(200, {"ok": True, "state": "held"})
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
            images = body.get("images") or []
            if not isinstance(images, list) or len(images) > 6 or any(not media.IMAGE_ID.fullmatch(str(i)) for i in images):
                return self.send(400, {"error": "attach up to 6 uploaded images"})
            for i in images:
                media.upload_path(SESSIONS, i)
            if isinstance(body.get("preview"), str) and media.URL.fullmatch(body["preview"]):
                s.preview_url = body["preview"]
            code, result = start_turn(s, text, project, images=images or None)
            if code == 409 and body.get("queue") and not result.get("project_mismatch"):
                item = enqueue(text, project or s.project, s.id, images)
                return self.send(200, {"queued": True, "qid": item["qid"], "id": s.id, "position": len(QUEUE)})
            return self.send(code, result)
        if u.startswith("/api/mesh/"):
            if u == "/api/mesh/gate":
                return self.send(200, mesh.set_gate(body.get("stage"), body.get("locked")))
            action = {"save": mesh.save, "create": mesh.create, "archive": mesh.archive}.get(u.rsplit("/", 1)[1])
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
                if act == "agy":
                    return self.send(200, codetools.agy(bridge, slug, str(body.get("prompt", "")),
                                                        mode=body.get("mode", "auto"),
                                                        model=str(body.get("model", "")),
                                                        effort=str(body.get("effort", "high")),
                                                        background=body.get("background", True)))
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
        if u.startswith("/api/vibe/"):
            act = u.rsplit("/", 1)[1]
            slug = str(body.get("slug", ""))
            try:
                if act == "config":
                    saved = codetools.vibe_config_save(slug, body.get("config", {}))
                    return self.send(200, {"ok": True, "config": saved})
                if act == "checkpoint":
                    return self.send(200, codetools.vibe_checkpoint(bridge, slug, body.get("label", "vibe")))
                if act == "rollback":
                    return self.send(200, codetools.vibe_rollback(bridge, slug, body.get("checkpoint_id", "")))
                if act == "clone":
                    img_id = body.get("image_id", "")
                    data = None
                    if img_id:
                        data = media.upload_path(SESSIONS, img_id).read_bytes()
                    tokens = media.extract_vibe_tokens(data, body.get("aesthetic", "Swiss Grid"))
                    css = media.generate_vibe_tokens_css(tokens)
                    root = codetools._root(slug)
                    bridge("/fs/write", {"path": f"{root}/vibe-tokens.css", "content": css})
                    src_dir = Path(root) / "src"
                    if src_dir.exists():
                        bridge("/fs/write", {"path": f"{root}/src/vibe-tokens.css", "content": css})
                    return self.send(200, {"ok": True, "tokens": tokens, "css": css})
                if act == "patch":
                    selector = body.get("selector", "")
                    prompt = body.get("prompt", "")
                    styles = body.get("styles", {})
                    file_hint = body.get("file", "")
                    # Auto checkpoint before patch
                    codetools.vibe_checkpoint(bridge, slug, f"pre-patch: {selector}")
                    all_agents = engine.load_agents()
                    build_agent = None
                    for a in all_agents.values():
                        if "build" in a.name.lower() or "engineer" in a.name.lower():
                            build_agent = a
                            break
                    if not build_agent:
                        build_agent = list(all_agents.values())[0]
                    patch_task = (
                        f"SURGICAL UI HOT-PATCH for element matching selector `{selector}` in project `{slug}`.\n"
                        f"User Request: {prompt}\n"
                        f"Target File: {file_hint or 'Find the component rendering ' + selector}\n"
                        f"Current Computed Styles: {json.dumps(styles)}\n"
                        f"Instructions: Apply minimal, surgical edits strictly to resolve the user's styling/UI request. Do not refactor unrelated code."
                    )
                    eng = engine.Engine(emit=lambda ev: None, project=slug)
                    result_text = eng.run_agent(build_agent, patch_task, [])
                    return self.send(200, {"ok": True, "result": result_text, "selector": selector})
            except Exception as e:
                return self.send(200, {"ok": False, "error": str(e)})
            return self.send(404, {"error": "unknown vibe action"})
        if u.startswith("/api/form/"):
            act = u.rsplit("/", 1)[1]
            if act == "skill":
                skills2.snapshot(str(body.get("original_name") or body.get("name") or ""))
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
    threading.Thread(target=housekeeping, daemon=True, name="kryzen-housekeeping").start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
