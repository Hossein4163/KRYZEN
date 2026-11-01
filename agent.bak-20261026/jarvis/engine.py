"""Jarvis engine: runs the DevPilot agents directly against NVIDIA NIM with streaming and tool calling.

Agents, prompts, models and tool lists come from the compiled workflow (workflow/ai-dev-agent.json), which
`devpilot-sync` builds from the Obsidian notes — so the vault stays the single source of truth.
Tools run through the sandboxed PC bridge, exactly like in n8n.
"""
import datetime
import http.client
import json
import os
import re
import shlex
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = AGENT_DIR / "workflow" / "ai-dev-agent.json"
sys.path.insert(0, str(AGENT_DIR / "workflow"))
from vaultnotes import AGENT_NOTES, load_custom_tools, read_note  # noqa: E402
from modelpolicy import RESPONSE_STYLE, model_options  # noqa: E402
BRIDGE = os.environ.get("KRYZEN_BRIDGE_URL", "http://172.22.0.1:8765")
SEARX = "http://127.0.0.1:8888/search"
NIM = "https://integrate.api.nvidia.com/v1/chat/completions"
TOOL_RESULT_LIMIT = 14000
ORCHESTRATOR = "DevPilot Orchestrator"

# bridge path -> stable function name the model sees
PATH_KEYS = {"/shell": "pc_shell", "/fs/read": "pc_read_file", "/fs/write": "pc_write_file", "/fs/list": "pc_list_dir",
             "/jobs/get": "pc_job_status", "/agy": "agy_run", "/browser": "browser", "/skills/list": "list_skills",
             "/skills/read": "read_skill", "/web/fetch": "web_fetch", "/project/init": "project_init",
             "/project/list": "project_list", "/project/resume": "project_resume",
             "/project/checkpoint": "project_checkpoint"}
FROM_AI = re.compile(r"\$fromAI\('(\w+)', `([^`]*)`, '(\w+)'(?:, (.+?))?\) \}\}")


def secret(path, key=None):
    text = Path(path).read_text()
    if key is None:
        return text.strip()
    for line in text.splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError(f"{key} missing in {path}")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ---------------------------------------------------------------------------- agent specs
class Tool:
    def __init__(self, name, title, description, kind, path=None, params=None, agent=None):
        self.name, self.title, self.description, self.kind = name, title, description, kind
        self.path, self.params, self.agent = path, params or [], agent

    def schema(self):
        props, required = {}, []
        for key, desc, typ, default in self.params:
            props[key] = {"type": typ if typ in ("string", "number", "boolean") else "string", "description": desc}
            if default is None:
                required.append(key)
        return {"type": "function", "function": {"name": self.name, "description": self.description[:1000],
                                                 "parameters": {"type": "object", "properties": props,
                                                                "required": required}}}


class AgentSpec:
    def __init__(self, name, model, system, max_iter, tools, description="", color=None):
        self.name, self.model, self.system, self.max_iter = name, model, system, max_iter
        self.tools, self.description, self.color = tools, description, color


def load_agents():
    """Parse the compiled n8n workflow into agent specs (orchestrator first)."""
    wf = json.loads(WORKFLOW_FILE.read_text())
    nodes = {n["name"]: n for n in wf["nodes"]}
    conns = wf["connections"]
    today = datetime.date.today().isoformat()

    def inputs(target, kind):
        return [src for src, v in conns.items() for c in v.get(kind, [[]])[0] if c["node"] == target]

    def system_of(node):
        msg = node["parameters"]["options"]["systemMessage"].lstrip("=")
        return re.sub(r"\{\{ \$now\.toFormat\('yyyy-MM-dd'\) \}\}", today, msg)

    def tool_of(src):
        n = nodes[src]
        t, p = n["type"], n["parameters"]
        title = src.split(": ", 1)[-1]
        if t.endswith("toolThink"):
            return Tool("think", "Think", p.get("description", "Think step by step."), "think",
                        params=[("thought", "your reasoning", "string", None)])
        if t.endswith("agentTool"):
            return Tool("delegate_" + slug(src), src, p["toolDescription"], "agent", agent=src,
                        params=[("task", "Full task for this agent incl. project slug, goal, milestone/tasks, "
                                         "context and where to continue from", "string", None)])
        if "searxng" in p.get("url", ""):
            return Tool("web_search", "Web Search", p["toolDescription"], "search",
                        params=[("query", "search query", "string", None)])
        path = p["url"].replace(BRIDGE, "")
        params = []
        for bp in p.get("bodyParameters", {}).get("parameters", []):
            m = FROM_AI.search(bp["value"])
            if m:
                default = json.loads(m.group(4)) if m.group(4) else None
                params.append((m.group(1), m.group(2), m.group(3), default))
        return Tool(PATH_KEYS.get(path, slug(title)), title, p["toolDescription"], "bridge", path=path, params=params)

    def spec(name, description=""):
        n = nodes[name]
        model = nodes[inputs(name, "ai_languageModel")[0]]["parameters"]["model"]
        tools = [tool_of(s) for s in inputs(name, "ai_tool")]
        return AgentSpec(name, model, system_of(n), n["parameters"]["options"].get("maxIterations", 40), tools,
                         description)

    agents = {ORCHESTRATOR: spec(ORCHESTRATOR)}
    for t in agents[ORCHESTRATOR].tools:
        if t.kind == "agent":
            agents[t.agent] = spec(t.agent, t.description)
    # custom tools (Jarvis only): _DevPilot/Tools/*.md, granted through each agent note's tools list
    custom = load_custom_tools()
    if custom:
        for f in AGENT_NOTES.glob("*.md"):
            meta, _ = read_note(f)
            name = meta.get("agent")
            if name in agents:
                for tid in meta.get("tools", []) or []:
                    if tid in custom:
                        c = custom[tid]
                        agents[name].tools.append(Tool(tid, c["title"], c["description"], "custom", params=c["params"],
                                                       path=c))
    return agents


# ---------------------------------------------------------------------------- model + tools
class Stopped(Exception):
    pass


class IncompleteStream(RuntimeError):
    pass


class OutputLimit(RuntimeError):
    pass


class Engine:
    def __init__(self, emit, project=""):
        self.emit = emit                       # emit(event: dict)
        self.agents = load_agents()
        self.nim_key = secret(AGENT_DIR / ".keys.env", "NVIDIA_API_KEY")
        self.bridge_token = secret(AGENT_DIR / "bridge" / ".token")
        self.stop = threading.Event()
        self.pause_requested = threading.Event()
        self.paused = threading.Event()
        self.project = project
        # Load studio lazily: studio uses mesh, which shares the workflow note reader.
        import studio
        routing = studio.routing()
        if routing:
            allowed = set(routing["allowed"])
            for spec in self.agents.values():
                spec.tools = [t for t in spec.tools if t.kind != "agent" or t.agent in allowed]
            self.agents[ORCHESTRATOR].system += (
                "\nACTIVE JARVIS CANVAS: " + json.dumps(routing, ensure_ascii=False) +
                "\nDelegate only to the linked specialist cards. Connections describe orchestration guidance, "
                "not executable code or a guarantee of order. Retain checkpoint and QA requirements.")
        for note in AGENT_NOTES.glob("*.md"):
            meta, _ = read_note(note)
            spec = self.agents.get(meta.get("agent"))
            if spec and "Assigned role skills (read matching instructions" not in spec.system:
                spec.system += "\nAssigned role skills (read matching instructions with read_skill): " + ", ".join(meta.get("skills") or [])
        # Structured plan operations remain inside the same bridge boundary as file tools.
        for spec in self.agents.values():
            tool_names = {t.name for t in spec.tools}
            if "pc_read_file" in tool_names:
                spec.tools.append(Tool("read_project_plan", "Read Project Plan",
                    "Read canonical PLAN.md, tasks, checkpoint and revision-bound user approval. Pass project slug.",
                    "studio", path="plan", params=[("project", "existing project slug", "string", None)]))
            if "pc_write_file" in tool_names:
                spec.tools.append(Tool("update_plan_task", "Update Plan Task",
                    "Mark a task complete only after verification. Read Project Plan first; pass its revision and task line. "
                    "This changes PLAN.md and makes any previous approval outdated.", "studio", path="plan-task",
                    params=[("project", "existing project slug", "string", None),
                            ("line", "task line from Read Project Plan", "number", None),
                            ("done", "verified completion state", "boolean", None),
                            ("revision", "current plan revision", "string", None)]))
        if project:
            resumed = json.loads(self.bridge("/project/resume", {"slug": project}))
            if resumed.get("error"):
                raise ValueError(resumed["error"])
            plan = studio.plan_get(lambda path, body: json.loads(self.bridge(path, body)), project)
            context = {k: plan[k] for k in ("slug", "revision", "tasks", "state", "approval")}
            self.agents[ORCHESTRATOR].system += (
                "\nSELECTED PROJECT CONTEXT: " + json.dumps(context, ensure_ascii=False)[:20000] +
                "\nWork in this project unless the user explicitly requests another. Read the full PLAN.md before "
                "implementation. The approval applies only to that revision. Pending/outdated approval requires "
                "following the existing approval protocol or explicit user authorization in this turn.")
            resume_context = {key: resumed.get(key) for key in
                              ("continuation", "state", "background_jobs", "uncommitted", "docs_status", "recent_checkpoints")}
            self.agents[ORCHESTRATOR].system += (
                "\nFRESH CONTINUATION CONTEXT: " + json.dumps(resume_context, ensure_ascii=False)[:24000] +
                "\nRe-read Resume Project if this snapshot may be stale. Resolve running jobs and interrupted edits "
                "before starting duplicate work. Treat saved next_action as a suggestion to reconcile with the current plan.")

    def checkpoint_control(self):
        """Pause at safe tool/model boundaries; stop always releases a paused run."""
        if self.stop.is_set():
            raise Stopped()
        if self.pause_requested.is_set():
            if not self.paused.is_set():
                self.paused.set()
                self.emit({"type": "run_state", "state": "paused"})
            while self.pause_requested.is_set():
                if self.stop.wait(0.15):
                    self.paused.clear()
                    raise Stopped()
            self.paused.clear()
            self.emit({"type": "run_state", "state": "running"})

    # --- NVIDIA NIM, streamed
    def chat(self, agent, messages, tools):
        body = {"model": agent.model, "messages": messages, "temperature": 0.3, "stream": True,
                "tools": [t.schema() for t in tools] if tools else None, **model_options(agent.model)}
        if not tools:
            body.pop("tools")
        last, compact_retry = None, False
        for attempt in range(5):
            self.checkpoint_control()
            try:
                return self._stream(agent, json.dumps(body).encode())
            except Stopped:
                raise
            except OutputLimit:
                if compact_retry or attempt == 4:
                    why = "after a compact retry" if compact_retry else "with the retry budget exhausted"
                    raise OutputLimit(f"Model output still exceeded its limit {why}; no tools from this request were executed. Earlier completed work is preserved.")
                compact_retry = True
                # Reject all partial calls. Retry from the same completed history so
                # commands/writes from a truncated response can never be replayed.
                body.pop("reasoning_effort", None)
                body.update(model_options(agent.model, recovery=True))
                body["messages"] = [*messages, {"role": "system", "content":
                    "The previous generation reached its output limit and was discarded; no tools from that generation executed. "
                    "Respond concisely. Use one small, complete tool call at a time; split large artifacts into supported file operations. "
                    "Keep final chat brief and put detailed work in project files."}]
                self.emit({"type": "stream_reset", "agent": agent.name})
                self.emit({"type": "retry", "agent": agent.name, "attempt": attempt + 1,
                           "error": "Output limit reached; retrying once with a compact response."})
            except Exception as e:
                transient = isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError,
                                          http.client.IncompleteRead, IncompleteStream))
                if isinstance(e, urllib.error.HTTPError):
                    transient = e.code in (408, 429, 500, 502, 503, 504)
                if not transient or attempt == 4:
                    raise
                last = e
                # Reset the partial display before replaying a failed model request. Tools
                # have not executed until a complete stream has been received.
                self.emit({"type": "stream_reset", "agent": agent.name})
                self.emit({"type": "retry", "agent": agent.name, "attempt": attempt + 1, "error": str(e)[:200]})
                delay = min(2 ** attempt, 20)
                if isinstance(e, urllib.error.HTTPError) and e.code == 429:
                    # Rate limited: honour Retry-After, otherwise back off long enough for the per-minute window.
                    try:
                        delay = min(float(e.headers.get("Retry-After") or 0), 120) or min(5 * 2 ** attempt, 60)
                    except (TypeError, ValueError):
                        delay = min(5 * 2 ** attempt, 60)
                if self.stop.wait(delay):
                    raise Stopped()
        raise RuntimeError(f"model call failed after retries: {last}")

    def _stream(self, agent, data):
        req = urllib.request.Request(NIM, data=data, headers={
            "Authorization": f"Bearer {self.nim_key}", "Content-Type": "application/json",
            "Accept": "text/event-stream"})
        content, reasoning, calls = [], [], {}
        complete, finish_reason = False, None
        with urllib.request.urlopen(req, timeout=300) as r:
            for raw in r:
                if self.stop.is_set():
                    raise Stopped()
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    complete = True
                    break
                chunk = json.loads(payload)
                if chunk.get("error"):
                    raise RuntimeError("model returned an error: " + str(chunk["error"])[:500])
                if not chunk.get("choices"):
                    continue
                delta = chunk["choices"][0].get("delta") or {}
                finish_reason = chunk["choices"][0].get("finish_reason") or finish_reason
                if delta.get("reasoning_content"):
                    reasoning.append(delta["reasoning_content"])
                    self.emit({"type": "thinking", "agent": agent.name, "text": delta["reasoning_content"]})
                if delta.get("content"):
                    content.append(delta["content"])
                    self.emit({"type": "token", "agent": agent.name, "text": delta["content"]})
                for tc in delta.get("tool_calls") or []:
                    c = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    c["id"] = tc.get("id") or c["id"]
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    # Some providers repeat the full function name in later chunks.
                    if name and name != c["name"]:
                        c["name"] += name
                    c["args"] += fn.get("arguments") or ""
        if not complete and not finish_reason:
            raise IncompleteStream("model stream ended before completion")
        if finish_reason == "length":
            raise OutputLimit("model response reached its output limit; partial tool calls were discarded")
        if finish_reason == "content_filter":
            raise RuntimeError(f"model response ended with {finish_reason}; no tools were executed")
        if not content and not calls:
            raise RuntimeError("model returned an empty response")
        return "".join(content), [calls[i] for i in sorted(calls)]

    # --- tools
    def bridge(self, path, args):
        req = urllib.request.Request(BRIDGE + path, data=json.dumps(args).encode(), headers={
            "X-Bridge-Token": self.bridge_token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1800) as r:
            return r.read().decode()

    def search(self, query):
        url = SEARX + "?" + urllib.parse.urlencode({"q": query, "format": "json"})
        with urllib.request.urlopen(url, timeout=30) as r:
            results = json.load(r).get("results", [])[:8]
        return json.dumps([{k: x.get(k) for k in ("title", "url", "content")} for x in results], ensure_ascii=False)

    def run_tool(self, agent, tool, args, depth):
        self.checkpoint_control()
        if not isinstance(args, dict):
            raise ValueError("tool arguments must be a JSON object")
        for key, _desc, typ, default in tool.params:
            value = args.get(key, default)
            if value is None:
                raise ValueError(f"missing required parameter {key}")
            valid = ((typ == "string" and isinstance(value, str)) or
                     (typ == "boolean" and isinstance(value, bool)) or
                     (typ == "number" and isinstance(value, (int, float)) and not isinstance(value, bool)))
            if typ in ("string", "number", "boolean") and not valid:
                raise ValueError(f"{key} must be {typ}")
        if tool.kind == "studio":
            import studio
            bridge = lambda path, body: json.loads(self.bridge(path, body))
            if tool.path == "plan":
                return json.dumps(studio.plan_get(bridge, args.get("project", "")), ensure_ascii=False)
            result = studio.plan_task(bridge, {**args, "slug": args.get("project", "")})
            return ("" if result.get("ok") else "error: ") + json.dumps(result, ensure_ascii=False)
        if tool.kind == "think":
            return "Thought recorded. Continue."
        if tool.kind == "search":
            return self.search(args.get("query", ""))
        if tool.kind == "agent":
            return self.run_agent(self.agents[tool.agent], args.get("task", ""), [], depth + 1)
        if tool.kind == "custom":
            spec, values = tool.path, {}
            for key, _desc, _typ, default in tool.params:
                v = args.get(key, default)
                if v is None:
                    return f"error: missing parameter {key}"
                values[key] = str(v)
            # replace only {param} slots, so shell syntax like ${VAR} or ${ARR[0]} stays intact
            fill = lambda text, vals: re.sub(r"\{(\w+)\}", lambda m: vals.get(m.group(1), m.group(0)), text)
            cmd = fill(spec["command"], {k: shlex.quote(v) for k, v in values.items()})
            cwd = fill(spec["cwd"], {k: re.sub(r"[^\w.-]", "", v) for k, v in values.items()})
            return self.bridge("/shell", {"cmd": cmd, "cwd": cwd, "timeout": spec["timeout"]})
        for key, _desc, _typ, default in tool.params:
            if key not in args and default is not None:
                args[key] = default
        return self.bridge(tool.path, args)

    # --- agent loop
    def run_agent(self, agent, task, history, depth=0):
        if depth > 8:
            raise RuntimeError("delegation depth limit exceeded")
        tools = {t.name: t for t in agent.tools}
        system = agent.system if "COMPACT RESPONSES:" in agent.system else agent.system + "\n\n" + RESPONSE_STYLE
        messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": task}]
        self.emit({"type": "agent_start", "agent": agent.name, "depth": depth, "task": task[:600]})
        try:
            for step in range(agent.max_iter):
                self.checkpoint_control()
                self.emit({"type": "step", "agent": agent.name, "step": step + 1, "max": agent.max_iter})
                content, calls = self.chat(agent, messages, list(tools.values()))
                if not calls:
                    self.emit({"type": "agent_end", "agent": agent.name, "depth": depth, "text": content})
                    return content
                messages.append({"role": "assistant", "content": content or None, "tool_calls": [
                    {"id": c["id"] or f"call_{step}_{i}", "type": "function",
                     "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for i, c in enumerate(calls)]})
                for i, c in enumerate(calls):
                    self.checkpoint_control()
                    call_id = c["id"] or f"call_{step}_{i}"
                    tool = tools.get(c["name"])
                    try:
                        args = json.loads(c["args"] or "{}")
                        if not isinstance(args, dict):
                            args = None
                    except ValueError:
                        args = None
                    self.emit({"type": "tool_start", "agent": agent.name, "tool": tool.title if tool else c["name"],
                               "kind": tool.kind if tool else "unknown", "args": args if args is not None else c["args"]})
                    t0 = time.time()
                    if tool is None:
                        result = f"error: unknown tool {c['name']}; available: {', '.join(tools)}"
                    elif args is None:
                        result = "error: arguments were not valid JSON; call the tool again with a JSON object"
                    else:
                        try:
                            result = self.run_tool(agent, tool, args, depth)
                        except Stopped:
                            raise
                        except Exception as e:
                            result = f"error: {type(e).__name__}: {e}"
                    result = str(result)
                    ok = not result.lower().startswith("error")
                    try:
                        data = json.loads(result)
                        if isinstance(data, dict):
                            ok = not data.get("error") and data.get("ok") is not False and data.get("exit_code") in (None, 0)
                    except ValueError:
                        pass
                    if len(result) > TOOL_RESULT_LIMIT:
                        result = result[:TOOL_RESULT_LIMIT] + f"\n…[{len(result) - TOOL_RESULT_LIMIT} chars cut]"
                    self.emit({"type": "tool_end", "agent": agent.name, "tool": tool.title if tool else c["name"],
                               "kind": tool.kind if tool else "unknown", "ok": ok,
                               "ms": int((time.time() - t0) * 1000), "preview": result[:400]})
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
            text = (f"Reached the limit of {agent.max_iter} steps. Say 'continue' to inspect the saved project progress and carry on.")
            self.emit({"type": "agent_end", "agent": agent.name, "depth": depth, "text": text})
            return text
        except Stopped:
            self.emit({"type": "agent_end", "agent": agent.name, "depth": depth, "text": "stopped by user"})
            raise

    def respond(self, user_text, history):
        """One user turn through the orchestrator. history: prior [{'role','content'}] messages."""
        return self.run_agent(self.agents[ORCHESTRATOR], user_text, history[-30:])
