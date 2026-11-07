"""Run telemetry: trace spans, content-addressed blobs and a global usage ledger.

Layout (all under jarvis/sessions/):
  <session>/trace.jsonl          one span per line (model calls, tool calls, delegations, lanes, budget events)
  <session>/blobs/<sha>.txt      full tool outputs and prompt messages, stored once (deduplicated by content)
  _usage.jsonl                   one line per model call across all sessions (dashboard spend, skill stats)

Spans are small; anything large is a blob reference so the UI can open the exact data on demand.
"""
import hashlib
import json
import re
import threading
import time
from pathlib import Path

BLOB_LIMIT = 4_000_000          # bytes per blob read through the API
TRACE_READ_LIMIT = 20000        # spans returned per request


def estimate_tokens(text):
    """Rough token estimate when the provider does not report usage (≈4 chars/token, CJK/Persian denser)."""
    if not text:
        return 0
    wide = len(re.findall(r"[؀-ۿ一-鿿]", text))
    return max(1, (len(text) - wide) // 4 + wide // 2)


class Trace:
    """Per-session trace writer. Thread-safe; cheap enough to call on every model/tool call."""

    def __init__(self, root, session="", project="", usage_file=None, turn=0):
        self.root = Path(root)
        self.blobs = self.root / "blobs"
        self.file = self.root / "trace.jsonl"
        self.session, self.project, self.turn = session, project, turn
        self.usage_file = Path(usage_file) if usage_file else None
        self.lock = threading.Lock()
        self.totals = {"prompt": 0, "completion": 0, "calls": 0, "tools": 0, "estimated": 0}
        self.started = time.time()
        self.blobs.mkdir(parents=True, exist_ok=True)

    # -- blobs
    def blob(self, text):
        data = text if isinstance(text, bytes) else str(text).encode("utf-8", "replace")
        sha = hashlib.sha256(data).hexdigest()[:32]
        path = self.blobs / f"{sha}.txt"
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return sha

    def message_blobs(self, messages):
        """Store each prompt message once; a span lists ids, so 90 growing prompts cost ~1 copy of each message."""
        return [self.blob(json.dumps(m, ensure_ascii=False, sort_keys=True)) for m in messages]

    # -- spans
    def span(self, kind, **fields):
        rec = {"kind": kind, "t": time.time(), "turn": self.turn, **fields}
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with self.lock:
            with open(self.file, "a", encoding="utf-8") as f:
                f.write(line)
        return rec

    def model_call(self, agent, model, messages, prompt_tokens, completion_tokens, estimated, **fields):
        ids = self.message_blobs(messages)
        with self.lock:
            self.totals["prompt"] += prompt_tokens
            self.totals["completion"] += completion_tokens
            self.totals["calls"] += 1
            self.totals["estimated"] += int(bool(estimated))
        rec = self.span("model_call", agent=agent, model=model, messages=ids,
                        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                        estimated=bool(estimated), **fields)
        if self.usage_file:
            line = json.dumps({"t": rec["t"], "session": self.session, "project": self.project, "agent": agent,
                               "model": model, "prompt": prompt_tokens, "completion": completion_tokens}) + "\n"
            with self.lock:
                with open(self.usage_file, "a", encoding="utf-8") as f:
                    f.write(line)
        return rec

    def tool_call(self, agent, tool, args, output, ok, ms, **fields):
        with self.lock:
            self.totals["tools"] += 1
        return self.span("tool_call", agent=agent, tool=tool, args=args, ok=ok, ms=ms,
                         output=self.blob(output), chars=len(output), **fields)

    def snapshot(self):
        with self.lock:
            return {**self.totals, "elapsed": round(time.time() - self.started, 1)}


# ----------------------------------------------------------------------------- readers (server side)
def read_trace(root, turn=None, since=0, limit=TRACE_READ_LIMIT):
    path = Path(root) / "trace.jsonl"
    out = []
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < since:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            rec["i"] = i
            if turn is None or rec.get("turn") == turn:
                out.append(rec)
            if len(out) >= limit:
                break
    return out


def read_blob(root, sha):
    if not re.fullmatch(r"[0-9a-f]{32}", sha or ""):
        raise ValueError("invalid blob id")
    path = Path(root) / "blobs" / f"{sha}.txt"
    data = path.read_bytes()[:BLOB_LIMIT]
    return data.decode("utf-8", "replace")


def find_blob(sessions_dir, sha):
    """Blob ids are global content hashes; find one in any session (agents only know the id)."""
    if not re.fullmatch(r"[0-9a-f]{32}", sha or ""):
        raise ValueError("invalid blob id")
    for path in Path(sessions_dir).glob(f"*/blobs/{sha}.txt"):
        return path.read_bytes()[:BLOB_LIMIT].decode("utf-8", "replace")
    raise FileNotFoundError("blob not found")


def usage_summary(usage_file, now=None):
    """Aggregate the usage ledger for the dashboard: today / 7 days, by project, agent and model."""
    now = now or time.time()
    day0 = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    week0 = now - 7 * 86400
    out = {"today": {"prompt": 0, "completion": 0, "calls": 0}, "week": {"prompt": 0, "completion": 0, "calls": 0},
           "by_project": {}, "by_agent": {}, "by_model": {}, "by_day": {}}
    path = Path(usage_file)
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("t", 0) < week0:
                continue
            total = r.get("prompt", 0) + r.get("completion", 0)
            for bucket, ok in (("week", True), ("today", r["t"] >= day0)):
                if ok:
                    b = out[bucket]
                    b["prompt"] += r.get("prompt", 0)
                    b["completion"] += r.get("completion", 0)
                    b["calls"] += 1
            for key, name in (("by_project", r.get("project") or "general"), ("by_agent", r.get("agent", "?")),
                              ("by_model", (r.get("model") or "?").split("/")[-1])):
                out[key][name] = out[key].get(name, 0) + total
            day = time.strftime("%Y-%m-%d", time.localtime(r["t"]))
            out["by_day"][day] = out["by_day"].get(day, 0) + total
    return out


def log_agy_invocation(agent, prompt, flags=None, cwd=None):
    """Log every agy invocation for security auditing and telemetry."""
    try:
        rec = {
            "t": time.time(),
            "agent": str(getattr(agent, "name", agent) if agent else "anonymous"),
            "flags": flags or [],
            "cwd": str(cwd or ""),
            "prompt_length": len(prompt) if prompt else 0,
        }
        log_dir = Path(__file__).resolve().parent / "sessions"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "_agy_audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass

