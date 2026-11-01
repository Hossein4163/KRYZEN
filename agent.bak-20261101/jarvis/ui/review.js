// Review mode: agents wait while you approve or reject each file write, shown as a diff.
import {api, diffHtml, esc, onEvent, shortAgent, toast} from "./core.js";

let dialog = null;
const queue = [];

export async function openReview(id) {
  const {approvals = []} = await api("/api/approvals?diff=1");
  const item = approvals.find(a => a.id === id) || approvals[0];
  if (!item) return toast("Nothing is waiting for review", "ok");
  show(item);
}

function show(item) {
  if (dialog?.open) { if (!queue.includes(item.id)) queue.push(item.id); return; }
  dialog?.remove();
  dialog = document.createElement("dialog");
  dialog.className = "kz-dialog";
  dialog.setAttribute("aria-labelledby", "kzReviewTitle");
  dialog.innerHTML = `<header><span class="kz-eyebrow">Review mode · ${esc(shortAgent(item.agent))} wants to ${item.new_file ? "create" : "change"} a file</span>
      <h2 id="kzReviewTitle">${esc(item.path)}</h2></header>
    <div class="kz-diff" tabindex="0" aria-label="Proposed changes">${diffHtml(item.diff)}</div>
    <footer><input class="kz-input" id="kzReviewNote" placeholder="Optional note for the agent (why you rejected)" style="flex:1;min-width:200px">
      <button class="kz-btn danger" data-act="reject">Reject</button><button class="kz-btn primary" data-act="approve">Approve write</button></footer>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("click", async e => {
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (!act) return;
    e.target.disabled = true;
    const r = await api("/api/approval", {id: item.id, approved: act === "approve", note: dialog.querySelector("#kzReviewNote").value});
    if (!r.ok) toast(r.error || "Could not send the decision", "err");
    dialog.close();
  });
  dialog.addEventListener("close", () => {
    dialog.remove(); dialog = null;
    const next = queue.shift();
    if (next) openReview(next);
    window.dispatchEvent(new Event("kryzen:inbox"));
  });
  dialog.showModal();
  dialog.querySelector('[data-act="approve"]').focus();
}

onEvent(ev => {
  if (ev.type === "approval_request") { openReview(ev.id); notify("Approval needed", `${shortAgent(ev.agent)} wants to write ${ev.path}`); }
  if (ev.type === "approval_done") window.dispatchEvent(new Event("kryzen:inbox"));
});

// ---- desktop notifications (only when the page is hidden)
export function notify(title, body) {
  if (!("Notification" in window) || !document.hidden) return;
  if (Notification.permission === "granted") new Notification(title, {body, tag: "kryzen-" + title});
}
export function askNotifyPermission() {
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}
onEvent(ev => {
  if (ev.type === "turn_end") notify(ev.error ? "Run failed" : ev.stopped ? "Run stopped" : "Run finished", String(ev.text || "").slice(0, 140));
  if (ev.type === "budget" && ev.state === "paused") notify("Run paused: budget reached", "Resume to allow 50% more.");
});
