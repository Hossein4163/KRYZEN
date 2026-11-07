// Command palette (Ctrl+K / ⌘K): every view, action, conversation, project, file and setting from the keyboard.
import {api, currentProject, currentSession, esc, setMode, toast} from "./core.js";

let box = null, items = [], shown = [], cursor = 0;

const VIEWS = [
  ["home", "Home dashboard"],
  ["mesh", "Agent mesh"],
  ["flow", "Flow studio & canvases"],
  ["plan", "Plan studio (docs/plan/PLAN.md)"],
  ["code", "Code workspace & IDE"],
  ["trace", "Trace — execution & telemetry"],
  ["control", "Control center"]
];

const CONTROL = [
  ["appearance", "Appearance & branding"],
  ["agents", "Agents & roles"],
  ["blocks", "Prompt blocks"],
  ["tools", "Tools"],
  ["skills", "Skills"],
  ["projects", "Projects"],
  ["models", "Models & API router"],
  ["network", "Network & Tailscale remote access"],
  ["services", "Services & system daemons"],
  ["advanced", "Advanced vault & code files"]
];

function collectStatic() {
  const out = [];
  const add = (group, label, run, hint = "") => out.push({group, label, run, hint});

  VIEWS.forEach(([m, l]) => add("Go to", l, () => {
    setMode(m);
  }));

  add("Actions", "New chat session", () => document.getElementById("newBtn")?.click(), "");
  add("Actions", "New project…", () => document.getElementById("newProjectBtn")?.click());
  add("Actions", "Continue selected project", () => (window.continueProject || window.continueProject)?.(), currentProject());
  add("Actions", "Pause / resume active run", () => document.getElementById("pauseBtn")?.click());
  add("Actions", "Stop active run", () => document.getElementById("stopBtn")?.click());
  add("Actions", "Trace active conversation", () => {
    window.dispatchEvent(new CustomEvent("kryzen:trace", {detail: {id: currentSession()}}));
    setMode("trace");
  });
  add("Actions", "Draft a skill from last run", async () => {
    const r = await api("/api/skills2/draft", {id: currentSession()});
    r.ok ? toast("Draft ready: " + r.draft.name + " (Home › Skills)", "ok") : toast((r.errors || [r.error]).join(" "), "err");
  });
  add("Actions", "Toggle review mode (approval queue)", async () => {
    const {settings} = await api("/api/settings/runtime");
    const r = await api("/api/settings/runtime", {settings: {review_mode: !settings.review_mode}});
    toast(r.ok ? `Review mode ${r.settings.review_mode ? "on" : "off"} for new runs` : (r.errors || []).join(" "), r.ok ? "ok" : "err");
  });

  CONTROL.forEach(([k, l]) => add("Settings", l, () => {
    setMode("control");
    if (window.showSection) window.showSection(k);
  }));

  add("Settings", "Runtime settings (budgets, models, review)", () => window.dispatchEvent(new CustomEvent("kryzen:hometab", {detail: "settings"})));
  add("Settings", "Project memory", () => window.dispatchEvent(new CustomEvent("kryzen:hometab", {detail: "memory"})));
  add("Go to", "Screenshots gallery", () => window.dispatchEvent(new CustomEvent("kryzen:hometab", {detail: "shots"})));

  return out;
}

async function collectDynamic() {
  const out = [];
  const add = (group, label, run, hint = "") => out.push({group, label, run, hint});

  try {
    const [sessions, projects] = await Promise.all([api("/api/sessions"), api("/api/projects")]);
    (sessions.sessions || []).forEach(s => add("Conversations", s.title || s.id, () => window.openSession?.(s.id), (s.running ? "● running · " : "") + (s.project || "")));
    (projects.folders || []).forEach(p => add("Projects", p, () => { window.switchProject?.(p); toast("Project: " + p, "ok"); }));
    const slug = currentProject();
    if (slug) {
      try {
        const tree = await api("/api/code/tree?slug=" + encodeURIComponent(slug));
        const files = (tree.entries || []).filter(e => typeof e === "string" && !e.endsWith("/"));
        files.slice(0, 2000).forEach(f => add("Files", f, async () => { setMode("code"); setTimeout(() => window.cwOpen?.(f), 150); }, slug));
      } catch (_) {}
    }
  } catch (_) {}

  return out;
}

function score(item, q) {
  if (!q) return 1;
  const t = (item.label + " " + item.group + " " + item.hint).toLowerCase();
  if (t.includes(q)) return 100 - t.indexOf(q);
  let i = 0;
  for (const ch of q) { i = t.indexOf(ch, i); if (i < 0) return 0; i++; }
  return 10;
}

function draw(q) {
  q = q.trim().toLowerCase();
  shown = items.map(it => [score(it, q), it]).filter(([s]) => s > 0).sort((a, b) => b[0] - a[0]).slice(0, 80).map(([, it]) => it);
  if (!q) shown.sort((a, b) => ["Go to", "Actions", "Conversations", "Projects", "Settings", "Files"].indexOf(a.group) - ["Go to", "Actions", "Conversations", "Projects", "Settings", "Files"].indexOf(b.group));
  cursor = Math.min(cursor, Math.max(0, shown.length - 1));
  let last = "";
  box.querySelector("ul").innerHTML = shown.map((it, n) => {
    const head = it.group !== last ? `<li class="group" role="presentation">${esc(it.group)}</li>` : ""; last = it.group;
    return head + `<li role="option" id="kzp${n}" data-n="${n}" aria-selected="${n === cursor}">${esc(it.label)}<small>${esc(it.hint)}</small></li>`;
  }).join("") || '<li class="group">No matches</li>';
  box.querySelector("input").setAttribute("aria-activedescendant", "kzp" + cursor);
  box.querySelector(`#kzp${cursor}`)?.scrollIntoView({block: "nearest"});
}

function close() { box?.remove(); box = null; }
async function run(it) {
  close();
  try {
    await it.run();
  } catch (e) {
    toast(e.message, "err");
  }
}

export function openPalette() {
  if (box) return close();
  box = document.createElement("div");
  box.className = "kz-palette";
  box.innerHTML = `<div class="kz-palette-box" role="dialog" aria-label="Command palette"><input type="text" placeholder="Type a view, setting, project or file…" role="combobox" aria-expanded="true" aria-controls="kzpList" aria-autocomplete="list"><ul id="kzpList" role="listbox"></ul></div>`;
  document.body.appendChild(box);
  const input = box.querySelector("input");
  box.addEventListener("mousedown", e => { if (e.target === box) close(); });
  box.querySelector("ul").addEventListener("click", e => { const li = e.target.closest("[data-n]"); if (li) run(shown[+li.dataset.n]); });
  input.addEventListener("input", () => { cursor = 0; draw(input.value); });
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); cursor = Math.min(shown.length - 1, cursor + 1); draw(input.value); }
    else if (e.key === "ArrowUp") { e.preventDefault(); cursor = Math.max(0, cursor - 1); draw(input.value); }
    else if (e.key === "Enter" && shown[cursor]) { e.preventDefault(); run(shown[cursor]); }
  });
  input.focus();

  // Instant zero-latency render of static navigation & settings items
  items = collectStatic();
  draw("");

  // Background fetch of conversations, projects, and files
  collectDynamic().then(dyn => {
    if (box) {
      items = [...collectStatic(), ...dyn];
      draw(input.value);
    }
  });
}

document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
});
window.addEventListener("kryzen:palette", openPalette);
