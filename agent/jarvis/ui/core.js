// Shared helpers for the K.R.Y.Z.E.N view modules. The legacy page script defines api(), toast(), send() etc.
// as globals; modules use them through these thin wrappers so a missing global never crashes a view.
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

export async function api(path, body) {
  if (typeof window.api === "function") return window.api(path, body);
  const r = await fetch(path, body ? {method: "POST", headers: {"Content-Type": "application/json", "X-Jarvis": "1"}, body: JSON.stringify(body)} : {});
  return r.json();
}
export async function text(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`Request failed (${r.status})`);
  return r.text();
}
export const toast = (msg, cls) => (typeof window.toast === "function" ? window.toast(msg, cls) : console.log(msg));

export function fmtTokens(n) {
  n = Number(n) || 0;
  return n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k" : String(n);
}
export function fmtMs(ms) {
  if (ms == null) return "—";
  return ms >= 60000 ? `${Math.floor(ms / 60000)}m ${Math.round(ms % 60000 / 1000)}s` : ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : ms + "ms";
}
export function ago(t) {
  if (!t) return "never";
  const s = Math.max(0, Date.now() / 1000 - t);
  return s < 60 ? "just now" : s < 3600 ? Math.floor(s / 60) + "m ago" : s < 86400 ? Math.floor(s / 3600) + "h ago" : Math.floor(s / 86400) + "d ago";
}
export const clock = t => new Date(t * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false});
export const shortAgent = a => !a ? "K.R.Y.Z.E.N" : a === "DevPilot Orchestrator" ? "Orchestrator" : a.replace(/ Agent$/, "");

// Current session/project from the legacy script (globals declared with let are reachable by name).
export function currentSession() { try { return sessionId || localStorage.getItem("jarvis.session"); } catch (_) { return null; } }
export function currentProject() { return $("#proj")?.value || ""; }
export function setMode(mode) { window.jarvisStudio?.setMode(mode); }

export function onEvent(fn) { window.addEventListener("kryzen:event", e => fn(e.detail)); }
export function onMode(fn) { window.addEventListener("kryzen:mode", e => fn(e.detail)); }
export function activeMode() {
  const b = document.body.classList;
  return b.contains("home-mode") ? "home" : b.contains("trace-mode") ? "trace" : "";
}

// Render a unified diff with add/remove colouring (safe: text only).
export function diffHtml(diff) {
  if (!diff) return '<div class="kz-empty" style="padding:10px">No changes.</div>';
  return diff.split("\n").map(line => {
    const cls = line.startsWith("@@") ? "hunk" : line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : "";
    return `<div class="${cls}">${esc(line) || " "}</div>`;
  }).join("");
}

export function download(name, content, type = "application/json") {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const a = Object.assign(document.createElement("a"), {href: url, download: name});
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
