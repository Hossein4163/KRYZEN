// Projects sidebar: lists the workspace projects above the chat; a click opens that project's chats. + adds a folder.
import {$, api, esc, toast} from "./core.js";

const select = () => $("#proj");
const chats = () => $("#sessions");
let collapsed = false;

function syncRows() {
  const cur = select().value;
  const row = $("#projectList")?.querySelector(`[data-p="${CSS.escape(cur)}"]`);
  for (const b of document.querySelectorAll(".mn-proj")) {
    const on = b === row;
    b.setAttribute("aria-current", String(on));
    b.setAttribute("aria-expanded", String(on && !collapsed));
    b.querySelector("i").className = on && !collapsed ? "icon-folder-open" : "icon-folder";
  }
  if (row) row.closest("li").append(chats());
  chats().hidden = collapsed || !row;
}

function renderProjects() {
  const parked = chats();
  $("#projectsPanel").append(parked); // keep the chat list alive while the rows are rebuilt
  $("#projectList").innerHTML = [...select().options].map(o =>
    `<li><div class="mn-proj-row"><button type="button" class="mn-proj" data-p="${esc(o.value)}" title="${esc(o.value)}. Right-click for options."><i class="icon-folder"></i><span>${esc(o.value)}</span></button><button type="button" class="mn-proj-more" data-more="${esc(o.value)}" aria-label="Options for ${esc(o.value)}" aria-haspopup="menu"><i class="icon-ellipsis"></i></button></div></li>`).join("");
  syncRows();
}

$("#projectList").addEventListener("click", e => {
  const more = e.target.closest("[data-more]");
  if (more) { e.stopPropagation(); const r = more.getBoundingClientRect(); return openMenu(more.dataset.more, r.left, r.bottom + 2, more); }
  const b = e.target.closest(".mn-proj"); if (!b) return;
  if (select().disabled) return toast("Finish or stop the current run first.", "err");
  if (b.dataset.p === select().value) { collapsed = !collapsed; return syncRows(); }
  collapsed = false;
  window.switchProject?.(b.dataset.p);
  syncRows();
});
window.addEventListener("jarvis:projects-ready", renderProjects);
select().addEventListener("change", syncRows);
// openSession can change the project without a change event; its chat list reload is the signal.
new MutationObserver(syncRows).observe(chats(), {childList: true});

/* ---------- project menu (right-click) ---------- */
$("#projectList").addEventListener("contextmenu", e => {
  const row = e.target.closest(".mn-proj-row"); if (!row) return;
  e.preventDefault();
  openMenu(row.querySelector(".mn-proj").dataset.p, e.clientX, e.clientY, row.querySelector(".mn-proj"));
});

function selectProject(slug) {
  if (select().value !== slug) { collapsed = false; window.switchProject?.(slug); }
  return select().value === slug;
}
const MENU = [
  {label: "New chat", icon: "message-square-plus", run: slug => { if (selectProject(slug)) $("#newBtn").click(); }},
  {label: "Open in Code", icon: "code", run: slug => { if (selectProject(slug)) window.jarvisStudio?.setMode("code"); }},
  {label: "Open plan", icon: "list-todo", run: slug => { if (selectProject(slug)) window.jarvisStudio?.setMode("plan"); }},
  {label: "Rename…", icon: "pencil", run: renameProject},
  {label: "Copy path", icon: "copy", run: copyPath},
  {label: "Remove from list", icon: "x", danger: true, run: removeProject},
];
function openMenu(slug, x, y, origin) {
  closeMenu();
  const m = document.createElement("div");
  m.className = "mn-menu"; m.id = "projectMenu"; m.setAttribute("role", "menu"); m.setAttribute("aria-label", `Options for ${slug}`);
  m.innerHTML = `<div class="mn-menu-title">${esc(slug)}</div>` + MENU.map((it, i) => `<button type="button" role="menuitem" data-i="${i}" class="${it.danger ? "danger" : ""}"><i class="icon-${it.icon}"></i>${it.label}</button>`).join("");
  document.body.append(m);
  m.style.left = Math.min(x, innerWidth - m.offsetWidth - 8) + "px";
  m.style.top = Math.min(y, innerHeight - m.offsetHeight - 8) + "px";
  const items = [...m.querySelectorAll("button")];
  m.onclick = e => { const b = e.target.closest("[data-i]"); if (!b) return; closeMenu(); MENU[+b.dataset.i].run(slug); };
  m.onkeydown = e => {
    const i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    if (e.key === "Escape") { closeMenu(); origin?.focus(); }
    if (e.key === "Tab") closeMenu();
  };
  items[0].focus();
  setTimeout(() => document.addEventListener("pointerdown", outsideMenu), 0);
}
function outsideMenu(e) { if (!e.target.closest("#projectMenu")) closeMenu(); }
function closeMenu() { $("#projectMenu")?.remove(); document.removeEventListener("pointerdown", outsideMenu); }

async function copyPath(slug) {
  const r = await api("/api/project/folders");
  try { await navigator.clipboard.writeText(`${r.workspace}/${slug}`); toast("Path copied", "ok"); }
  catch (_) { toast(`${r.workspace}/${slug}`, "ok"); }
}
async function refreshAfterChange(next) {
  await window.loadProjects?.();
  renderProjects();
  const fallback = [...select().options][0]?.value;
  const target = next && [...select().options].some(o => o.value === next) ? next : fallback;
  if (target) window.switchProject?.(target); else window.loadSessions?.("");
  syncRows();
}
function askDialog(html, onSubmit) {
  const dlg = document.createElement("dialog"); dlg.className = "studio-dialog"; dlg.innerHTML = html;
  document.body.append(dlg);
  dlg.querySelector("[data-cancel]").onclick = () => dlg.close();
  dlg.querySelector("form").onsubmit = async e => { e.preventDefault(); await onSubmit(dlg); };
  dlg.addEventListener("close", () => dlg.remove(), {once: true});
  dlg.showModal();
  return dlg;
}
function renameProject(slug) {
  const dlg = askDialog(`<form><h2>Rename project</h2><p>This renames the project in your workspace and keeps its chats.</p>
    <label class="studio-eyebrow" for="pjName">Name</label><input id="pjName" required maxlength="49" pattern="[a-z0-9][a-z0-9-]{1,48}" value="${esc(slug)}" autocomplete="off">
    <p id="pjErr" class="mn-picker-err" role="alert"></p><div class="studio-actions"><button class="btn primary">Rename</button><button type="button" class="btn" data-cancel>Cancel</button></div></form>`,
  async d => {
    const name = d.querySelector("#pjName").value.trim();
    if (name === slug) return d.close();
    const r = await api("/api/project/rename", {slug, name});
    if (!r.ok) { d.querySelector("#pjErr").textContent = r.error || (r.errors || []).join(" · ") || "Couldn't rename it."; return; }
    d.close();
    await refreshAfterChange(select().value === slug ? name : select().value);
    toast(`Renamed to ${name}`, "ok");
  });
  dlg.querySelector("#pjName").select();
}
function removeProject(slug) {
  askDialog(`<form><h2>Remove ${esc(slug)} from the list?</h2><p>Its files and chats stay on your computer. Add the folder again with + to bring it back.</p>
    <p id="pjErr" class="mn-picker-err" role="alert"></p><div class="studio-actions"><button class="btn primary">Remove from list</button><button type="button" class="btn" data-cancel>Cancel</button></div></form>`,
  async d => {
    const r = await api("/api/project/remove", {slug});
    if (!r.ok) { d.querySelector("#pjErr").textContent = r.error || (r.errors || []).join(" · ") || "Couldn't remove it."; return; }
    d.close();
    await refreshAfterChange(select().value === slug ? "" : select().value);
    toast(`${slug} removed from the list`, "ok");
  });
}

/* ---------- folder picker ---------- */
function openPicker() {
  if ($("#projectPicker")) return;
  const dlg = document.createElement("dialog");
  dlg.id = "projectPicker"; dlg.className = "studio-dialog mn-picker"; dlg.setAttribute("aria-labelledby", "pkTitle");
  dlg.innerHTML = `<header><h2 id="pkTitle">Add a project</h2><p>Open a folder from this computer, or start a new one.</p></header>
    <div class="mn-picker-path"><button type="button" class="btn mn-icon-btn" id="pkUp" title="Parent folder" aria-label="Parent folder"><i class="icon-arrow-up"></i></button><span id="pkPath" dir="ltr"></span></div>
    <ul class="mn-picker-list" id="pkList" aria-label="Folders"></ul>
    <p class="mn-picker-note" id="pkNote"></p><p class="mn-picker-err" id="pkErr" role="alert"></p>
    <footer><button type="button" class="btn primary" id="pkUse">Use this folder</button><button type="button" class="btn" id="pkCancel">Cancel</button><span class="grow"></span><button type="button" class="btn" id="pkNew"><i class="icon-plus"></i>New project</button></footer>`;
  document.body.append(dlg);
  const q = s => dlg.querySelector(s);
  let cur = null;
  async function go(path) {
    q("#pkErr").textContent = "";
    const r = await api("/api/project/folders?path=" + encodeURIComponent(path || ""));
    if (r.error) { q("#pkErr").textContent = r.error; return; }
    cur = r;
    q("#pkPath").textContent = r.path;
    q("#pkUp").disabled = !r.parent;
    q("#pkList").innerHTML = r.dirs.map(d => `<li><button type="button" data-path="${esc(d.path)}"><i class="icon-folder"></i>${esc(d.name)}</button></li>`).join("") || '<li class="empty">No sub-folders here.</li>';
    q("#pkList").scrollTop = 0;
    const inside = r.path === r.workspace || r.path.startsWith(r.workspace + "/");
    q("#pkNote").textContent = inside ? "This folder is in your workspace." : "Agents will be able to read and change everything in this folder.";
    q("#pkNote").classList.toggle("warn", !inside);
  }
  q("#pkList").onclick = e => { const b = e.target.closest("[data-path]"); if (b) go(b.dataset.path); };
  q("#pkUp").onclick = () => cur?.parent && go(cur.parent);
  q("#pkCancel").onclick = () => dlg.close();
  q("#pkNew").onclick = () => { dlg.close(); window.openNewProject?.(); };
  q("#pkUse").onclick = async () => {
    if (!cur) return;
    q("#pkUse").disabled = true;
    const r = await api("/api/project/link", {path: cur.path});
    q("#pkUse").disabled = false;
    if (!r.ok) { q("#pkErr").textContent = r.error || (r.errors || []).join(" · ") || "That folder cannot be added."; return; }
    await window.loadProjects?.();
    collapsed = false;
    window.switchProject?.(r.slug);
    renderProjects();
    dlg.close();
    toast(`Project ${r.slug} added`, "ok");
  };
  dlg.addEventListener("close", () => { dlg.remove(); $("#newProjectBtn")?.focus(); }, {once: true});
  dlg.showModal();
  go("");
}
$("#newProjectBtn").onclick = openPicker;
if (select().options.length) renderProjects();
