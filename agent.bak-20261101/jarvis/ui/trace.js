// Trace: every model call and tool call of a conversation — timeline, filterable log, inspector, replay.
import {$, api, activeMode, clock, currentSession, download, esc, fmtMs, fmtTokens, onEvent, onMode, shortAgent, text, toast} from "./core.js";

const S = {id: null, turn: "last", turns: 0, spans: [], next: 0, sel: -1, follow: true,
           filter: {agent: "", kind: "", failed: false, q: ""}, loading: false, sessions: []};
const root = () => $("#traceView");
const blobCache = new Map();

const kindOf = s => s.kind === "model_call" ? (s.helper ? "helper" : "model") : s.kind === "tool_call" ? "tool" : s.kind;
const startOf = s => s.t - (s.ms || 0) / 1000;
const label = s => s.kind === "model_call" ? `${s.helper ? "helper · " : ""}${fmtTokens(s.prompt_tokens)} → ${fmtTokens(s.completion_tokens)} tok${s.tool_calls?.length ? " · calls " + s.tool_calls.join(", ") : ""}`
  : s.kind === "tool_call" ? `${s.tool} ${s.ok ? "" : "✗"} · ${fmtTokens(s.chars)} chars`
  : s.kind === "delegation" ? `→ ${shortAgent(s.to)}: ${s.task || ""}` : s.kind;

async function loadSessions() {
  const r = await api("/api/sessions");
  S.sessions = r.sessions || [];
}

async function load(reset) {
  if (!S.id || S.loading) return;
  S.loading = true;
  try {
    if (reset) { S.spans = []; S.next = 0; S.sel = -1; }
    const turnQ = S.turn === "all" || S.turn === "last" ? "" : `&turn=${S.turn}`;
    const r = await api(`/api/trace?id=${encodeURIComponent(S.id)}&since=${S.next}${turnQ}`);
    if (r.error) { toast(r.error, "err"); return; }
    S.turns = r.turns || 0;
    for (const sp of r.spans || []) { S.spans.push(sp); S.next = Math.max(S.next, sp.i + 1); }
    if (S.turn === "last" && S.turns) S.spans = S.spans.filter(s => s.turn === Math.max(...S.spans.map(x => x.turn || 0)));
  } finally { S.loading = false; }
  render();
  if (S.follow && S.sel === -1) $(".kz-log")?.scrollTo({top: 1e9});
}

function filtered() {
  const f = S.filter, q = f.q.toLowerCase();
  return S.spans.filter(s => (!f.agent || s.agent === f.agent) && (!f.kind || kindOf(s) === f.kind) &&
    (!f.failed || s.ok === false) && (!q || JSON.stringify(s).toLowerCase().includes(q)));
}

function shell() {
  root().innerHTML = `<div class="kz-trace">
    <div class="kz-trace-top"><h2>Trace</h2>
      <select class="kz-select" id="kzTrSession" aria-label="Conversation"></select>
      <select class="kz-select" id="kzTrTurn" aria-label="Turn"></select>
      <label class="kz-muted" style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="kzTrFollow" ${S.follow ? "checked" : ""}>Follow live</label>
      <span style="flex:1"></span><button class="kz-btn" id="kzTrReload">Refresh</button><button class="kz-btn" id="kzTrExport">Export JSONL</button></div>
    <div class="kz-totals" id="kzTrTotals"></div>
    <div class="kz-trace-body"><div class="kz-trace-main"><div><div class="kz-timeline" id="kzTrTimeline" aria-label="Timeline"></div>
      <div class="kz-filters"><select class="kz-select" id="kzFAgent" aria-label="Agent"><option value="">All agents</option></select>
        <select class="kz-select" id="kzFKind" aria-label="Kind"><option value="">All kinds</option><option value="model">Model calls</option><option value="tool">Tool calls</option><option value="delegation">Delegations</option><option value="helper">Helper calls</option></select>
        <label class="kz-muted" style="display:flex;gap:5px;align-items:center"><input type="checkbox" id="kzFFailed">Failures only</label>
        <input class="kz-input" id="kzFText" placeholder="Search args, outputs, tools…" style="flex:1;min-width:140px"></div></div>
      <div class="kz-log" id="kzTrLog" role="listbox" aria-label="Trace log" tabindex="0"></div></div>
      <aside class="kz-inspector" id="kzTrInspector" aria-live="polite"></aside></div></div>`;
  $("#kzTrSession").onchange = e => { S.id = e.target.value; S.turn = "last"; load(true); };
  $("#kzTrTurn").onchange = e => { S.turn = e.target.value; load(true); };
  $("#kzTrFollow").onchange = e => { S.follow = e.target.checked; };
  $("#kzTrReload").onclick = () => load(true);
  $("#kzTrExport").onclick = () => download(`trace-${S.id}.jsonl`, S.spans.map(s => JSON.stringify(s)).join("\n"), "application/x-ndjson");
  $("#kzFAgent").onchange = e => { S.filter.agent = e.target.value; render(); };
  $("#kzFKind").onchange = e => { S.filter.kind = e.target.value; render(); };
  $("#kzFFailed").onchange = e => { S.filter.failed = e.target.checked; render(); };
  $("#kzFText").oninput = e => { S.filter.q = e.target.value; render(); };
  $("#kzTrLog").onclick = e => { const row = e.target.closest("[data-i]"); if (row) select(+row.dataset.i); };
  $("#kzTrLog").onkeydown = e => {
    const rows = filtered(); const pos = rows.findIndex(s => s.i === S.sel);
    if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); select(rows[Math.min(rows.length - 1, pos + 1)]?.i); }
    if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); select(rows[Math.max(0, pos - 1)]?.i); }
  };
  $("#kzTrTimeline").onclick = e => { const b = e.target.closest("[data-i]"); if (b) select(+b.dataset.i); };
}

function render() {
  if (!root().querySelector(".kz-trace")) shell();
  const sel = $("#kzTrSession");
  sel.innerHTML = S.sessions.map(s => `<option value="${esc(s.id)}" ${s.id === S.id ? "selected" : ""}>${esc(s.title || s.id)}${s.running ? " ●" : ""}</option>`).join("");
  $("#kzTrTurn").innerHTML = `<option value="last" ${S.turn === "last" ? "selected" : ""}>Latest turn</option><option value="all" ${S.turn === "all" ? "selected" : ""}>All turns</option>` +
    Array.from({length: S.turns}, (_, i) => `<option value="${i + 1}" ${String(S.turn) === String(i + 1) ? "selected" : ""}>Turn ${i + 1}</option>`).join("");
  const agents = [...new Set(S.spans.map(s => s.agent).filter(Boolean))];
  const fa = $("#kzFAgent"), cur = S.filter.agent;
  fa.innerHTML = `<option value="">All agents</option>` + agents.map(a => `<option value="${esc(a)}" ${a === cur ? "selected" : ""}>${esc(shortAgent(a))}</option>`).join("");
  totals(); timeline(); log(); inspector();
}

function totals() {
  const m = S.spans.filter(s => s.kind === "model_call"), t = S.spans.filter(s => s.kind === "tool_call");
  const p = m.reduce((a, s) => a + (s.prompt_tokens || 0), 0), c = m.reduce((a, s) => a + (s.completion_tokens || 0), 0);
  const span = S.spans.length ? Math.max(...S.spans.map(s => s.t)) - Math.min(...S.spans.map(startOf)) : 0;
  const est = m.filter(s => s.estimated).length, retries = m.reduce((a, s) => a + Math.max(0, (s.attempts || 1) - 1), 0);
  const slow = m.length ? Math.round(m.reduce((a, s) => a + (s.ms || 0), 0) / m.length) : 0;
  $("#kzTrTotals").innerHTML = `<span><b>${m.length}</b> model calls</span><span><b>${fmtTokens(p)}</b> in · <b>${fmtTokens(c)}</b> out</span>
    <span><b>${t.length}</b> tools · <b style="color:var(--bad)">${t.filter(s => !s.ok).length}</b> failed</span><span><b>${fmtMs(span * 1000)}</b> wall time</span>
    <span>avg model call <b>${fmtMs(slow)}</b></span><span><b>${retries}</b> retries</span>${est ? `<span title="Provider did not report usage for these calls">${est} estimated</span>` : ""}`;
}

function timeline() {
  const el = $("#kzTrTimeline"), spans = S.spans.filter(s => ["model_call", "tool_call"].includes(s.kind));
  if (!spans.length) { el.innerHTML = `<div class="kz-empty">${S.id ? "No recorded calls for this turn yet. Traces are recorded for runs started after the upgrade." : "Open a conversation."}</div>`; return; }
  const t0 = Math.min(...spans.map(startOf)), t1 = Math.max(...spans.map(s => s.t)), w = Math.max(.001, t1 - t0);
  const lanes = new Map();
  for (const s of spans) { const k = (s.task_id ? s.task_id.split(":").pop() + " · " : "") + shortAgent(s.agent); if (!lanes.has(k)) lanes.set(k, []); lanes.get(k).push(s); }
  el.innerHTML = [...lanes].map(([name, list]) => `<div class="kz-lane"><span title="${esc(name)}">${esc(name)}</span><div class="kz-track">${list.map(s => {
    const left = (startOf(s) - t0) / w * 100, width = Math.max(.4, (s.ms || 0) / 1000 / w * 100);
    return `<button class="kz-span ${kindOf(s)} ${s.ok === false ? "bad" : ""} ${s.i === S.sel ? "sel" : ""}" data-i="${s.i}" style="left:${left}%;width:${width}%" title="${esc(label(s))} · ${fmtMs(s.ms)}" aria-label="${esc(kindOf(s) + " " + label(s))}"></button>`;
  }).join("")}</div></div>`).join("") + `<div class="kz-muted" style="display:flex;justify-content:space-between;margin:4px 0 0 118px;font-size:10.5px"><span>${clock(t0)}</span><span>${fmtMs(w * 1000)}</span><span>${clock(t1)}</span></div>`;
}

function log() {
  const rows = filtered(), el = $("#kzTrLog");
  el.innerHTML = rows.map(s => `<div class="kz-log-row ${s.i === S.sel ? "sel" : ""}" data-i="${s.i}" role="option" aria-selected="${s.i === S.sel}">
    <span class="t">${clock(s.t)}</span><span class="a">${esc(shortAgent(s.agent))}</span><span class="m">${esc(label(s))}</span>
    <span>${s.kind === "tool_call" ? `<span class="kz-chip ${s.ok ? "ok" : "bad"}">${fmtMs(s.ms)}</span>` : s.kind === "model_call" ? `<span class="kz-chip ${s.attempts > 1 ? "warn" : ""}">${fmtMs(s.ms)}</span>` : ""}</span></div>`).join("") ||
    `<div class="kz-empty" style="padding:14px">${S.spans.length ? "No entries match the filters." : ""}</div>`;
}

function select(i) {
  if (i == null || Number.isNaN(i)) return;
  S.sel = i; S.follow = false; const f = $("#kzTrFollow"); if (f) f.checked = false;
  timeline(); log(); inspector();
  $(`.kz-log-row[data-i="${i}"]`)?.scrollIntoView({block: "nearest"});
}

async function blob(sha) {
  if (blobCache.has(sha)) return blobCache.get(sha);
  const t = await text(`/api/blob?id=${encodeURIComponent(S.id)}&sha=${encodeURIComponent(sha)}`).catch(e => "⚠ " + e.message);
  blobCache.set(sha, t); if (blobCache.size > 400) blobCache.delete(blobCache.keys().next().value);
  return t;
}

function replayBar() {
  const rows = filtered(), pos = rows.findIndex(s => s.i === S.sel);
  return `<div class="kz-replay"><button class="kz-btn" data-step="-1" ${pos <= 0 ? "disabled" : ""}>◀ Prev</button>
    <input type="range" min="0" max="${Math.max(0, rows.length - 1)}" value="${Math.max(0, pos)}" id="kzReplay" aria-label="Replay position">
    <button class="kz-btn" data-step="1" ${pos >= rows.length - 1 ? "disabled" : ""}>Next ▶</button><span class="kz-muted">${pos + 1}/${rows.length}</span></div>`;
}

async function inspector() {
  const el = $("#kzTrInspector"), s = S.spans.find(x => x.i === S.sel);
  if (!s) { el.innerHTML = overview(); return; }
  const kv = (pairs) => `<dl class="kz-kv">${pairs.filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
  let html = replayBar();
  if (s.kind === "model_call") {
    html += `<h3>${s.helper ? "Helper" : "Model"} call · ${esc(shortAgent(s.agent))}</h3>` + kv([["Model", esc(s.model)], ["Prompt", `${fmtTokens(s.prompt_tokens)} tokens · ${fmtTokens(s.prompt_chars)} chars`],
      ["Output", fmtTokens(s.completion_tokens) + " tokens"], ["Usage", s.estimated ? "estimated (provider sent none)" : "reported by provider"],
      ["Latency", fmtMs(s.ms) + (s.ttft_ms != null ? ` · first token ${fmtMs(s.ttft_ms)}` : "")], ["Attempts", s.attempts], ["Requested tools", esc((s.tool_calls || []).join(", ") || "none — final answer")],
      ["Lane", esc(s.task_id || "")], ["Time", clock(s.t)]]) +
      `<div class="kz-eyebrow" style="margin:6px 0">Exact messages sent (${(s.messages || []).length})</div><div id="kzMsgs">${(s.messages || []).map((sha, n) => `<details class="kz-msg" data-sha="${esc(sha)}"><summary>#${n + 1} <span class="kz-muted">loading…</span></summary></details>`).join("")}</div>`;
  } else if (s.kind === "tool_call") {
    html += `<h3>${esc(s.tool)} · ${esc(shortAgent(s.agent))}</h3>` + kv([["Status", s.ok ? '<span class="kz-chip ok">ok</span>' : '<span class="kz-chip bad">failed</span>'],
      ["Duration", fmtMs(s.ms)], ["Output", fmtTokens(s.chars) + " chars"], ["Lane", esc(s.task_id || "")], ["Time", clock(s.t)]]) +
      `<div class="kz-eyebrow">Arguments</div><pre class="kz-pre">${esc(typeof s.args === "string" ? s.args : JSON.stringify(s.args, null, 2))}</pre>
       <div class="kz-eyebrow">Full output</div><pre class="kz-pre" id="kzOut">loading…</pre>`;
  } else if (s.kind === "delegation") {
    html += `<h3>${esc(shortAgent(s.agent))} → ${esc(shortAgent(s.to))}</h3>` + kv([["Took", fmtMs(s.ms)], ["Handoff size", fmtTokens(s.result_chars) + " chars"], ["Depth", s.depth]]) +
      `<div class="kz-eyebrow">Task</div><pre class="kz-pre">${esc(s.task)}</pre>`;
  } else html += `<pre class="kz-pre">${esc(JSON.stringify(s, null, 2))}</pre>`;
  el.innerHTML = html;
  el.querySelector("[data-step='-1']")?.addEventListener("click", () => step(-1));
  el.querySelector("[data-step='1']")?.addEventListener("click", () => step(1));
  el.querySelector("#kzReplay")?.addEventListener("input", e => select(filtered()[+e.target.value]?.i));
  if (s.kind === "tool_call") $("#kzOut").textContent = await blob(s.output);
  if (s.kind === "model_call") {
    for (const d of el.querySelectorAll(".kz-msg")) {
      const raw = await blob(d.dataset.sha); if (S.sel !== s.i) return;
      let m; try { m = JSON.parse(raw); } catch (_) { m = {role: "?", content: raw}; }
      const content = typeof m.content === "string" ? m.content : JSON.stringify(m.content);
      const masked = content?.startsWith("[earlier tool result");
      d.querySelector("summary").innerHTML = `<b>${esc(m.role)}</b> <span class="kz-muted">${esc((content || "").slice(0, 70))}</span>${masked ? '<span class="kz-chip">masked</span>' : `<span class="kz-chip">${fmtTokens((content || "").length)} ch</span>`}`;
      d.insertAdjacentHTML("beforeend", `<pre class="kz-pre">${esc(content || "")}${m.tool_calls ? "\n\n— tool calls —\n" + esc(JSON.stringify(m.tool_calls, null, 2)) : ""}</pre>`);
    }
  }
}

function step(d) { const rows = filtered(), pos = rows.findIndex(s => s.i === S.sel); select(rows[Math.max(0, Math.min(rows.length - 1, pos + d))]?.i); }

function overview() {
  const per = {};
  for (const s of S.spans) {
    if (!s.agent) continue;
    const p = per[s.agent] ||= {tok: 0, calls: 0, tools: 0, fail: 0, ms: 0};
    if (s.kind === "model_call") { p.tok += (s.prompt_tokens || 0) + (s.completion_tokens || 0); p.calls++; p.ms += s.ms || 0; }
    if (s.kind === "tool_call") { p.tools++; if (!s.ok) p.fail++; }
  }
  const dele = S.spans.filter(s => s.kind === "delegation");
  return `<h3>This turn at a glance</h3><p class="kz-muted">Select any row or bar to see its exact input and output. Use ↑/↓ in the log or Prev/Next to replay step by step.</p>
    <table style="width:100%;font-size:12px;border-collapse:collapse;margin:10px 0 16px"><thead><tr style="color:var(--faint);text-align:left"><th>Agent</th><th>Tokens</th><th>Calls</th><th>Tools</th><th>Model time</th></tr></thead><tbody>
    ${Object.entries(per).sort((a, b) => b[1].tok - a[1].tok).map(([a, p]) => `<tr style="border-top:1px solid rgba(255,255,255,.06)"><td style="padding:5px 0">${esc(shortAgent(a))}</td><td>${fmtTokens(p.tok)}</td><td>${p.calls}</td><td>${p.tools}${p.fail ? ` <span style="color:var(--bad)">(${p.fail}✗)</span>` : ""}</td><td>${fmtMs(p.ms)}</td></tr>`).join("") || '<tr><td colspan="5" class="kz-muted">No data.</td></tr>'}</tbody></table>
    <div class="kz-eyebrow" style="margin-bottom:6px">Delegation tree</div><div class="kz-tree">${dele.map(d => `<div style="margin-left:${(d.depth - 1) * 14}px" data-i="${d.i}"><b>${esc(shortAgent(d.agent))}</b> → <b>${esc(shortAgent(d.to))}</b> <span class="kz-muted">${fmtMs(d.ms)} · ${esc((d.task || "").slice(0, 90))}</span></div>`).join("") || '<div class="kz-muted">No delegations in this turn.</div>'}</div>`;
}

async function open(id) {
  await loadSessions();
  S.id = id || S.id || currentSession() || S.sessions[0]?.id || null;
  S.turn = "last";
  render(); load(true);
}

onMode(m => { if (m === "trace") open(); });
window.addEventListener("kryzen:trace", e => { S.id = e.detail?.id || S.id; if (activeMode() === "trace") open(S.id); });
if (activeMode() === "trace") open();

let pending = 0;
onEvent(ev => {
  if (activeMode() !== "trace" || !S.follow || !["model_call", "tool_end", "turn_end", "agent_end", "turn_start"].includes(ev.type)) return;
  if (ev.type === "turn_start") { S.turn = "last"; }
  clearTimeout(pending); pending = setTimeout(() => load(ev.type === "turn_start"), 400);
});
