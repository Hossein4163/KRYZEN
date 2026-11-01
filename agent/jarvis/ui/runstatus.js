// Live run status above the chat: what every agent is doing right now (and for how long), plus a clear
// banner whenever the run is paused — by you or by the token budget — with the buttons to continue.
import {$, api, currentSession, esc, fmtTokens, onEvent, setMode, shortAgent, toast} from "./core.js";

const S = {agents: new Map(), paused: null, running: false, rate: null, auto: null};
const left = at => Math.max(0, Math.ceil(at - Date.now() / 1000));
let strip = null, timer = 0;

function mount() {
  const chat = $("#chat");
  if (!chat || strip) return;
  strip = document.createElement("div");
  strip.className = "kz-runstatus";
  strip.setAttribute("aria-live", "polite");
  chat.parentNode.insertBefore(strip, chat);
  strip.addEventListener("click", async e => {
    const b = e.target.closest("button"); if (!b) return;
    const id = currentSession();
    if (b.dataset.act === "resume") {
      const r = await api("/api/run-control", {id, action: "resume"});
      if (r.ok === false) toast(r.error || (r.errors || []).join(" "), "err");
    } else if (b.dataset.act === "stop") {
      await api("/api/stop", {id});
    } else if (b.dataset.act === "hold") {
      await api("/api/run-control", {id, action: "hold"});
    } else if (b.dataset.act === "cancel-auto") {
      await api("/api/auto-continue/cancel", {id});
    } else if (b.dataset.act === "continue-now") {
      await api("/api/auto-continue/cancel", {id});
      if (typeof window.continueProject === "function") window.continueProject();
    } else if (b.dataset.act === "budget") {
      window.dispatchEvent(new CustomEvent("kryzen:hometab", {detail: "settings"}));
    } else if (b.dataset.act === "trace") setMode("trace");
  });
}

const since = t => { const s = Math.max(0, Math.round(Date.now() / 1000 - t)); return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`; };

function set(agent, what, t, extra = {}) {
  if (!agent) return;
  const cur = S.agents.get(agent);
  // Keep the start time while the same activity continues (e.g. streaming tokens).
  S.agents.set(agent, {what, t: cur && cur.what === what ? cur.t : (t || Date.now() / 1000), ...extra});
}

function render() {
  if (!strip) return;
  if (!S.running && !S.paused && !S.auto) { strip.hidden = true; return; }
  strip.hidden = false;
  let banner = "";
  if (S.paused) {
    const b = S.paused;
    const auto = b.reason === "budget" && b.autoAt && !b.held ? left(b.autoAt) : null;
    banner = b.reason === "budget"
      ? `<div class="kz-paused budget" role="alert"><div><b>⏸ Paused — token budget reached${auto != null ? ` · resuming in ${auto}s` : ""}</b><span>${fmtTokens(b.tokens)} of ${fmtTokens(b.max_tokens)} tokens used in this run. ${b.hardCap ? "The hard cap is reached, so it will not resume by itself." : auto != null ? "It continues automatically with more budget." : "Resume to keep going (allows +50% or your new budget)."}</span></div>
         <div class="kz-paused-actions"><button class="kz-btn primary" data-act="resume">${auto != null ? "Resume now" : "Resume"}</button>${auto != null ? '<button class="kz-btn" data-act="hold">Keep paused</button>' : ""}<button class="kz-btn" data-act="budget">Change budget</button><button class="kz-btn danger" data-act="stop">Stop</button></div></div>`
      : `<div class="kz-paused" role="alert"><div><b>⏸ Paused</b><span>Agents wait at their next safe step. Nothing is lost.</span></div>
         <div class="kz-paused-actions"><button class="kz-btn primary" data-act="resume">Resume</button><button class="kz-btn danger" data-act="stop">Stop</button></div></div>`;
  }
  const rows = [...S.agents.entries()].map(([agent, a]) => {
    const slow = !S.paused && Date.now() / 1000 - a.t > 90;
    return `<div class="kz-rs-row ${slow ? "slow" : ""}" style="--agent:${typeof color === "function" ? color(agent) : "var(--accent)"}">
      <span class="kz-rs-dot ${S.paused ? "paused" : ""}"></span><b>${esc(shortAgent(agent))}</b><span class="kz-rs-what" title="${esc(a.what)}">${esc(S.paused ? "paused · " + a.what : a.what)}</span>
      <span class="kz-rs-time">${since(a.t)}</span></div>`;
  }).join("");
  const rate = S.rate && S.rate.until > Date.now() / 1000 ? `<div class="kz-rs-note">⏳ NVIDIA rate limit — retrying in ${Math.ceil(S.rate.until - Date.now() / 1000)}s (parallel requests now ${S.rate.limit})</div>` : "";
  const slowNote = !S.paused && [...S.agents.values()].some(a => Date.now() / 1000 - a.t > 90)
    ? `<div class="kz-rs-note">Something is taking long — usually a slow model response or a long command. <button class="kz-btn" data-act="trace">Open trace</button></div>` : "";
  let autoBanner = "";
  if (S.auto) {
    const a = S.auto;
    autoBanner = a.state === "scheduled"
      ? `<div class="kz-paused auto" role="status"><div><b>↻ Continuing automatically in ${left(a.at)}s</b><span>${esc(a.reason)} · attempt ${a.attempt} of ${a.max}. Progress is saved; it picks up from the checkpoint.</span></div>
         <div class="kz-paused-actions"><button class="kz-btn primary" data-act="continue-now">Continue now</button><button class="kz-btn" data-act="cancel-auto">Cancel</button></div></div>`
      : a.state === "exhausted"
      ? `<div class="kz-paused" role="status"><div><b>Stopped auto-continuing</b><span>${a.max} automatic continues in a row — check the last reply or Trace, then say continue.</span></div><div class="kz-paused-actions"><button class="kz-btn" data-act="trace">Open trace</button></div></div>`
      : a.state === "failed" ? `<div class="kz-paused" role="alert"><div><b>Could not continue automatically</b><span>${esc(a.error || "")}</span></div></div>` : "";
  }
  strip.innerHTML = autoBanner + banner + (rows ? `<div class="kz-rs-list">${rows}</div>` : "") + rate + slowNote;
}

function reset() { S.agents.clear(); S.paused = null; S.rate = null; }
function resetAll() { reset(); S.auto = null; }

onEvent(ev => {
  mount();
  const a = ev.agent, t = ev.t;
  switch (ev.type) {
    case "turn_start": resetAll(); S.running = true; break;
    case "agent_start": S.running = true; set(a, "thinking about the task", t); break;
    case "request_state":
      if (ev.state === "queued") set(a, "waiting for a free model slot", t);
      else if (ev.state === "running") set(a, "waiting for the model's answer", t);
      break;
    case "thinking": set(a, "reasoning", S.agents.get(a)?.what === "reasoning" ? null : t); break;
    case "token": set(a, "writing", S.agents.get(a)?.what === "writing" ? null : t); break;
    case "tool_start": {
      const arg = ev.args && typeof ev.args === "object" ? (ev.args.path || ev.args.cmd || ev.args.query || ev.args.task || "") : "";
      set(a, `running ${ev.tool}${arg ? " · " + String(arg).replace(/\s+/g, " ").slice(0, 60) : ""}`, t);
      break;
    }
    case "tool_end": set(a, ev.ok ? "reading the result" : `${ev.tool} failed — deciding what to do`, t); break;
    case "approval_request": set(a, `waiting for your review of ${ev.path}`, t); break;
    case "agent_end": S.agents.delete(a); break;
    case "rate_limit": S.rate = {until: (t || Date.now() / 1000) + (ev.wait || 0), limit: ev.limit}; break;
    case "budget":
      if (ev.state === "paused") S.paused = {reason: "budget", tokens: ev.tokens, max_tokens: ev.max_tokens, hardCap: ev.hard_cap_reached,
        autoAt: ev.auto_resume_in != null ? (t || Date.now() / 1000) + ev.auto_resume_in : null};
      if (ev.state === "held" && S.paused) S.paused.held = true;
      if (ev.state === "auto_resumed") S.paused = null;
      break;
    case "auto_continue":
      S.auto = ev.state === "cancelled" ? null : {...ev, at: (t || Date.now() / 1000) + (ev.in || 0)};
      break;
    case "run_state":
      if (ev.state === "paused" || ev.state === "pause_requested") S.paused = S.paused || {reason: "user"};
      if (ev.state === "running") S.paused = null;
      break;
    case "turn_end": S.running = false; reset(); break;
  }
  // Freeze the mesh animation while paused so it does not look like work is happening.
  const g = document.getElementById("graph");
  if (g?.pauseAnimations) S.paused ? g.pauseAnimations() : g.unpauseAnimations();
  const was = document.body.classList.contains("run-paused");
  document.body.classList.toggle("run-paused", !!S.paused);
  if (was !== !!S.paused && typeof meshStatus === "function") meshStatus();
  render();
});

// A different conversation was opened: start clean (its events replay through onEvent).
window.addEventListener("kryzen:session", () => { resetAll(); S.running = false; render(); });
mount();
clearInterval(timer);
timer = setInterval(() => { if (S.running || S.paused || S.auto) render(); }, 1000);
