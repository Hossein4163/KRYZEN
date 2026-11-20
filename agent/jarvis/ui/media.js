// Images in K.R.Y.Z.E.N: attach / paste / drop / share-screen into the chat, screenshot cards for finished jobs
// and agent captures, a per-project gallery, and screenshot/send-to-chat buttons in the code workspace.
import {$, api, ago, currentProject, esc, onEvent, shortAgent, toast} from "./core.js";

// ------------------------------------------------------------------ composer attachments
const attached = [];
let strip = null, uploading = 0;

function renderStrip() {
  if (!strip) return;
  strip.hidden = !attached.length;
  strip.innerHTML = attached.map((image, i) => `<span class="kz-att"><img src="${esc(image.url)}" alt="Attached image ${i + 1}">
    <button type="button" data-rm="${i}" aria-label="Remove image ${i + 1}"><i class="icon-x" aria-hidden="true"></i></button></span>`).join("");
  $("#attachmentStatus").textContent = uploading ? (uploading === 1 ? "Uploading image…" : `Uploading ${uploading} images…`) : "";
  window.dispatchEvent(new Event("kryzen:attachment-state"));
}

async function uploadImage(payload) {
  if (attached.length + uploading >= 6) {
    toast("Up to 6 images per message", "err");
    return false;
  }
  uploading++;
  renderStrip();
  try {
    const result = await api("/api/upload-image", payload);
    if (!result.ok) {
      toast(result.error || "Could not attach the image", "err");
      return false;
    }
    if (!attached.some(image => image.id === result.id)) attached.push({id: result.id, url: result.url});
    return true;
  } finally {
    uploading--;
    renderStrip();
  }
}
export function attachData(data) { return uploadImage({data}); }
export async function attachProjectImage(slug, path) {
  if (await uploadImage({slug, path}) && !strip?.getClientRects().length) toast("Image attached to your next message", "ok");
}
const readFile = file => new Promise((ok, bad) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.onerror = bad; fr.readAsDataURL(file); });
async function attachFiles(files) {
  for (const f of files) {
    if (!f.type.startsWith("image/")) { toast(`${f.name} is not an image`, "err"); continue; }
    if (f.size > 12e6) { toast(`${f.name} is larger than 12 MB`, "err"); continue; }
    try { await attachData(await readFile(f)); }
    catch (error) { toast(`Could not read ${f.name}: ${error.message || "read failed"}`, "err"); }
  }
}

// Share screen: the browser asks which screen/window/tab; we grab one frame and stop sharing immediately.
export async function shareScreen() {
  if (!navigator.mediaDevices?.getDisplayMedia) return toast("Screen sharing is not available in this browser", "err");
  let stream;
  try { stream = await navigator.mediaDevices.getDisplayMedia({video: {frameRate: 5}, audio: false}); }
  catch (_) { return; }  // user cancelled
  try {
    const video = Object.assign(document.createElement("video"), {srcObject: stream, muted: true, playsInline: true});
    await video.play();
    await new Promise(r => setTimeout(r, 350));
    const c = document.createElement("canvas");
    c.width = video.videoWidth; c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);
    if (await attachData(c.toDataURL("image/png"))) toast("Screen captured and attached", "ok");
  } finally { stream.getTracks().forEach(t => t.stop()); }
}

function mountComposer() {
  const form = $("#form"), input = $("#input");
  if (!form || form.querySelector(".kz-compose-tools")) return;
  strip = $("#attachmentStrip");
  strip.addEventListener("click", event => {
    const button = event.target.closest("[data-rm]");
    if (!button) return;
    const index = Number(button.dataset.rm);
    attached.splice(index, 1);
    renderStrip();
    (strip.querySelectorAll("button")[Math.min(index, attached.length - 1)] || $("#input")).focus({preventScroll: true});
  });
  const tools = document.createElement("div"); tools.className = "kz-compose-tools";
  tools.innerHTML = `<button type="button" class="kz-icon" data-act="file" title="Attach images (or paste / drop them)" aria-label="Attach images">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.5l-8.6 8.6a5 5 0 01-7.1-7.1l9.2-9.2a3.4 3.4 0 014.8 4.8l-9.2 9.2a1.7 1.7 0 01-2.4-2.4l8.5-8.5"/></svg></button>
    <button type="button" class="kz-icon" data-act="screen" title="Share your screen (one snapshot is attached)" aria-label="Share screen">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4M12 7v6M9.5 9.5L12 7l2.5 2.5"/></svg></button>
    <input type="file" accept="image/*" multiple hidden>`;
  form.querySelector(".composer-tools").prepend(tools);
  renderStrip();
  const fileInput = tools.querySelector("input");
  tools.querySelector('[data-act="file"]').onclick = () => fileInput.click();
  tools.querySelector('[data-act="screen"]').onclick = shareScreen;
  fileInput.onchange = () => { attachFiles([...fileInput.files]); fileInput.value = ""; };
  input?.addEventListener("paste", e => {
    const files = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith("image/"));
    if (files.length) { e.preventDefault(); attachFiles(files); }
  });
  const panel = form.closest(".panel") || form;
  panel.addEventListener("dragover", e => { if ([...(e.dataTransfer?.items || [])].some(i => i.type.startsWith("image/"))) { e.preventDefault(); panel.classList.add("kz-drop"); } });
  panel.addEventListener("dragleave", () => panel.classList.remove("kz-drop"));
  panel.addEventListener("drop", e => {
    const files = [...(e.dataTransfer?.files || [])].filter(f => f.type.startsWith("image/"));
    panel.classList.remove("kz-drop");
    if (files.length) { e.preventDefault(); attachFiles(files); }
  });
}

// Used by the page's send(): images go with the message; cleared only after it was accepted.
window.kryzenAttach = {
  peek: () => attached.map(a => a.id),
  urls: () => attached.map(a => a.url),
  uploading: () => uploading > 0,
  removeSent: ids => {
    const sent = new Set(ids);
    for (let i = attached.length - 1; i >= 0; i--) {
      if (sent.delete(attached[i].id)) attached.splice(i, 1);
    }
    renderStrip();
  },
};

// ------------------------------------------------------------------ sharing helpers
async function copyImage(url) {
  try {
    const blob = await (await fetch(url)).blob();
    const png = blob.type === "image/png" ? blob : await new Promise(res => {
      const img = new Image(); img.onload = () => { const c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
        c.getContext("2d").drawImage(img, 0, 0); c.toBlob(res, "image/png"); }; img.src = URL.createObjectURL(blob); });
    await navigator.clipboard.write([new ClipboardItem({"image/png": png})]);
    toast("Image copied — paste it anywhere", "ok");
  } catch (e) { toast("Copy failed: " + e.message, "err"); }
}
function openViewer(url, caption) {
  const d = document.createElement("dialog"); d.className = "kz-dialog kz-viewer";
  d.innerHTML = `<header><h2>${esc(caption)}</h2></header><div class="kz-viewer-img"><img src="${esc(url)}" alt="${esc(caption)}"></div>
    <footer><a class="kz-btn" href="${esc(url)}" download>Download</a><button class="kz-btn" data-copy>Copy image</button><button class="kz-btn primary" data-close>Close</button></footer>`;
  document.body.appendChild(d);
  d.onclick = e => { if (e.target === d || e.target.closest("[data-close]")) d.close(); if (e.target.closest("[data-copy]")) copyImage(url); };
  d.addEventListener("close", () => d.remove()); d.showModal();
}
const shotUrl = s => `/api/project-image?slug=${encodeURIComponent(s.slug)}&path=${encodeURIComponent(s.path)}`;

function shotActions(s, url) {
  return `<div class="kz-shot-actions"><button class="kz-btn" data-open>Open</button><button class="kz-btn" data-copy>Copy</button>
    <a class="kz-btn" href="${esc(url)}" download="${esc(s.path.split("/").pop())}">Download</a><button class="kz-btn" data-attach>Attach to chat</button></div>`;
}
function wireShot(el, s, url, caption) {
  el.addEventListener("click", e => {
    if (e.target.closest("[data-open]") || e.target.closest("img")) openViewer(url, caption);
    if (e.target.closest("[data-copy]")) copyImage(url);
    if (e.target.closest("[data-attach]")) attachProjectImage(s.slug, s.path);
  });
}

// Chat card for a screenshot (finished job or agent capture).
export function renderShot(s) {
  const chat = $("#chat"); if (!chat || !s?.path) return;
  const url = shotUrl(s);
  const caption = s.kind === "finished" ? "Finished — screenshot of the running app" : `${shortAgent(s.agent)} captured a screenshot`;
  const el = document.createElement("figure"); el.className = "kz-shot msg";
  el.innerHTML = `<img src="${esc(url)}" alt="${esc(caption)}" loading="lazy"><figcaption><b>${esc(caption)}</b>
    <span>${esc(s.url || "")} · ${esc(s.path)}</span></figcaption>${shotActions(s, url)}`;
  wireShot(el, s, url, caption);
  const live = chat.querySelector(".msg.ai.live");
  chat.insertBefore(el, live && live.parentNode === chat ? live : null);
  if (chat.scrollHeight - chat.scrollTop - chat.clientHeight < 400) chat.scrollTop = chat.scrollHeight;
}
window.kryzenRenderShot = renderShot;

onEvent(ev => { if (ev.type === "screenshot") renderShot(ev); });

// ------------------------------------------------------------------ gallery (Home › Screenshots)
export async function renderGallery(body) {
  const slug = currentProject();
  if (!slug) { body.innerHTML = '<div class="kz-empty">Choose a project in the header to see its screenshots.</div>'; return; }
  const pv = $("#pvUrl")?.value || "http://localhost:5173";
  body.innerHTML = `<section class="kz-card"><h3>${esc(slug)} · screenshots <small>.devpilot/screenshots</small></h3>
    <form class="kz-shotbar" id="kzShotForm"><input class="kz-input" id="kzShotUrl" value="${esc(pv)}" aria-label="Page address" placeholder="http://localhost:5173">
      <button class="kz-btn primary">Take screenshot</button><span class="kz-muted">Captures the page into the project gallery. Finished project runs add one automatically when the app is running.</span></form>
    <div class="kz-gallery" id="kzGallery"><div class="kz-empty">Loading…</div></div></section>`;
  const g = body.querySelector("#kzGallery");
  const load = async () => {
    const r = await api("/api/screenshots?slug=" + encodeURIComponent(slug));
    if (!g.isConnected) return;
    if (r.error) { g.innerHTML = `<div class="kz-empty" role="alert">${esc(r.error)}</div>`; return; }
    g.innerHTML = (r.shots || []).map((s, i) => `<figure class="kz-shot" data-i="${i}"><img src="${esc(shotUrl({...s, slug}))}" alt="${esc(s.name)}" loading="lazy">
      <figcaption><b>${esc(s.kind === "finished" ? "Finished run" : s.kind === "agent" ? shortAgent(s.agent) : s.name.includes("diff") ? "Visual diff" : "Screenshot")}</b><span>${ago(s.t)} · ${esc(s.url || s.name)}</span></figcaption>
      ${shotActions({...s, slug}, shotUrl({...s, slug}))}</figure>`).join("") || '<div class="kz-empty">No screenshots yet.</div>';
    g.querySelectorAll("figure").forEach(f => { const s = {...r.shots[+f.dataset.i], slug}; wireShot(f, s, shotUrl(s), s.name); });
  };
  body.querySelector("#kzShotForm").onsubmit = async e => {
    e.preventDefault(); const b = e.target.querySelector("button"); b.disabled = true; b.textContent = "Capturing…";
    const r = await api("/api/screenshot", {slug, url: body.querySelector("#kzShotUrl").value.trim(), label: "manual"});
    b.disabled = false; b.textContent = "Take screenshot";
    r.ok ? (toast("Screenshot saved", "ok"), load()) : toast(r.error, "err");
  };
  load();
}

// ------------------------------------------------------------------ code workspace
const cw = () => (typeof CW !== "undefined" ? CW : null);   // the page's code-workspace state
function mountCode() {
  const tools = $("#dPrev .dtools");
  if (tools && !tools.querySelector("[data-kz-shot]")) {
    const b = document.createElement("button"); b.className = "btn"; b.dataset.kzShot = "1"; b.type = "button";
    b.textContent = "📸 Screenshot"; b.title = "Capture this page into the project gallery and attach it to the chat";
    b.onclick = async () => {
      const slug = cw()?.slug || currentProject(); const url = $("#pvUrl").value.trim();
      if (!slug) return toast("Open a project first", "err");
      b.disabled = true; b.textContent = "Capturing…";
      const r = await api("/api/screenshot", {slug, url, label: "preview"});
      b.disabled = false; b.textContent = "📸 Screenshot";
      if (!r.ok) return toast(r.error, "err");
      attached.push({id: r.id, url: r.url, w: r.width, h: r.height}); renderStrip();
      toast(`Saved ${r.path} and attached it to your next message`, "ok");
    };
    tools.appendChild(b);
  }
  const imgTools = $("#cwImageView .cw-image-tools");
  if (imgTools && !imgTools.querySelector("[data-kz-send]")) {
    const b = document.createElement("button"); b.className = "btn"; b.dataset.kzSend = "1"; b.type = "button";
    b.textContent = "Send to chat"; b.title = "Attach this image to your next chat message";
    b.onclick = () => { const f = cw()?.cur; if (f) attachProjectImage(cw().slug, f.path); };
    imgTools.appendChild(b);
  }
}

mountComposer();
mountCode();
