// Home: everything running, the run queue, attention inbox, projects, spend, health, skills, memory, settings.
import {$, ago, api, currentProject, currentSession, esc, fmtMs, fmtTokens, onEvent, onMode, activeMode, setMode, shortAgent, toast} from "./core.js";
import {openReview} from "./review.js";
import {renderGallery} from "./media.js";

const root = () => $("#homeView");
let tab = localStorage.getItem("kryzen.homeTab") || "overview";
let data = null, health = null, timer = 0, busy = false;
let renderedProject = "";

const TABS = [["overview", "Overview"], ["shots", "Screenshots"], ["skills", "Skills"], ["memory", "Memory"], ["system", "System"], ["settings", "Settings"]];

function shell() {
  if (!TABS.some(([key]) => key === tab)) tab = "overview";
  root().innerHTML = `<div class="kz-pad"><header class="workspace-heading"><h1>Workspace</h1>
    <div class="kz-tabs" role="tablist" aria-label="Workspace sections">${TABS.map(([key, label]) =>
      `<button role="tab" id="home-tab-${key}" data-tab="${key}" aria-controls="kzHomeBody" aria-selected="${key === tab}" tabindex="${key === tab ? 0 : -1}">${label}</button>`).join("")}</div></header>
    <div id="kzHomeBody" role="tabpanel" tabindex="0" aria-labelledby="home-tab-${tab}"></div></div>`;
  const tabs = root().querySelector(".kz-tabs");
  const select = key => {
    tab = key;
    localStorage.setItem("kryzen.homeTab", tab);
    shell();
    render();
    refresh();
    root().querySelector(`#home-tab-${tab}`).focus();
  };
  tabs.addEventListener("click", event => {
    const button = event.target.closest("[data-tab]");
    if (button && button.dataset.tab !== tab) select(button.dataset.tab);
  });
  tabs.addEventListener("keydown", event => {
    const index = TABS.findIndex(([key]) => key === tab);
    const keys = {ArrowRight: (index + 1) % TABS.length, ArrowLeft: (index + TABS.length - 1) % TABS.length, Home: 0, End: TABS.length - 1};
    if (!(event.key in keys)) return;
    event.preventDefault();
    select(TABS[keys[event.key]][0]);
  });
}

async function refresh(force = false) {
  if (busy || activeMode() !== "home" || !["overview", "system"].includes(tab)) return;
  busy = true;
  try {
    const checks = force || !health || Date.now() - health._at > 30000
      ? api("/api/health/deep" + (force ? "?force=1" : "")) : Promise.resolve(health);
    const [overview, status] = await Promise.all([api("/api/dashboard"), checks]);
    data = overview;
    if (status !== health) health = {...status, _at: Date.now()};
    if (activeMode() === "home" && ["overview", "system"].includes(tab)) render();
  } finally { busy = false; }
}

function render() {
  const body = $("#kzHomeBody");
  if (!body) return;
  renderedProject = currentProject();
  if (tab === "skills") return renderSkills(body);
  if (tab === "shots") return renderGallery(body);
  if (tab === "memory") return renderMemory(body);
  if (tab === "settings") return renderSettings(body);
  if (!data) { body.innerHTML = '<div class="kz-empty" role="status">Loading workspace…</div>'; return; }
  const markup = data.error
    ? `<div class="kz-empty" role="alert">${esc(data.error)} <button type="button" class="kz-btn" data-recheck>Try again</button></div>`
    : tab === "system"
      ? `<div class="workspace-system">${spendCard()}${healthCard()}</div>`
      : `${projectSpotlight()}<div class="workspace-overview">${activitySection()}${projectsCard()}</div>`;
  if (body.workspaceMarkup === markup) return;
  body.workspaceMarkup = markup;
  const focused = body.contains(document.activeElement) ? document.activeElement : null;
  const buttonKey = focused?.tagName === "BUTTON" ? focused.outerHTML : null;
  body.innerHTML = markup;
  wire(body);
  if (buttonKey) {
    const match = [...body.querySelectorAll("button")].find(button => button.outerHTML === buttonKey);
    (match || body).focus({preventScroll: true});
  }
}

function projectSpotlight() {
  const slug = currentProject();
  if (!slug) return `<section class="workspace-spotlight" aria-labelledby="current-project">
    <div><h2 id="current-project">Add your first project</h2><p>Open a folder or create a project to start planning and working with your agents.</p>
      <button type="button" class="kz-btn primary" data-add-project><i class="icon-plus" aria-hidden="true"></i>Add project</button></div>
  </section>`;
  const project = (data.projects || []).find(item => item.slug === slug);
  const run = (data.running || []).find(item => item.project === slug);
  const total = project?.total || 0;
  const done = project?.done || 0;
  const next = project?.next || (total > 0 && done === total ? "All planned tasks are complete." : "Open the plan to review the next milestone.");
  return `<section class="workspace-spotlight" aria-labelledby="current-project">
    <div class="spotlight-main">
      <div class="spotlight-title"><span class="project-mark"><i class="icon-folder-open" aria-hidden="true"></i></span><h2 id="current-project" dir="auto">${esc(slug)}</h2></div>
      <p>${esc(next)}</p>
      <div class="spotlight-actions">
        ${run ? `<button type="button" class="kz-btn primary" data-open="${esc(run.id)}">Open active run</button>` : ""}
        <button type="button" class="kz-btn ${run ? "" : "primary"}" data-plan="${esc(slug)}">Open plan<i class="icon-arrow-up-right" aria-hidden="true"></i></button>
        <button type="button" class="kz-btn workspace-quiet" data-chat>Open conversation</button>
      </div>
    </div>
    <div class="spotlight-progress">
      <div><span>Plan progress</span><strong>${total ? Math.round(done / total * 100) + "%" : "No tasks yet"}</strong></div>
      ${total ? `<progress aria-label="Plan tasks completed" value="${done}" max="${total}"></progress><span>${done} of ${total} tasks complete</span>` : ""}
    </div>
  </section>`;
}

function activitySection() {
  const groups = [inboxCard(), nowCard(), queueCard(), recentCard()].filter(Boolean);
  return `<section class="workspace-activity" aria-labelledby="workspace-activity"><h2 id="workspace-activity">Activity</h2>
    ${groups.join("") || '<div class="workspace-empty"><i class="icon-activity" aria-hidden="true"></i><div><strong>No activity yet</strong><p>Runs, approvals and recent conversations will appear here.</p></div></div>'}
  </section>`;
}

function nowCard() {
  const runs = data.running || [], g = data.gate || {};
  if (!runs.length) return "";
  const rows = runs.map(r => {
    const state = r.stopping ? "Stopping" : r.paused ? "Paused" : r.pause_requested ? "Pausing" : "Running";
    const b = r.budget || {}, ratio = Math.min(1, b.ratio || 0), u = r.usage || {};
    const lanes = (r.lanes || []).filter(l => ["running", "waiting"].includes(l.state));
    return `<div class="kz-row" style="flex-wrap:wrap"><span class="kz-dot ${r.paused ? "warn" : "live"}"></span>
      <div class="grow"><div class="title">${esc(r.title)}</div><div class="sub">${state} · ${esc(r.project || "General")} · ${fmtTokens((u.prompt || 0) + (u.completion || 0))} tokens · ${u.calls || 0} model calls · ${u.tools || 0} tools · ${fmtMs((u.elapsed || 0) * 1000)}</div>
        ${b.max_tokens || b.max_seconds ? `<div class="kz-bar ${ratio >= 1 ? "bad" : ratio >= .8 ? "warn" : ""}" title="Budget ${Math.round(ratio * 100)}%" style="margin-top:6px"><i style="width:${ratio * 100}%"></i></div>` : ""}
        ${lanes.length ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">${lanes.map(l => `<span class="kz-chip live">${esc(l.id)} · ${esc(shortAgent(l.agent))}<button class="kz-btn" style="padding:0 5px;font-size:10px" data-lane="${esc(l.task_id)}" data-session="${esc(r.id)}" title="Cancel this lane">✕</button></span>`).join("")}</div>` : ""}</div>
      <button class="kz-btn" data-open="${esc(r.id)}">Open</button>
      <button class="kz-btn" data-pause="${esc(r.id)}" data-state="${r.paused || r.pause_requested ? "resume" : "pause"}" ${r.stopping ? "disabled" : ""}>${r.pause_requested && !r.paused ? "Cancel pause" : r.paused ? "Resume" : "Pause"}</button>
      <button class="kz-btn danger" data-stop="${esc(r.id)}" ${r.stopping ? "disabled" : ""}>${r.stopping ? "Stopping…" : "Stop"}</button></div>`;
  }).join("");
  return `<section class="kz-card"><h3>Active runs <small>model requests ${g.active || 0}/${g.limit || 0} (max ${g.max_limit || "?"}) · ${g.queued || 0} waiting${g.cooldown_seconds ? ` · rate-limit cooldown ${g.cooldown_seconds}s` : ""}</small></h3>
    ${rows || '<div class="kz-empty">No runs in progress.</div>'}</section>`;
}

function inboxCard() {
  const items = data.approvals || [], failed = (data.recent || []).filter(r => r.error);
  const bad = (health?.checks || []).filter(c => !c.ok && !c.optional);
  const rows = [
    ...items.map(a => `<div class="kz-row"><span class="kz-dot warn"></span><div class="grow"><div class="title">${esc(shortAgent(a.agent))} wants to ${a.new_file ? "create" : "edit"} ${esc(a.path)}</div><div class="sub">${esc(a.project || "")} · ${ago(a.t)}</div></div><button class="kz-btn primary" data-review="${esc(a.id)}">Review</button></div>`),
    ...bad.map(c => `<div class="kz-row"><span class="kz-dot bad"></span><div class="grow"><div class="title">${esc(c.title)}</div><div class="sub">${esc(c.detail)}</div></div></div>`),
    ...failed.slice(0, 3).map(r => `<div class="kz-row"><span class="kz-dot bad"></span><div class="grow"><div class="title">${esc(r.title)}</div><div class="sub">${esc((r.last || "").replace(/^⚠️\s*/, ""))}</div></div><button class="kz-btn" data-open="${esc(r.id)}">Open</button></div>`)];
  return rows.length ? `<section class="kz-card"><h3>Needs attention <small>${rows.length}</small></h3>${rows.join("")}</section>` : "";
}

function queueCard() {
  const q = data.queue || [];
  if (!q.length) return "";
  return `<section class="kz-card"><h3>Run queue <small>${q.length} waiting</small></h3>${q.map((i, n) => `<div class="kz-row"><span class="kz-chip">#${n + 1}</span><div class="grow"><div class="title">${esc(i.text)}</div><div class="sub">${esc(i.project || "general")} · queued ${ago(i.t)}</div></div><button class="kz-btn danger" data-unqueue="${esc(i.qid)}">Remove</button></div>`).join("") ||
    '<div class="kz-empty">Messages sent while a run is busy wait here and start automatically.</div>'}</section>`;
}

function spendCard() {
  const u = data.usage || {}, t = u.today || {}, w = u.week || {};
  const days = Array.from({length: 7}, (_, i) => { const d = new Date(Date.now() - (6 - i) * 864e5); return d.toISOString().slice(0, 10); });
  const local = d => { const x = new Date(d + "T12:00:00"); return x.toLocaleDateString([], {weekday: "short"}); };
  const byDay = u.by_day || {}, max = Math.max(1, ...days.map(d => byDay[d] || 0));
  const top = (obj, n = 5) => Object.entries(obj || {}).sort((a, b) => b[1] - a[1]).slice(0, n);
  return `<section class="kz-card"><h2>Token usage</h2>
    <div class="kz-stat"><div><b>${fmtTokens((t.prompt || 0) + (t.completion || 0))}</b><span>today · ${t.calls || 0} calls</span></div><div><b>${fmtTokens((w.prompt || 0) + (w.completion || 0))}</b><span>7 days</span></div><div><b>${w.prompt ? Math.round((w.completion || 0) / w.prompt * 100) : 0}%</b><span>output / input</span></div></div>
    <div class="kz-chart" role="img" aria-label="Tokens per day, last 7 days">${days.map(d => `<div title="${d}: ${fmtTokens(byDay[d] || 0)}"><i style="height:${(byDay[d] || 0) / max * 100}%"></i><span>${local(d)}</span></div>`).join("")}</div>
    <div class="kz-grid" style="grid-template-columns:1fr 1fr;margin-top:10px"><div><div class="kz-eyebrow" style="margin-bottom:4px">By agent</div><ul class="kz-list">${top(u.by_agent).map(([k, v]) => `<li><span>${esc(shortAgent(k))}</span><span>${fmtTokens(v)}</span></li>`).join("") || '<li class="kz-muted">no data yet</li>'}</ul></div>
    <div><div class="kz-eyebrow" style="margin-bottom:4px">By project</div><ul class="kz-list">${top(u.by_project).map(([k, v]) => `<li><span>${esc(k)}</span><span>${fmtTokens(v)}</span></li>`).join("") || '<li class="kz-muted">no data yet</li>'}</ul></div></div></section>`;
}

function projectsCard() {
  const projects = data.projects || [];
  if (!projects.length) return "";
  const selected = currentProject();
  return `<section class="workspace-projects" aria-labelledby="workspace-projects">
    <div class="workspace-project-heading"><h2 id="workspace-projects">Projects</h2>
      <button type="button" class="kz-btn workspace-quiet" data-add-project title="Add project" aria-label="Add project"><i class="icon-plus" aria-hidden="true"></i></button></div>
    <ul>${projects.map(project => {
      const slug = esc(project.slug);
      const current = project.slug === selected;
      return `<li>
        <button type="button" class="workspace-project-select" data-select-project="${slug}" ${current ? 'aria-current="true"' : ""}>
          <i class="icon-${current ? "folder-open" : "folder"}" aria-hidden="true"></i>
          <div><strong dir="auto">${slug}</strong>
          <span>${project.total ? `${project.done} of ${project.total} tasks complete` : "No tasks yet"}</span></div>
        </button>
        <button type="button" class="kz-btn workspace-quiet" data-plan="${slug}" title="Open plan" aria-label="Open plan for ${slug}"><i class="icon-arrow-up-right" aria-hidden="true"></i></button>
      </li>`;
    }).join("")}</ul></section>`;
}

function healthCard() {
  const h = health || {checks: []};
  const summary = h.error ? "Unavailable" : h.ok ? "Ready" : h.checks?.length ? "Needs attention" : "Checking";
  return `<section class="kz-card"><h2>Health <small>${summary}</small></h2>
    ${(h.checks || []).map(c => `<div class="kz-row"><span class="kz-dot ${c.ok ? "ok" : "bad"}"></span><div class="grow"><div class="title">${esc(c.title)}</div><div class="sub">${esc(c.detail)}</div></div></div>`).join("") || `<div class="kz-empty">${esc(h.error || "Checking…")}</div>`}
    <div style="margin-top:10px"><button class="kz-btn" data-recheck>Check again</button></div></section>`;
}

function recentCard() {
  const r = data.recent || [];
  if (!r.length) return "";
  return `<section class="kz-card"><h3>Recent conversations</h3>${r.map(s => `<div class="kz-row"><span class="kz-dot ${s.error ? "bad" : "ok"}"></span><div class="grow"><div class="title">${esc(s.title)}</div><div class="sub">${esc(s.project || "general")} · ${ago(s.t)}</div></div><button class="kz-btn" data-open="${esc(s.id)}">Open</button><button class="kz-btn" data-trace="${esc(s.id)}">Trace</button></div>`).join("") || '<div class="kz-empty">No conversations yet.</div>'}</section>`;
}

function wire(body) {
  body.onclick = async e => {
    const t = e.target.closest("button"); if (!t) return;
    const d = t.dataset;
    if (d.open) { if (await window.openSession(d.open)) window.showChat(); return; }
    if ("chat" in d) return window.showChat();
    if ("addProject" in d) return window.openNewProject();
    const project = d.selectProject || d.plan;
    if (project) {
      if (currentProject() !== project) {
        if ($("#newProjectBtn").disabled) return toast("Finish or stop the current run before switching projects.", "err");
        if (!window.switchProject(project)) return;
      }
      if (d.plan) setMode("plan");
      else body.querySelector(`[data-select-project="${CSS.escape(project)}"]`)?.focus({preventScroll: true});
      return;
    }
    if (d.trace) { window.dispatchEvent(new CustomEvent("kryzen:trace", {detail: {id: d.trace}})); setMode("trace"); return; }
    if (d.review) return openReview(d.review);
    if (d.stop || d.pause) {
      t.disabled = true;
      const run = data.running.find(item => item.id === (d.stop || d.pause));
      const r = await api(d.stop ? "/api/stop" : "/api/run-control",
        {id: d.stop || d.pause, action: d.state, turn_seq: run?.turn_seq});
      if (!r.ok) toast(r.error || r.errors?.join(" ") || "Could not update the run", "err");
      await refresh();
      if (t.isConnected) t.disabled = false;
      return;
    }
    if (d.lane) { if (!confirm("Cancel this lane? Tasks that depend on it will be blocked.")) return; await api("/api/lane", {id: d.session, task_id: d.lane, action: "cancel"}); toast("Lane cancelled", "ok"); return refresh(); }
    if (d.unqueue) { await api("/api/queue/cancel", {qid: d.unqueue}); return refresh(); }
    if ("recheck" in d) { health = null; return refresh(true); }
  };
}

// ---------------------------------------------------------------- Skills tab
async function renderSkills(body) {
  body.innerHTML = '<div class="kz-empty">Loading skills…</div>';
  const [ins, imp] = await Promise.all([api("/api/skills2/insights"), api("/api/skills2/importable")]);
  if (!body.isConnected) return;
  if (ins.error) { body.innerHTML = `<div class="kz-empty" role="alert">${esc(ins.error)}</div>`; return; }
  const drafts = ins.drafts || [];
  body.innerHTML = `<div class="kz-grid">
    <section class="kz-card full"><h3>Usage <small>${ins.skills.length} skills · ${ins.unused_assigned.length} assigned but never read</small></h3>
      <div style="overflow:auto"><table style="width:100%;border-collapse:collapse;font-size:12.5px"><thead><tr style="text-align:left;color:var(--faint);font-size:11px;letter-spacing:.08em;text-transform:uppercase;border-bottom:2px solid var(--color-divider)"><th style="padding:6px 4px">Skill</th><th>Reads</th><th>OK</th><th>Last used</th><th>Used by</th><th>Versions</th><th></th></tr></thead>
      <tbody>${ins.skills.map(s => `<tr style="border-bottom:1px solid rgba(243,242,242,.12)"><td style="padding:7px 4px"><b>${esc(s.name)}</b><div class="kz-muted">${esc(s.description).slice(0, 90)}</div></td>
        <td>${s.reads}</td><td>${s.ok_rate == null ? "—" : Math.round(s.ok_rate * 100) + "%"}</td><td>${s.last_used ? ago(s.last_used) : "never"}</td>
        <td class="kz-muted">${Object.keys(s.used_by).map(shortAgent).join(", ") || (s.assigned.length ? "assigned: " + s.assigned.map(shortAgent).join(", ") : "unassigned")}</td>
        <td>${s.versions ? `<button class="kz-btn" data-versions="${esc(s.name)}">${s.versions}</button>` : "0"}</td>
        <td style="white-space:nowrap"><button class="kz-btn" data-test="${esc(s.name)}" data-prompt="${esc(s.test)}" title="${s.test ? "Run the saved test prompt" : "Set a test prompt"}">${s.test ? "Test" : "Set test"}</button></td></tr>`).join("")}</tbody></table></div></section>
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
  if (!body.isConnected || slug !== currentProject()) return;
  if (m.error) { body.innerHTML = `<div class="kz-empty" role="alert">${esc(m.error)}</div>`; return; }
  const entries = (m.content.match(/^- \d{4}-\d{2}-\d{2} \(\w+\) .+$/gm) || []).length;
  body.innerHTML = `<section class="kz-card"><h3>${esc(slug)} · project memory <small>${entries} facts · .devpilot/memory.md</small></h3>
    <p class="kz-muted" style="margin:0 0 10px">Decisions, conventions and gotchas the agents learned. Relevant lines are given to the team each run; agents add more with <code>remember</code>. One fact per line: <code>- YYYY-MM-DD (decision) text</code>.</p>
    <textarea class="kz-textarea" id="kzMem" spellcheck="false" aria-label="Project memory">${esc(m.content || "# Project memory\n\n")}</textarea>
    <div style="display:flex;gap:8px;margin-top:10px;align-items:center"><button class="kz-btn primary" id="kzMemSave">Save</button><span class="kz-muted" id="kzMemState">${m.exists ? "" : "Not created yet — agents create it on their first remember."}</span></div></section>`;
  let revision = m.revision;
  const button = body.querySelector("#kzMemSave");
  const editor = body.querySelector("#kzMem");
  const status = body.querySelector("#kzMemState");
  status.setAttribute("role", "status");
  button.onclick = async () => {
    button.disabled = true;
    const r = await api("/api/memory", {slug, content: editor.value, revision});
    button.disabled = false;
    if (r.ok) { revision = r.revision; status.textContent = "Saved."; }
    else status.textContent = r.error || "Could not save. Reload the tab if the file changed.";
  };
}

// ---------------------------------------------------------------- Settings tab
async function renderSettings(body) {
  body.innerHTML = '<p class="kz-muted" role="status">Loading runtime settings…</p>';
  const r = await api("/api/settings/runtime");
  if (!body.isConnected) return;
  if (!r.settings) {
    body.innerHTML = `<p role="alert">${esc(r.error || "Runtime settings could not load.")}</p><button type="button" class="kz-btn">Try again</button>`;
    body.querySelector("button").onclick = () => renderSettings(body);
    return;
  }
  const s = r.settings;
  const group = (id, title, fields) => `<section class="settings-group" aria-labelledby="settings-${id}">
    <h3 id="settings-${id}">${title}</h3><div class="settings-fields">${fields}</div></section>`;
  const field = (name, label, control, help = "") => `<div class="settings-field">
    <label for="runtime-${name}">${label}</label>
    ${control(`id="runtime-${name}" name="${name}"${help ? ` aria-describedby="hint-${name}"` : ""}`)}
    ${help ? `<small id="hint-${name}">${help}</small>` : ""}
    </div>`;
  const text = (name, label, fallback, help = "") => field(name, label,
    attrs => `<input type="text" ${attrs} value="${esc(s[name] || fallback)}" spellcheck="false">`, help);
  const num = (name, label, help) => field(name, label,
    attrs => `<input type="number" required ${attrs} value="${esc(s[name])}" min="${r.limits?.[name]?.[0] ?? 0}" max="${r.limits?.[name]?.[1] ?? 999999999}">`, help);
  const toggle = (name, label) => `<label class="settings-toggle">
    <span>${label}</span><input type="checkbox" name="${name}" ${s[name] ? "checked" : ""}></label>`;
  const provider = field("active_provider", "Execution provider", attrs => `<select ${attrs}>
    <option value="auto" ${s.active_provider === "auto" ? "selected" : ""}>Automatic failover</option>
    <option value="openai" ${s.active_provider === "openai" ? "selected" : ""}>OpenAI-compatible API</option>
    <option value="ollama" ${s.active_provider === "ollama" ? "selected" : ""}>Ollama</option>
    <option value="agy" ${s.active_provider === "agy" ? "selected" : ""}>Antigravity CLI</option>
    </select>`, "Automatic failover tries the primary provider, then the secondary provider, then local Ollama.");

  body.innerHTML = `<section class="runtime-settings" aria-labelledby="runtimeSettingsTitle">
    <header class="settings-heading"><h2 id="runtimeSettingsTitle">Runtime settings</h2><p>Changes apply to new runs.</p></header>
    <form id="kzSettings">
      ${group("models", "Providers and models", `
        ${provider}
        ${text("openai_base_url", "API endpoint", "https://generativelanguage.googleapis.com/v1beta/openai/")}
        <p class="settings-note">${s.provider_key_configured ? "Provider key is configured in the server environment." : "Set the provider key in the server environment."}</p>
        ${text("tier_reasoning", "Reasoning model", "gemini-3.8-flash", "Orchestrator, Architect, and QA.")}
        ${text("tier_fast", "Fast model", "gemini-3-flash", "Build, Design, Content, and SEO.")}
        ${text("tier_compact", "Compact model", "gemini-3-flash", "Summarization and project memory.")}
        ${text("ollama_base_url", "Ollama endpoint", "http://127.0.0.1:11434", "Local fallback.")}
      `)}
      ${group("limits", "Run limits", `
        ${num("budget_tokens", "Token budget", "Warns at 80% and pauses at 100%. Enter 0 for unlimited. Resuming adds 50%.")}
        ${num("budget_hard_tokens", "Hard token cap", "Auto-resume stops at this limit. Enter 0 for no cap.")}
        ${num("budget_minutes", "Time budget (minutes)", "Enter 0 for unlimited.")}
        ${num("max_concurrency", "Parallel model requests", "Concurrency falls on rate limits and rises after successful calls.")}
        ${num("max_lanes", "Parallel task lanes", "Applies to task graphs.")}
      `)}
      ${group("context", "Conversation context", `
        ${num("mask_after", "Tool results to keep in full", "Older results become one-line stubs. Reopen them with read_blob.")}
        ${num("fold_after", "Chat messages to keep in full", "The compact model summarizes older messages.")}
        ${num("compact_at_tokens", "Compact after (prompt tokens)", "Summarizes earlier steps once the prompt exceeds this size.")}
      `)}
      ${group("automation", "Run automation and review", `
        ${num("auto_resume_seconds", "Auto-resume delay (seconds)", "Time to choose Keep paused after a budget pause.")}
        ${num("auto_continue_max", "Consecutive automatic continues", "Enter 0 to disable automatic continuation.")}
        <div class="settings-toggles">
          ${toggle("review_mode", "Require approval for every file write")}
          ${toggle("auto_resume", "Resume automatically after reaching the token budget")}
          ${toggle("auto_continue", "Continue after a step limit or temporary failure")}
          ${toggle("auto_screenshot", "Capture a screenshot after a project run")}
          ${toggle("auto_memory", "Update project memory after each run")}
        </div>
      `)}
      ${group("access", "Network access", `<div class="settings-toggles">
        ${toggle("allow_tailscale", "Allow Tailscale connections (*.ts.net and 100.64.0.0/10)")}
        ${toggle("allow_lan", "Allow local network connections (192.168.x.x and 10.x.x.x)")}
      </div>`)}
      <footer class="settings-actions">
        <span id="kzSetState" role="status"></span><button type="submit" class="kz-btn primary">Save settings</button>
      </footer>
    </form>
  </section>`;
  const form = body.querySelector("#kzSettings");
  form.onsubmit = async event => {
    event.preventDefault();
    const button = form.querySelector("button");
    const message = form.querySelector("#kzSetState");
    const settings = {};
    for (const input of form.elements) {
      if (!input.name) continue;
      settings[input.name] = input.type === "checkbox" ? input.checked
        : input.type === "number" ? input.valueAsNumber : input.value.trim();
    }
    button.disabled = true;
    message.dataset.state = "pending";
    message.textContent = "Saving…";
    const result = await api("/api/settings/runtime", {settings});
    button.disabled = false;
    message.dataset.state = result.ok ? "saved" : "error";
    message.textContent = result.ok ? "Saved. Applies to new runs." : (result.errors || [result.error]).join(" · ");
  };
}

// ---------------------------------------------------------------- lifecycle
function start() { tab = localStorage.getItem("kryzen.homeTab") || tab; shell(); render(); refresh(); clearInterval(timer); timer = setInterval(() => refresh(), 4000); }
onMode(m => { if (m === "home") start(); else clearInterval(timer); });
if (activeMode() === "home") start();
onEvent(ev => { if (activeMode() === "home" && ["turn_start", "turn_end", "approval_request", "approval_done", "budget", "queue_started", "task_state"].includes(ev.type)) setTimeout(refresh, 300); });
window.addEventListener("kryzen:inbox", () => refresh());
// Open a specific tab even when Home is already showing (palette, "Change budget" button).
window.addEventListener("kryzen:hometab", e => { tab = e.detail || tab; localStorage.setItem("kryzen.homeTab", tab); if (activeMode() === "home") { shell(); render(); refresh(); } else setMode("home"); });
window.addEventListener("kryzen:queue", () => refresh());
function updateProject() {
  if (activeMode() !== "home") return;
  const project = currentProject();
  if (tab === "overview" || ((tab === "shots" || tab === "memory") && project !== renderedProject)) render();
  renderedProject = project;
}
$("#proj").addEventListener("change", updateProject);
window.addEventListener("jarvis:projects-ready", updateProject);
document.addEventListener("visibilitychange", () => { if (!document.hidden && activeMode() === "home") refresh(); });
