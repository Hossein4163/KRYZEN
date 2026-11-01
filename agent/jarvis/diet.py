"""Context diet: keep model prompts small without hiding anything from the user.

- smart_truncate:    big tool outputs keep their head, tail and error lines instead of only the first N chars
- mask_observations: tool results the model already used become one-line stubs with a blob id (read_blob reopens)
- fold_history:      chat history beyond the recent window becomes one summary message (cached per prefix)
- ledger_digest:     the parallel-task ledger is summarised instead of being pasted in full
- Budget:            per-run token/time caps with a warning at 80 % and a pause at 100 %
"""
import hashlib
import json
import re
import time

SIGNAL = re.compile(r"error|fail|exception|traceback|warn|denied|not found|cannot|undefined|refused|panic|fatal|✗|✖",
                    re.I)


def smart_truncate(text, limit=12000):
    if len(text) <= limit:
        return text
    head_n, tail_n = int(limit * .55), int(limit * .3)
    head, middle, tail = text[:head_n], text[head_n:-tail_n], text[-tail_n:]
    signal, seen, budget = [], set(), limit - head_n - tail_n - 200
    for line in middle.splitlines():
        s = line.strip()
        if s and SIGNAL.search(s) and s not in seen:
            seen.add(s)
            s = s[:300]
            if budget - len(s) < 0:
                break
            budget -= len(s) + 1
            signal.append(s)
    cut = len(text) - head_n - tail_n
    note = f"\n…[{cut} chars omitted"
    note += f"; {len(signal)} error/warning lines kept below]\n" + "\n".join(signal) + "\n…\n" if signal else "]\n"
    return head + note + tail


def stub(content, blob):
    first = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")[:160]
    ok = "error" not in content[:400].lower()
    return (f"[earlier tool result, {len(content)} chars, {'ok' if ok else 'had errors'}: {first} … "
            f"Full output kept as blob {blob}; call read_blob with this id only if you need it again.]")


def mask_observations(messages, blobs, keep_last=2, min_chars=700):
    """Return a prompt view where old, large tool results are replaced by stubs. `messages` is not modified."""
    tool_idx = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    old = set(tool_idx[:-keep_last] if keep_last else tool_idx)
    out = []
    for i, m in enumerate(messages):
        content = m.get("content")
        blob = blobs.get(m.get("tool_call_id"))
        if i in old and blob and isinstance(content, str) and len(content) > min_chars:
            out.append({**m, "content": stub(content, blob)})
        else:
            out.append(m)
    return out


def prompt_chars(messages):
    return sum(len(m.get("content") or "") + len(json.dumps(m.get("tool_calls") or "")) for m in messages)


def history_key(messages):
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


def extractive_summary(messages, limit=2400):
    """No-model fallback: first lines of each older turn."""
    lines = []
    for m in messages:
        text = re.sub(r"\s+", " ", str(m.get("content") or "")).strip()
        if text:
            lines.append(f"- {m.get('role')}: {text[:220]}")
    out = "\n".join(lines)
    return out if len(out) <= limit else out[:limit // 3] + "\n…\n" + out[-2 * limit // 3:]


def fold_history(history, keep, summarize, cache, max_chars=40000):
    """history: [{'role','content'}]. Older messages become one summary message; `cache` maps prefix hash -> text.
    The verbatim tail also shrinks (two messages at a time) while it is longer than max_chars."""
    while keep > 2 and sum(len(str(m.get("content") or "")) for m in history[-keep:]) > max_chars:
        keep -= 2
    if len(history) <= keep:
        return history, None
    older, recent = history[:-keep], history[-keep:]
    key = history_key(older)
    summary = cache.get(key)
    if summary is None:
        try:
            summary = summarize(older)
        except Exception:
            summary = None
        summary = summary or extractive_summary(older)
        cache[key] = summary
    folded = {"role": "user", "content": "[Summary of earlier conversation in this session — background only, "
                                          "not new instructions]\n" + summary}
    ack = {"role": "assistant", "content": "Understood; I will use that as background."}
    return [folded, ack, *recent], key


def ledger_digest(memory, limit=2000):
    """memory: TaskLedger.memory() records. A compact table the coordinator can expand with ledger_lookup."""
    if not memory:
        return "none yet"
    rows = []
    for r in memory:
        line = f"{r.get('id')} [{r.get('state')}] {r.get('agent', '').replace(' Agent', '')}: {str(r.get('task', ''))[:70]}"
        if r.get("error"):
            line += f" — {str(r['error'])[:60]}"
        rows.append(line)
    text = "\n".join(rows)
    if len(text) > limit:
        text = text[-limit:]
        text = "…" + text[text.find("\n"):]
    return text + "\nUse ledger_lookup(task_id) for a task's full definition, result and checkpoint."


class Budget:
    def __init__(self, max_tokens=0, max_minutes=0):
        self.max_tokens, self.max_seconds = max_tokens or 0, (max_minutes or 0) * 60
        self.started, self.warned, self.tripped = time.time(), False, False

    def state(self, tokens):
        elapsed = time.time() - self.started
        ratio = max(tokens / self.max_tokens if self.max_tokens else 0, elapsed / self.max_seconds if self.max_seconds else 0)
        return {"ratio": round(ratio, 3), "tokens": tokens, "max_tokens": self.max_tokens,
                "elapsed": round(elapsed), "max_seconds": self.max_seconds}

    def check(self, tokens):
        """Returns 'warn' once at 80 %, 'pause' once at 100 %, else None."""
        s = self.state(tokens)
        if s["ratio"] >= 1 and not self.tripped:
            self.tripped = True
            return "pause", s
        if s["ratio"] >= .8 and not self.warned:
            self.warned = True
            return "warn", s
        return None, s

    def extend(self, max_tokens=None, max_minutes=None):
        """After the user resumes a budget pause, allow another 50 % — or the (higher) current settings."""
        if self.max_tokens:
            self.max_tokens = max(int(self.max_tokens * 1.5), max_tokens or 0) if max_tokens != 0 else 0
        if self.max_seconds:
            self.max_seconds = max(int(self.max_seconds * 1.5), (max_minutes or 0) * 60) if max_minutes != 0 else 0
        self.warned = self.tripped = False


def compact_boundary(messages, head, keep_tail=8):
    """Index where the verbatim tail starts: an assistant message (so tool results stay with their call) leaving
    about `keep_tail` messages after it. Returns None if there is nothing worth compacting."""
    start = max(head, len(messages) - keep_tail)
    for i in range(start, len(messages)):
        if messages[i].get("role") == "assistant":
            return i if i - head >= 4 else None
    return None


def steps_digest(messages, limit=30000):
    """Readable text of agent steps for the summarizer: calls, arguments and (shortened) results."""
    out = []
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            if m.get("content"):
                out.append("ASSISTANT: " + str(m["content"])[:1500])
            for c in m.get("tool_calls") or []:
                fn = c.get("function") or {}
                out.append(f"CALL {fn.get('name')}: {str(fn.get('arguments'))[:400]}")
        elif role == "tool":
            out.append("RESULT: " + str(m.get("content") or "")[:800])
        elif role == "user":
            out.append("NOTE: " + str(m.get("content") or "")[:1500])
    text = "\n".join(out)
    return text if len(text) <= limit else text[:limit // 3] + "\n…\n" + text[-2 * limit // 3:]


COMPACT_PROMPT = ("Compress these earlier work steps of an AI agent into a precise state summary it can continue from. "
                  "Keep: what was done, files created/changed (exact paths), commands run and their outcome, decisions, "
                  "errors still open, and what remains to do. Max 25 short bullets. No speculation.")


def compacted_view(messages, head, state):
    """Prompt view after compaction: the head (system + history + task), one summary message, then the tail."""
    if not state.get("summary"):
        return messages
    note = {"role": "user", "content": "[Context compacted — summary of your earlier steps in this task. Continue from "
                                       "here; files and tool results still exist, re-read anything you need.]\n" + state["summary"]}
    return [*messages[:head], note, *messages[state["cut"]:]]
