// Keeps long conversations light on screen: the latest items stay full, older replies and agent cards collapse
// to short previews (click to expand) and very old ones hide behind a "Show earlier messages" button.
const FULL = 24;      // newest items rendered in full
const VISIBLE = 140;  // items shown at all before "Show earlier"
let pending = 0, showAll = false;

function compact() {
  const chat = document.getElementById("chat");
  if (!chat) return;
  const items = [...chat.children].filter(el => el.matches(".msg, .agent-card"));
  const n = items.length;
  items.forEach((el, i) => {
    const fromEnd = n - i;
    el.classList.toggle("kz-old-hidden", !showAll && fromEnd > VISIBLE);
    if (fromEnd > FULL && !el.classList.contains("kz-open") && !el.classList.contains("live")) el.classList.add("kz-compact");
    else if (fromEnd <= FULL) el.classList.remove("kz-compact");
  });
  let more = chat.querySelector(":scope > .kz-earlier");
  const hidden = showAll ? 0 : Math.max(0, n - VISIBLE);
  if (hidden && !more) {
    more = document.createElement("button");
    more.className = "kz-earlier"; more.type = "button";
    more.onclick = () => { showAll = true; compact(); };
    chat.prepend(more);
  }
  if (more) { if (hidden) more.textContent = `Show ${hidden} earlier messages`; else more.remove(); }
}

function schedule() { clearTimeout(pending); pending = setTimeout(compact, 250); }

const chat = document.getElementById("chat");
if (chat) {
  new MutationObserver(schedule).observe(chat, {childList: true});
  chat.addEventListener("click", e => {
    const el = e.target.closest(".kz-compact");
    if (!el || e.target.closest("a, button, .chips")) return;
    el.classList.remove("kz-compact"); el.classList.add("kz-open");
  });
}
window.addEventListener("kryzen:session", () => { showAll = false; schedule(); });
schedule();
