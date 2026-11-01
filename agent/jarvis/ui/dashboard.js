// Home: everything running, the run queue, attention inbox, projects, spend, health, skills, memory, settings.
import {$, $$, ago, api, currentProject, currentSession, esc, fmtMs, fmtTokens, onEvent, onMode, activeMode, setMode, shortAgent, toast} from "./core.js";
import {openReview} from "./review.js";
import {renderGallery} from "./media.js";

const root = () => $("#homeView");
let tab = localStorage.getItem("kryzen.homeTab") || "overview";
let data = null, health = null, timer = 0, healthTimer = 0, busy = false;

const TABS = [["overview", "Overview"], ["shots", "Screenshots"], ["skills", "Skills"], ["memory", "Project memory"], ["settings", "Runtime settings"]];

function shell() {
  root().innerHTML = `<div class="kz-pad"><div class="kz-head"><div><div class="kz-eyebrow">K.R.Y.Z.E.N</div><h2>Home</h2></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="kz-btn" data-go="trace">Open trace</button><button class="kz-btn" id="kzPaletteHint" title="Command palette">⌘K / Ctrl+K</button></div></div>
    <div class="kz-tabs" role="tablist">${TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("")}</div>
    <div id="kzHomeBody"></div></div>`;
  root().querySelector(".kz-tabs").onclick = e => { const b = e.target.closest("[data-tab]"); if (b) { tab = b.dataset.tab; localStorage.setItem("kryzen.homeTab", tab); shell(); render(); } };
  root().querySelector('[data-go="trace"]').onclick = () => setMode("trace");
  root().querySelector("#kzPaletteHint").onclick = () => window.dispatchEvent(new Event("kryzen:palette"));
}

async function refresh(force) {
  if (busy || activeMode() !== "home") return;
  busy = true;
  try {
    data = await api("/api/dashboard");
    if (force || !health || Date.now() - health._at > 30000) { health = await api("/api/health/deep" + (force ? "?force=1" : "")); health._at = Date.now(); }
    if (tab === "overview") render();
  } finally { busy = false; }
}

function render() {
  const body = $("#kzHomeBody");
  if (!body) return;
  if (tab === "skills") return renderSkills(body);
  if (tab === "shots") return renderGallery(body);
  if (tab === "memory") return renderMemory(body);
  if (tab === "settings") return renderSettings(body);
  if (!data) { body.innerHTML = '<div class="kz-empty">Loading…</div>'; return; }
  if (data.error) { body.innerHTML = `<div class="kz-empty" role="alert">${esc(data.error)}</div>`; return; }
  body.innerHTML = `<div class="kz-grid">${nowCard()}${inboxCard()}${queueCard()}${spendCard()}${projectsCard()}${healthCard()}${recentCard()}</div>`;
  wire(body);
}

function nowCard() {
  const runs = data.running || [], g = data.gate || {};
  const rows = runs.map(r => {
    const b = r.budget || {}, ratio = Math.min(1, b.ratio || 0), u = r.usage || {};
    const lanes = (r.lanes || []).filter(l => ["running", "waiting"].includes(l.state));
    return `<div class="kz-row" style="flex-wrap:wrap"><span class="kz-dot ${r.paused ? "warn" : "live"}"></span>
      <div class="grow"><div class="title">${esc(r.title)}</div><div class="sub">${esc(r.project || "general")} · ${fmtTokens((u.prompt || 0) + (u.completion || 0))} tokens · ${u.calls || 0} model calls · ${u.tools || 0} tools · ${fmtMs((u.elapsed || 0) * 1000)}</div>
        ${b.max_tokens || b.max_seconds ? `<div class="kz-bar ${ratio >= 1 ? "bad" : ratio >= .8 ? "warn" : ""}" title="Budget ${Math.round(ratio * 100)}%" style="margin-top:6px"><i style="width:${ratio * 100}%"></i></div>` : ""}
        ${lanes.length ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">${lanes.map(l => `<span class="kz-chip live">${esc(l.id)} · ${esc(shortAgent(l.agent))}<button class="kz-btn" style="padding:0 5px;font-size:10px" data-lane="${esc(l.task_id)}" data-session="${esc(r.id)}" title="Cancel this lane">✕</button></span>`).join("")}</div>` : ""}</div>
      <button class="kz-btn" data-open="${esc(r.id)}">Open</button>
      <button class="kz-btn" data-pause="${esc(r.id)}" data-state="${r.paused ? "resume" : "pause"}">${r.paused ? "Resume" : "Pause"}</button>
      <button class="kz-btn danger" data-stop="${esc(r.id)}">Stop</button></div>`;
  }).join("");
  return `<section class="kz-card wide"><h3>Now <small>model requests ${g.active || 0}/${g.limit || 0} (max ${g.max_limit || "?"}) · ${g.queued || 0} waiting${g.cooldown_seconds ? ` · rate-limit cooldown ${g.cooldown_seconds}s` : ""}</small></h3>
    ${rows || '<div class="kz-empty">Nothing is running. Start a chat, or Continue a project below.</div>'}</section>`;
}

function inboxCard() {
  const items = data.approvals || [], failed = (data.recent || []).filter(r => r.error);
  const bad = (health?.checks || []).filter(c => !c.ok);
  const rows = [
    ...items.map(a => `<div class="kz-row"><span class="kz-dot warn"></span><div class="grow"><div class="title">${esc(shortAgent(a.agent))} wants to ${a.new_file ? "create" : "edit"} ${esc(a.path)}</div><div class="sub">${esc(a.project || "")} · ${ago(a.t)}</div></div><button class="kz-btn primary" data-review="${esc(a.id)}">Review</button></div>`),
    ...bad.map(c => `<div class="kz-row"><span class="kz-dot bad"></span><div class="grow"><div class="title">${esc(c.title)}</div><div class="sub">${esc(c.detail)}</div></div>${c.fix === "repair" ? '<button class="kz-btn" data-repair>Repair</button>' : ""}</div>`),
    ...failed.slice(0, 3).map(r => `<div class="kz-row"><span class="kz-dot bad"></span><div class="grow"><div class="title">${esc(r.title)}</div><div class="sub">${esc(r.last.replace(/^⚠️\s*/, ""))}</div></div><button class="kz-btn" data-open="${esc(r.id)}">Open</button></div>`)];
  return `<section class="kz-card"><h3>Attention <small>${rows.length || "all clear"}</small></h3>${rows.join("") || '<div class="kz-empty">Nothing needs you right now.</div>'}</section>`;
}

function queueCard() {
  const q = data.queue || [];
  return `<section class="kz-card"><h3>Run queue <small>${q.length} waiting</small></h3>${q.map((i, n) => `<div class="kz-row"><span class="kz-chip">#${n + 1}</span><div class="grow"><div class="title">${esc(i.text)}</div><div class="sub">${esc(i.project || "general")} · queued ${ago(i.t)}</div></div><button class="kz-btn danger" data-unqueue="${esc(i.qid)}">Remove</button></div>`).join("") ||
    '<div class="kz-empty">Messages sent while a run is busy wait here and start automatically.</div>'}</section>`;
}

function spendCard() {
  const u = data.usage || {}, t = u.today || {}, w = u.week || {};
  const days = Array.from({length: 7}, (_, i) => { const d = new Date(Date.now() - (6 - i) * 864e5); return d.toISOString().slice(0, 10); });
  const local = d => { const x = new Date(d + "T12:00:00"); return x.toLocaleDateString([], {weekday: "short"}); };
  const byDay = u.by_day || {}, max = Math.max(1, ...days.map(d => byDay[d] || 0));
  const top = (obj, n = 5) => Object.entries(obj || {}).sort((a, b) => b[1] - a[1]).slice(0, n);
  return `<section class="kz-card"><h3>Spend <small>tokens</small></h3>
    <div class="kz-stat"><div><b>${fmtTokens((t.prompt || 0) + (t.completion || 0))}</b><span>today · ${t.calls || 0} calls</span></div><div><b>${fmtTokens((w.prompt || 0) + (w.completion || 0))}</b><span>7 days</span></div><div><b>${w.prompt ? Math.round((w.completion || 0) / w.prompt * 100) : 0}%</b><span>output / input</span></div></div>
    <div class="kz-chart" role="img" aria-label="Tokens per day, last 7 days">${days.map(d => `<div title="${d}: ${fmtTokens(byDay[d] || 0)}"><i style="height:${(byDay[d] || 0) / max * 100}%"></i><span>${local(d)}</span></div>`).join("")}</div>
    <div class="kz-grid" style="grid-template-columns:1fr 1fr;margin-top:10px"><div><div class="kz-eyebrow" style="margin-bottom:4px">By agent</div><ul class="kz-list">${top(u.by_agent).map(([k, v]) => `<li><span>${esc(shortAgent(k))}</span><span>${fmtTokens(v)}</span></li>`).join("") || '<li class="kz-muted">no data yet</li>'}</ul></div>
    <div><div class="kz-eyebrow" style="margin-bottom:4px">By project</div><ul class="kz-list">${top(u.by_project).map(([k, v]) => `<li><span>${esc(k)}</span><span>${fmtTokens(v)}</span></li>`).join("") || '<li class="kz-muted">no data yet</li>'}</ul></div></div></section>`;
}

function projectsCard() {
  const ps = data.projects || [];
  return `<section class="kz-card"><h3>Projects <small>${ps.length}</small></h3>${ps.map(p => {
    const pct = p.total ? Math.round(p.done / p.total * 100) : 0;
    return `<div class="kz-row"><div class="grow"><div class="title">${esc(p.slug)} <span class="kz-muted">${p.done}/${p.total}${p.state ? " · " + esc(p.state) : ""}</span></div>
      <div class="kz-bar ok" style="margin:5px 0"><i style="width:${pct}%"></i></div><div class="sub">${p.next ? "Next: " + esc(p.next) : p.total ? "All planned tasks done" : "No plan yet"}</div></div>
      <button class="kz-btn" data-continue="${esc(p.slug)}">Continue</button></div>`;
  }).join("") || '<div class="kz-empty">No projects yet.</div>'}</section>`;
}

function healthCard() {
  const h = health || {checks: []};
  const repairing = h.repair?.state === "running";
  return `<section class="kz-card"><h3>Health <small>${h.ok ? "all good" : "needs attention"}</small></h3>
    ${(h.checks || []).map(c => `<div class="kz-row"><span class="kz-dot ${c.ok ? "ok" : "bad"}"></span><div class="grow"><div class="title">${esc(c.title)}</div><div class="sub">${esc(c.detail)}</div></div></div>`).join("") || '<div class="kz-empty">Checking…</div>'}
    <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap"><button class="kz-btn" data-recheck>Check again</button>
    <button class="kz-btn" data-repair ${repairing ? "disabled" : ""}>${repairing ? "Repairing backend…" : "Repair backend"}</button>
    ${h.repair?.state === "failed" ? '<span class="kz-chip bad">last repair failed</span>' : h.repair?.state === "done" ? '<span class="kz-chip ok">repaired</span>' : ""}</div></section>`;
}

function recentCard() {
  const r = data.recent || [];
  return `<section class="kz-card"><h3>Recent conversations</h3>${r.map(s => `<div class="kz-row"><span class="kz-dot ${s.error ? "bad" : "ok"}"></span><div class="grow"><div class="title">${esc(s.title)}</div><div class="sub">${esc(s.project || "general")} · ${ago(s.t)}</div></div><button class="kz-btn" data-open="${esc(s.id)}">Open</button><button class="kz-btn" data-trace="${esc(s.id)}">Trace</button></div>`).join("") || '<div class="kz-empty">No conversations yet.</div>'}</section>`;
}

function wire(body) {
  body.onclick = async e => {
    const t = e.target.closest("button"); if (!t) return;
    const d = t.dataset;
    if (d.open) { await window.openSession?.(d.open); return; }
    if (d.trace) { window.dispatchEvent(new CustomEvent("kryzen:trace", {detail: {id: d.trace}})); setMode("trace"); return; }
    if (d.review) return openReview(d.review);
    if (d.stop) { await api("/api/stop", {id: d.stop}); toast("Stopping…", "ok"); return refresh(); }
    if (d.pause) { const r = await api("/api/run-control", {id: d.pause, action: d.state}); if (r.ok === false) toast(r.error || r.errors?.join(" "), "err"); return refresh(); }
    if (d.lane) { if (!confirm("Cancel this lane? Tasks that depend on it will be blocked.")) return; await api("/api/lane", {id: d.session, task_id: d.lane, action: "cancel"}); toast("Lane cancelled", "ok"); return refresh(); }
    if (d.unqueue) { await api("/api/queue/cancel", {qid: d.unqueue}); return refresh(); }
    if (d.continue !== undefined && d.continue) {
      if (typeof window.switchProject === "function") window.switchProject(d.continue);
      const r = await window.continueProject?.(d.continue);
      if (r?.queued || r?.id) toast(r.queued ? "Queued" : "Continuing " + d.continue, "ok");
      return;
    }
    if ("recheck" in d) { health = null; return refresh(true); }
    if ("repair" in d) {
      if (!confirm("Repair the backend? This recreates the workflow/search containers and their network (data is kept). Running agent tool calls may fail briefly.")) return;
      const r = await api("/api/repair-backend", {}); if (!r.ok) toast(r.error, "err"); else toast("Repairing backend…", "ok");
      health = null; setTimeout(() => refresh(true), 1500);
    }
  };
}

// ---------------------------------------------------------------- Skills tab
async function renderSkills(body) {
  body.innerHTML = '<div class="kz-empty">Loading skills…</div>';
  const [ins, imp] = await Promise.all([api("/api/skills2/insights"), api("/api/skills2/importable")]);
  if (ins.error) { body.innerHTML = `<div class="kz-empty" role="alert">${esc(ins.error)}</div>`; return; }
  const drafts = ins.drafts || [];
  body.innerHTML = `<div class="kz-grid">
    <section class="kz-card wide"><h3>Usage <small>${ins.skills.length} skills · ${ins.unused_assigned.length} assigned but never read</small></h3>
      <div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12.5px"><thead><tr style="text-align:left;color:var(--faint)"><th style="padding:6px 4px">Skill</th><th>Reads</th><th>OK</th><th>Last used</th><th>Used by</th><th>Versions</th><th></th></tr></thead>
      <tbody>${ins.skills.map(s => `<tr style="border-top:1px solid rgba(255,255,255,.06)"><td style="padding:7px 4px"><b>${esc(s.name)}</b><div class="kz-muted">${esc(s.description).slice(0, 90)}</div></td>
        <td>${s.reads}</td><td>${s.ok_rate == null ? "—" : Math.round(s.ok_rate * 100) + "%"}</td><td>${s.last_used ? ago(s.last_used) : "never"}</td>
        <td class="kz-muted">${Object.keys(s.used_by).map(shortAgent).join(", ") || (s.assigned.length ? "assigned: " + s.assigned.map(shortAgent).join(", ") : "unassigned")}</td>
        <td>${s.versions ? `<button class="kz-btn" data-versions="${esc(s.name)}">${s.versions}</button>` : "0"}</td>
        <td style="white-space:nowrap"><button class="kz-btn" data-test="${esc(s.name)}" data-prompt="${esc(s.test)}" title="${s.test ? "Run the saved test prompt" : "Set a test prompt"}">${s.test ? "▶ Test" : "Set test"}</button></td></tr>`).join("")}</tbody></table></div></section>
    <section class="kz-card"><h3>Learned skill drafts <small>${drafts.length}</small></h3>
      ${drafts.map(d => `<div class="kz-row" style="align-items:flex-start"><div class="grow"><div class="title">${esc(d.name)}</div><div class="sub" style="white-space:normal">${esc(d.description)}</div><details><summary class="kz-muted" style="cursor:pointer">instructions</summary><pre class="kz-pre">${esc(d.body)}</pre></details></div>
        <button class="kz-btn primary" data-approve="${esc(d.name)}">Install</button><button class="kz-btn danger" data-discard="${esc(d.name)}">Discard</button></div>`).join("") || '<div class="kz-empty">No drafts. Create one from a successful run below.</div>'}
      <div style="margin-top:10px"><button class="kz-btn" data-draft>Draft a skill from the current conversation's last run</button></div></section>
    <section class="kz-card"><h3>Import skills <small>~/.claude/skills · ~/.agents/skills</small></h3>
      ${(imp.skills || []).map(s => `<div class="kz-row"><div class="grow"><div class="title">${esc(s.name)}</div><div class="sub">${esc(s.description || s.source)}</div></div>${s.installed ? '<span class="kz-chip ok">installed</span>' : s.valid_name ? `<button class="kz-btn" data-import="${esc(s.source)}">Import</button>` : '<span class="kz-chip">rename needed</span>'}</div>`).join("") || '<div class="kz-empty">No external skills found.</div>'}</section>
    <section class="kz-card"><h3>Per-project overrides</h3><p class="kz-muted" style="margin:0">Put <code>.devpilot/skills/&lt;skill-name&gt;.md</code> in a project to replace a shared skill's instructions for that project only. Agents read the override automatically.</p></section>
  </div>`;
  body.onclick = async e => {
    const b = e.target.closest("button"); if (!b) return; const d = b.dataset;
    if (d.versions) return showVersions(d.versions);
    if (d.test !== undefined && d.test) {
      if (d.prompt) { setMode("mesh"); return window.send?.(d.prompt); }
      const p = prompt(`Test prompt for ${d.test} (a request that should make agents use this skill):`);
      if (p) { const r = await api("/api/skills2/test", {name: d.test, prompt: p}); r.ok ? toast("Saved", "ok") : toast(r.errors?.join(" "), "err"); renderSkills(body); }
      return;
    }
    if (d.approve) { const r = await api("/api/skills2/approve-draft", {name: d.approve}); r.ok ? toast("Skill installed — assign it to agents in Control › Skills", "ok") : toast((r.errors || [r.error]).join(" "), "err"); return renderSkills(body); }
    if (d.discard) { await api("/api/skills2/discard-draft", {name: d.discard}); return renderSkills(body); }
    if (d.import) { const r = await api("/api/skills2/import", {source: d.import}); r.ok ? toast(r.message, "ok") : toast((r.errors || [r.error]).join(" "), "err"); return renderSkills(body); }
    if ("draft" in d) {
      const id = currentSession(); if (!id) return toast("Open a conversation first", "err");
      b.disabled = true; b.textContent = "Drafting…";
      const r = await api("/api/skills2/draft", {id});
      r.ok ? toast("Draft ready: " + r.draft.name, "ok") : toast((r.errors || [r.error]).join(" "), "err");
      return renderSkills(body);
    }
  };
}

async function showVersions(name) {
  const {versions = []} = await api("/api/skills2/versions?name=" + encodeURIComponent(name));
  const dlg = document.createElement("dialog"); dlg.className = "kz-dialog";
  dlg.innerHTML = `<header><span class="kz-eyebrow">Skill history</span><h2>${esc(name)}</h2></header>
    <div style="padding:0 18px;display:grid;grid-template-columns:200px 1fr;gap:12px;min-height:300px"><div>${versions.map(v => `<button class="kz-btn" style="display:block;width:100%;margin-bottom:6px;text-align:left" data-v="${esc(v.stamp)}">${esc(v.stamp)}</button>`).join("")}</div>
    <pre class="kz-pre" id="kzVer" style="max-height:52vh">Pick a version to preview it.</pre></div>
    <footer><button class="kz-btn" data-close>Close</button><button class="kz-btn primary" data-restore disabled>Restore this version</button></footer>`;
  document.body.appendChild(dlg); let cur = null;
  dlg.onclick = async e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.v) { cur = b.dataset.v; const r = await api(`/api/skills2/version?name=${encodeURIComponent(name)}&stamp=${encodeURIComponent(cur)}`); dlg.querySelector("#kzVer").textContent = r.text || r.error; dlg.querySelector("[data-restore]").disabled = false; }
    if ("close" in b.dataset) dlg.close();
    if ("restore" in b.dataset && cur) { const r = await api("/api/skills2/rollback", {name, stamp: cur}); r.ok ? toast(r.message, "ok") : toast((r.errors || [r.error]).join(" "), "err"); dlg.close(); }
  };
  dlg.addEventListener("close", () => dlg.remove()); dlg.showModal();
}

// ---------------------------------------------------------------- Memory tab
async function renderMemory(body) {
  const slug = currentProject();
  if (!slug) { body.innerHTML = '<div class="kz-empty">Choose a project in the header to see its memory.</div>'; return; }
  body.innerHTML = '<div class="kz-empty">Loading…</div>';
  const m = await api("/api/memory?slug=" + encodeURIComponent(slug));
  if (m.error) { body.innerHTML = `<div class="kz-empty" role="alert">${esc(m.error)}</div>`; return; }
  const entries = (m.content.match(/^- \d{4}-\d{2}-\d{2} \(\w+\) .+$/gm) || []).length;
  body.innerHTML = `<section class="kz-card"><h3>${esc(slug)} · project memory <small>${entries} facts · .devpilot/memory.md</small></h3>
    <p class="kz-muted" style="margin:0 0 10px">Decisions, conventions and gotchas the agents learned. Relevant lines are given to the team each run; agents add more with <code>remember</code>. One fact per line: <code>- YYYY-MM-DD (decision) text</code>.</p>
    <textarea class="kz-textarea" id="kzMem" spellcheck="false" aria-label="Project memory">${esc(m.content || "# Project memory\n\n")}</textarea>
    <div style="display:flex;gap:8px;margin-top:10px;align-items:center"><button class="kz-btn primary" id="kzMemSave">Save</button><span class="kz-muted" id="kzMemState">${m.exists ? "" : "Not created yet — agents create it on their first remember."}</span></div></section>`;
  let revision = m.revision;
  $("#kzMemSave").onclick = async () => {
    const r = await api("/api/memory", {slug, content: $("#kzMem").value, revision});
    if (r.ok) { revision = r.revision; $("#kzMemState").textContent = "Saved."; } else $("#kzMemState").textContent = r.error || "Could not save (changed elsewhere? reload the tab).";
  };
}

// ---------------------------------------------------------------- Settings tab
async function renderSettings(body) {
  const r = await api("/api/settings/runtime");
  const s = r.settings || {};
  const num = (k, label, hint) => `<label>${label}<input type="number" name="${k}" value="${esc(s[k])}" min="${r.limits?.[k]?.[0] ?? 0}" max="${r.limits?.[k]?.[1] ?? 999999999}"><span class="kz-muted">${hint}</span></label>`;
  body.innerHTML = `<section class="kz-card"><h3>Runtime settings <small>apply to new runs</small></h3><form class="kz-form" id="kzSettings">
    <label>Small model (summaries, memory, skill drafts)<input type="text" name="small_model" value="${esc(s.small_model)}"><span class="kz-muted">Falls back to the orchestrator's model if unavailable.</span></label>
    ${num("budget_tokens", "Token budget per run", "Warn at 80%, pause at 100% (0 = unlimited). Resume adds 50%.")}
    ${num("budget_minutes", "Time budget per run (minutes)", "0 = unlimited.")}
    ${num("max_concurrency", "Max parallel model requests", "Adapts down on rate limits, up after clean calls.")}
    ${num("max_lanes", "Max parallel task lanes", "For task graphs.")}
    ${num("mask_after", "Tool results kept verbatim", "Older results become one-line stubs (reopen with read_blob).")}
    ${num("fold_after", "Chat messages kept verbatim", "Older history is summarized by the small model.")}
    ${num("compact_at_tokens", "Auto-compact at (prompt tokens)", "Long agent runs fold earlier steps into a summary past this size.")}
    ${num("budget_hard_tokens", "Hard cap per run (tokens)", "Never auto-resume past this (0 = no cap).")}
    ${num("auto_resume_seconds", "Auto-resume countdown (seconds)", "Time to press Keep paused after a budget pause.")}
    ${num("auto_continue_max", "Automatic continues in a row", "After a step limit or temporary failure (0 = never).")}
    <label class="check"><input type="checkbox" name="auto_screenshot" ${s.auto_screenshot ? "checked" : ""}>Screenshot the running app when a project run finishes</label>
    <label class="check"><input type="checkbox" name="auto_resume" ${s.auto_resume ? "checked" : ""}>Resume automatically after the token budget is reached</label>
    <label class="check"><input type="checkbox" name="auto_continue" ${s.auto_continue ? "checked" : ""}>Continue automatically after a step limit or temporary failure</label>
    <label class="check"><input type="checkbox" name="review_mode" ${s.review_mode ? "checked" : ""}>Review mode: approve every file write as a diff</label>
    <label class="check"><input type="checkbox" name="auto_memory" ${s.auto_memory ? "checked" : ""}>Learn project memory after each run</label>
    <div style="grid-column:1/-1;display:flex;gap:8px;align-items:center"><button class="kz-btn primary">Save settings</button><span class="kz-muted" id="kzSetState"></span></div></form></section>`;
  $("#kzSettings").onsubmit = async e => {
    e.preventDefault();
    const f = new FormData(e.target), out = {};
    for (const [k, v] of Object.entries(s)) out[k] = typeof v === "boolean" ? f.has(k) : typeof v === "number" ? Number(f.get(k)) : String(f.get(k) || "");
    const res = await api("/api/settings/runtime", {settings: out});
    $("#kzSetState").textContent = res.ok ? "Saved — used from the next run." : (res.errors || [res.error]).join(" · ");
  };
}

// ---------------------------------------------------------------- lifecycle
function start() { tab = localStorage.getItem("kryzen.homeTab") || tab; shell(); render(); refresh(); clearInterval(timer); timer = setInterval(refresh, 4000); }
onMode(m => { if (m === "home") start(); else clearInterval(timer); });
if (activeMode() === "home") start();
onEvent(ev => { if (activeMode() === "home" && ["turn_start", "turn_end", "approval_request", "approval_done", "budget", "queue_started", "task_state"].includes(ev.type)) setTimeout(refresh, 300); });
window.addEventListener("kryzen:inbox", () => refresh());
// Open a specific tab even when Home is already showing (palette, "Change budget" button).
window.addEventListener("kryzen:hometab", e => { tab = e.detail || tab; localStorage.setItem("kryzen.homeTab", tab); if (activeMode() === "home") { shell(); render(); refresh(); } else setMode("home"); });
window.addEventListener("kryzen:queue", () => refresh());
document.addEventListener("visibilitychange", () => { if (!document.hidden && activeMode() === "home") refresh(); });
