(async () => {
  if (!(await fetch("/api/fixture").then(response => response.json())).fixture) throw new Error("Fixture required");
  const q = selector => document.querySelector(selector);
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  async function wait(predicate, message) {
    for (let attempt = 0; attempt < 150; attempt++) {
      if (await predicate()) return;
      await delay(30);
    }
    throw new Error(message);
  }

  await wait(() => q("#proj").value === "example-project", "Project selection did not load");
  jarvisStudio.setMode("mesh", false);
  q("#newBtn").click();
  check(document.activeElement === q("#input"), "New chat did not focus the composer");

  let submitted = false;
  const mark = event => { submitted = true; event.preventDefault(); event.stopImmediatePropagation(); };
  q("#form").addEventListener("submit", mark, true);
  q("#input").dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", isComposing: true, bubbles: true, cancelable: true}));
  q("#form").removeEventListener("submit", mark, true);
  check(!submitted, "IME composition submitted a chat");

  const gate = q('[data-gate="plan"]');
  await wait(() => gate.getAttribute("aria-disabled") === "false", "Gate did not load");
  gate.dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", bubbles: true, cancelable: true}));
  await wait(() => gate.getAttribute("aria-pressed") === "true", "Keyboard did not lock the gate");
  const project = await api("/api/mesh/gates?project=example-project");
  const other = await api("/api/mesh/gates?project=other-project");
  check(project.gates.plan && !other.gates.plan, "Gate was not saved per project");

  await send("wait for gate", {project: "example-project"});
  const gated = sessionId;
  await wait(() => document.querySelector(".kz-runstatus")?.textContent.includes("waiting for the plan gate"), "Gate did not stop entry");
  gate.dispatchEvent(new KeyboardEvent("keydown", {key: " ", bubbles: true, cancelable: true}));
  await wait(() => !runBusy, "Run did not finish after gate release");
  const finished = await api("/api/session?id=" + gated);
  check(finished.messages.at(-1).content === "Gate released.", "Run did not resume after release");

  q("#newBtn").click();
  await send("slow cancellable run", {project: "example-project"});
  const stopped = sessionId;
  await wait(() => !q("#pauseBtn").disabled, "Pause did not enable");
  const pause = q("#pauseBtn").getBoundingClientRect();
  const stop = q("#stopBtn").getBoundingClientRect();
  check(pause.width > 0 && stop.width > 0 && pause.left >= 0 && stop.right <= innerWidth, "Active run actions are visible in the mobile header");
  q("#pauseBtn").click();
  await wait(() => q("#statusText").textContent === "Paused", "Run did not pause at a safe boundary");
  q("#input").value = "queued work that must be cancelled";
  q("#input").dispatchEvent(new Event("input"));
  check(q("#form .send").getAttribute("aria-label") === "Queue message", "The composer labels the action Queue during an active run");
  q("#form").requestSubmit();
  await wait(() => !q("#input").value, "Queued message was not accepted from the composer");
  await wait(() => !q("#stopBtn").disabled, "Stop did not enable on the paused run");
  q("#stopBtn").click();
  await wait(() => !runBusy, "Stop did not release the paused run");
  const session = await api("/api/session?id=" + stopped);
  check(session.messages.at(-1).content.startsWith("Stopped"), "Stop did not record a cancelled turn");
  const queue = await api("/api/queue");
  check(!queue.queue.some(item => item.session === stopped), "Stop left a queued message");
  check(q("#stopBtn").disabled && q("#pauseBtn").disabled, "Run controls did not return to idle");

  const manifest = await fetch("/manifest.webmanifest").then(response => response.json());
  check(manifest.display === "standalone" && manifest.icons.length >= 2, "Install manifest is incomplete");
  await wait(() => navigator.serviceWorker.controller, "Service worker did not activate");
  const cached = await caches.open("kryzen-offline-v3").then(cache => cache.keys());
  check(cached.length === 1 && cached[0].url.endsWith("/offline.html"), "Service worker cached private content");
  return {ok: true, passed: 10};
})()
