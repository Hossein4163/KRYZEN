// Entry point for the K.R.Y.Z.E.N modules (Home, Trace, palette, review) plus small chat/Activity additions.
import {$, esc, fmtMs, fmtTokens, onEvent, setMode, shortAgent} from "./core.js";
import "./review.js";
import "./dashboard.js";
import "./trace.js";
import "./palette.js";
import "./runstatus.js";
import "./chatcompact.js";
import "./media.js";
import {askNotifyPermission} from "./review.js";

// Ask for notification permission on the first user interaction (browsers require a gesture).
document.addEventListener("click", askNotifyPermission, {once: true});

function activity(agent, head, detail) {
  // Same structured row as every other Activity entry (defined by the page script).
  if (typeof window.log === "function") return window.log(agent, head, detail);
}

onEvent(ev => {
  switch (ev.type) {
    case "model_call":
      activity(ev.agent, `◆ ${fmtTokens(ev.prompt_tokens)}→${fmtTokens(ev.completion_tokens)} tok · ${fmtMs(ev.ms)}${ev.attempts > 1 ? ` · ${ev.attempts} tries` : ""}`, `run total ${fmtTokens(ev.run_tokens)}`);
      break;
    case "tool_end":
      if (ev.blob && ev.chars > 400) {
        const first = $("#pLog")?.firstElementChild;
        if (first && !first.querySelector(".kz-full")) first.insertAdjacentHTML("beforeend", ` <a class="kz-full" data-trace-open>full output (${fmtTokens(ev.chars)} chars)</a>`);
      }
      break;
    case "budget":
      activity("", ev.state === "warn" ? "⚠ 80% of the run budget used" : ev.state === "paused" ? "⏸ Budget reached — paused. Resume to allow 50% more." : "↗ Budget extended",
        `${fmtTokens(ev.tokens)} / ${ev.max_tokens ? fmtTokens(ev.max_tokens) : "∞"} tokens`);
      if (ev.state !== "extended" && typeof window.toast === "function") window.toast(ev.state === "paused" ? "Budget reached — run paused. Resume to continue." : "80% of this run's budget used", ev.state === "paused" ? "err" : "ok");
      break;
    case "memory":
      if (ev.added) activity(ev.agent || "", `🧠 remembered ${ev.added} fact${ev.added > 1 ? "s" : ""}`, (ev.lines || []).join(" · "));
      break;
    case "rate_limit": activity(ev.agent, `⏳ rate limited — waiting ${Math.round(ev.wait)}s`, `parallel requests now ${ev.limit}`); break;
    case "fanout": activity(ev.agent, `⇉ ${ev.agents.length} specialists in parallel`, ev.agents.map(shortAgent).join(" · ")); break;
    case "context":
      if (ev.compacted) activity(ev.agent, `🗜 compacted ${ev.compacted} earlier steps`, `prompt reached ${fmtTokens(ev.prompt_tokens)} tokens (limit ${fmtTokens(ev.limit)}); the full history is still saved`);
      else activity("", `🗜 folded ${ev.folded} older chat messages into a summary`, "");
      break;
    case "approval_request": activity(ev.agent, "✋ waiting for your review", ev.path); break;
    case "lane_cancel": activity("", "✕ lane cancelled", ev.task_id); break;
    case "queue_started": activity("", "▶ queued message started", ""); break;
    case "turn_end": {
      if (!ev.usage) break;
      const bubbles = document.querySelectorAll("#chat .msg.ai"), last = bubbles[bubbles.length - 1];
      if (last && !last.querySelector(".kz-usage")) {
        const u = ev.usage;
        last.insertAdjacentHTML("beforeend", `<div class="kz-usage"><span>${fmtTokens(u.prompt + u.completion)} tokens</span><span>${u.calls} model calls</span><span>${u.tools} tools</span><span>${fmtMs(u.elapsed * 1000)}</span><a data-trace-open>see trace</a></div>`);
      }
      break;
    }
  }
});

document.addEventListener("click", e => {
  if (e.target.closest("[data-trace-open]")) { e.preventDefault(); setMode("trace"); }
});
