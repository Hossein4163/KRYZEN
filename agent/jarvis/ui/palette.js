// Command palette (Ctrl+K / ⌘K): every view, action, conversation, project, file and setting from the keyboard.
import {api, currentProject, currentSession, esc, setMode, toast} from "./core.js";

let dialog = null;

const GROUP_ICONS = {
  "Go to": "arrow-up-right", Actions: "list-todo", Conversations: "message-square-plus",
  Projects: "folder", Settings: "sliders-horizontal", Files: "file-code"
};

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
  add("Actions", "Continue selected project", () => window.continueProject?.(), currentProject());
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
    (sessions.sessions || []).forEach(s => add("Conversations", s.title || s.id, async () => { if (await window.openSession(s.id)) window.showChat(); }, (s.running ? "● running · " : "") + (s.project || "")));
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
  const label = item.label.toLowerCase();
  if (label === q) return 300;
  const titleMatch = label.indexOf(q);
  if (titleMatch >= 0) return 200 + 1 / (1 + titleMatch);
  const searchable = (label + " " + item.group + " " + item.hint).toLowerCase();
  const match = searchable.indexOf(q);
  if (match >= 0) return 100 + 1 / (1 + match);
  let i = 0;
  for (const ch of q) { i = searchable.indexOf(ch, i); if (i < 0) return 0; i++; }
  return 10;
}

export function openPalette() {
  if (dialog?.open) return dialog.close();
  dialog?.remove();
  const panel = document.createElement("dialog");
  panel.className = "workspace-search";
  panel.setAttribute("aria-labelledby", "workspaceSearchTitle");
  panel.innerHTML = `
    <div class="workspace-search-content">
      <header class="workspace-search-header">
        <h2 id="workspaceSearchTitle">Search workspace</h2>
        <button type="button" class="btn" data-search-close aria-label="Close search">Esc</button>
      </header>
      <label class="workspace-search-field">
        <i class="icon-search" aria-hidden="true"></i>
        <input id="workspaceSearchQuery" type="search" placeholder="Commands, projects, files…" aria-label="Search workspace"
          autocomplete="off" spellcheck="false" role="combobox" aria-expanded="true"
          aria-controls="workspaceSearchResults" aria-autocomplete="list" autofocus>
      </label>
      <div id="workspaceSearchResults" class="workspace-search-results" role="listbox" aria-label="Search results"></div>
      <div class="workspace-search-empty" role="status" hidden>No matches. Try a different search.</div>
      <footer class="workspace-search-footer"><span><kbd>↑</kbd> <kbd>↓</kbd> Navigate</span><span><kbd>↵</kbd> Open</span></footer>
    </div>`;
  document.body.append(panel);
  dialog = panel;
  const input = panel.querySelector("input");
  const results = panel.querySelector('[role="listbox"]');
  const empty = panel.querySelector(".workspace-search-empty");
  let items = collectStatic();
  let shown = [];
  let cursor = 0;

  function select(index) {
    results.querySelector('[aria-selected="true"]')?.setAttribute("aria-selected", "false");
    cursor = Math.max(0, Math.min(shown.length - 1, index));
    const option = results.querySelector(`[data-result="${cursor}"]`);
    if (option) {
      option.setAttribute("aria-selected", "true");
      input.setAttribute("aria-activedescendant", option.id);
      option.scrollIntoView({block: "nearest"});
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function draw(keepSelection = false) {
    const previous = keepSelection ? shown[cursor] : null;
    const query = input.value.trim().toLowerCase();
    const ranked = items.map(item => [score(item, query), item])
      .filter(([points]) => points > 0).sort((a, b) => b[0] - a[0]).slice(0, 80);
    const groups = new Map();
    for (const [, item] of ranked) {
      if (!groups.has(item.group)) groups.set(item.group, []);
      groups.get(item.group).push(item);
    }
    const orderedGroups = query ? [...groups.keys()] : Object.keys(GROUP_ICONS).filter(group => groups.has(group));
    shown = orderedGroups.flatMap(group => groups.get(group));
    let index = 0;
    results.innerHTML = orderedGroups.map((group, groupIndex) => `
      <div class="workspace-search-group" role="group" aria-labelledby="searchGroup${groupIndex}">
        <div class="workspace-search-label" id="searchGroup${groupIndex}">${esc(group)}</div>
        ${groups.get(group).map(item => {
          const id = index++;
          return `<div class="workspace-search-option" role="option" id="searchResult${id}" data-result="${id}" aria-selected="false">
            <i class="icon-${GROUP_ICONS[group]}" aria-hidden="true"></i>
            <span dir="auto">${esc(item.label)}</span>
            ${item.hint ? `<small dir="auto">${esc(item.hint)}</small>` : ""}
          </div>`;
        }).join("")}
      </div>`).join("");
    empty.hidden = shown.length > 0;
    select(previous ? shown.indexOf(previous) : 0);
  }

  async function run(item) {
    panel.close();
    try {
      await item.run();
    } catch (error) {
      toast(error.message, "err");
    }
  }

  panel.addEventListener("close", () => {
    if (dialog === panel) dialog = null;
    panel.remove();
  }, {once: true});
  panel.querySelector("[data-search-close]").onclick = () => panel.close();
  panel.addEventListener("keydown", event => {
    if (event.key === "Escape" && !event.isComposing) {
      event.preventDefault();
      panel.close();
    }
  });
  panel.addEventListener("click", event => {
    if (event.target === panel) panel.close();
  });
  results.addEventListener("click", event => {
    const option = event.target.closest("[data-result]");
    if (option) run(shown[Number(option.dataset.result)]);
  });
  input.addEventListener("input", () => draw());
  input.addEventListener("keydown", event => {
    if (event.isComposing) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      select(cursor + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Enter" && shown[cursor]) {
      event.preventDefault();
      run(shown[cursor]);
    }
  });
  panel.showModal();
  draw();
  collectDynamic().then(dynamic => {
    if (dialog !== panel || !panel.open) return;
    items.push(...dynamic);
    draw(true);
  });
}

document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "k") {
    event.preventDefault();
    if (!event.repeat) openPalette();
  }
});
window.addEventListener("kryzen:palette", openPalette);
