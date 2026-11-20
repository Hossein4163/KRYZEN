const button = document.getElementById("installAppBtn");
let installPrompt;

window.addEventListener("beforeinstallprompt", event => {
  event.preventDefault();
  installPrompt = event;
  button.hidden = false;
});

button.addEventListener("click", async () => {
  if (!installPrompt) return;
  const prompt = installPrompt;
  installPrompt = null;
  button.hidden = true;
  try {
    await prompt.prompt();
  } catch (error) {
    window.toast?.(error.message, "err");
  }
});

window.addEventListener("appinstalled", () => {
  button.hidden = true;
  installPrompt = null;
});

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/service-worker.js").catch(error => {
    console.warn("K.R.Y.Z.E.N offline page could not be registered", error);
  });
}
