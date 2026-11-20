/* Run against browser_fixture.py in a fresh browser profile. */
(async () => {
  if (!(await fetch("/api/fixture").then(response => response.json())).fixture) throw new Error("Fixture required");
  const q = selector => document.querySelector(selector);
  const checks = [];
  const check = (condition, message) => {
    if (!condition) throw new Error(message);
    checks.push(message);
  };
  async function wait(predicate, message) {
    for (let step = 0; step < 200; step++) {
      if (predicate()) return;
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    throw new Error(message);
  }
  const input = q("#input");
  const installEvent = new Event("beforeinstallprompt", {cancelable: true});
  await wait(() => q(".workspace-spotlight") && q('[data-p="example-project"]'), "Home did not load");
  check(q("#homeBtn").getAttribute("aria-current") === "page", "Home is the default workspace");
  window.dispatchEvent(installEvent);
  const runStatus = q("#statusText").getBoundingClientRect();
  const installIcon = q("#installAppBtn i");
  check(runStatus.width > 0 && runStatus.height > 0 && q("#status .dot").getBoundingClientRect().width > 0, "Run state stays visible in the header");
  check(installIcon.getBoundingClientRect().width > 0 && getComputedStyle(installIcon, "::before").content !== "none", "Install has a visible icon");
  check(document.documentElement.scrollWidth <= innerWidth, "Header and workspace fit without horizontal scrolling");
  check(q("#pauseBtn").getBoundingClientRect().width === 0 && q("#stopBtn").getBoundingClientRect().width === 0, "Idle run controls do not occupy the header");
  const mobile = innerWidth <= 760;
  const chatButton = q("#jumpChatBtn");
  const chatBox = chatButton.getBoundingClientRect();
  check(chatBox.width >= 32 && chatBox.right <= innerWidth, "Chat remains reachable in the header");
  if (mobile) {
    check(!q("#chatPanel").getClientRects().length && chatButton.getAttribute("aria-expanded") === "false", "Mobile workspace starts without the chat panel");
  }
  const searchButton = q("#paletteBtn");
  searchButton.focus();
  searchButton.click();
  const palette = q(".workspace-search");
  const search = q("#workspaceSearchQuery");
  const popup = palette.getBoundingClientRect();
  check(palette.open && document.activeElement === search && popup.left >= 0 &&
    popup.right <= innerWidth && popup.bottom <= innerHeight, "Search opens as a focused dialog inside the viewport");
  press("ArrowDown");
  check(q('#' + search.getAttribute("aria-activedescendant"))?.dataset.result === "1", "Search supports arrow-key navigation");
  search.value = "settings";
  search.dispatchEvent(new Event("input"));
  check(q('#' + search.getAttribute("aria-activedescendant"))?.textContent.includes("Runtime settings"), "Search ranks title matches above category matches");
  search.value = "zzzzz-no-match";
  search.dispatchEvent(new Event("input"));
  press("ArrowDown");
  check(!search.hasAttribute("aria-activedescendant") && !q(".workspace-search-empty").hidden, "Empty search has no invalid keyboard selection");
  press("Escape");
  check(!palette.open && document.activeElement === searchButton, "Closing search restores focus");

  searchButton.click();
  const nextSearch = q(".workspace-search[open] input");
  nextSearch.value = "appearance";
  nextSearch.dispatchEvent(new Event("input"));
  press("Enter");
  await wait(() => q("#aAccent") && q('#cnav [data-sec="appearance"][aria-current="page"]'), "Search did not open the requested settings section");
  check(document.body.classList.contains("control-mode") && q(".appearance-settings .settings-group"), "Search can open a grouped Control settings page");
  q("#homeBtn").click();
  const modePicker = q("#modePickerBtn");
  if (mobile) {
    check(modePicker.getClientRects().length && !q("#workspaceNav").getClientRects().length, "Compact header shows the current workspace with navigation tucked away");
    modePicker.click();
    await wait(() => q("#workspaceNav").matches(":popover-open") && document.activeElement === q("#homeBtn"), "Workspace picker did not open and focus the selected view");
    const nav = q("#workspaceNav").getBoundingClientRect();
    check(nav.left >= 0 && nav.right <= innerWidth && nav.bottom <= innerHeight && modePicker.getAttribute("aria-expanded") === "true", "Workspace menu fits the viewport");
    q("#meshBtn").click();
    check(!q("#workspaceNav").matches(":popover-open") && modePicker.textContent.trim() === "Mesh", "Selecting a view closes the menu and updates the title");
  } else {
    check(!modePicker.getClientRects().length && q("#workspaceNav").getClientRects().length, "Desktop shows all workspace destinations");
    q("#meshBtn").click();
  }
  q("#inspectorProject").focus();
  press("ArrowRight");
  check(document.activeElement.id === "inspectorFiles" && q("#inspectorFiles").getAttribute("aria-selected") === "true" &&
    q("#pFiles").getClientRects().length && !q("#pProject").getClientRects().length, "Inspector tabs switch with the keyboard");
  press("End");
  check(document.activeElement.id === "inspectorAgy" && q("#pAgy").getClientRects().length, "Antigravity is reachable in the inspector");
  press("Home");
  if (!mobile) {
    const side = q("#sidePanel");
    const normal = side.getBoundingClientRect().width;
    q("#sideExpandBtn").click();
    check(side.getBoundingClientRect().width > normal && q("#sideExpandBtn").getAttribute("aria-pressed") === "true", "Enlarging the desktop inspector creates more room");
    q("#sideExpandBtn").click();
    check(Math.abs(side.getBoundingClientRect().width - normal) < 2, "Restoring the inspector preserves its saved size");
  }
  q("#sideCollapseBtn").click();
  check(document.activeElement.id === "sideExpandTrigger" && !q(".inspector-tabs").getClientRects().length, "Collapsing the inspector keeps its reopen control focused");
  q("#sideExpandTrigger").click();
  check(document.activeElement.id === "sideCollapseBtn" && q(".inspector-tabs").getClientRects().length, "Reopening the inspector restores its controls");
  q("#homeBtn").click();
  q("#home-tab-system").click();
  await wait(() => q(".workspace-system")?.textContent.includes("Token usage"), "System tab did not show usage");
  check(q(".workspace-system").textContent.includes("Health"), "System tab keeps health and token usage accessible");
  q("#home-tab-overview").click();

  q('[data-select-project="other-project"]').click();
  await wait(() => q(".spotlight-title")?.textContent.includes("other-project"), "Project row did not switch the workspace");
  check(q('[data-select-project="other-project"]').getAttribute("aria-current") === "true", "Home can switch projects with the chat panel closed");
  q('[data-select-project="example-project"]').click();
  await wait(() => q(".spotlight-title")?.textContent.includes("example-project"), "Selected project did not reach Home");
  check(q("#chatContext").textContent === "example-project", "Home and chat show the selected project");
  q("[data-plan]").click();
  await wait(() => jarvisStudio.state.planSlug === "example-project" &&
    q(".plan-layout")?.textContent.includes("Check the interface"), "Open plan did not load the selected project's plan");
  checks.push("Open plan opens the selected project's plan");
  q("#homeBtn").click();

  if (mobile) {
    chatButton.click();
    check(!q("#projectsPanel").getClientRects().length, "Chat starts with space for the conversation");
    q("#chatProjectsBtn").click();
    check(q("#projectsPanel").getClientRects().length && q("#chatProjectsBtn").getAttribute("aria-expanded") === "true", "Projects are available from mobile chat");
  }
  const query = q("#projectQuery");
  query.value = "other";
  query.dispatchEvent(new Event("input"));
  check(q(".mn-proj").dataset.p === "other-project" && document.querySelectorAll(".mn-proj").length === 1, "Project search filters the list");
  query.value = "missing";
  query.dispatchEvent(new Event("input"));
  check(q("#projectList").textContent.includes("No projects match"), "Project search reports no matches");
  query.value = "";
  query.dispatchEvent(new Event("input"));
  check(q('[data-p="example-project"]').getAttribute("aria-current") === "true", "Clearing search keeps the current project");

  const projectOptions = q('[data-more="example-project"]');
  projectOptions.click();
  check(projectOptions.getAttribute("aria-expanded") === "true" && document.activeElement.matches("#projectMenu [role=menuitem]"), "Project options open and receive focus");
  press("ArrowDown");
  check(document.activeElement.textContent.includes("Open in Code"), "Project options support arrow-key navigation");
  press("Escape");
  check(!q("#projectMenu") && document.activeElement === projectOptions && projectOptions.getAttribute("aria-expanded") === "false", "Closing project options restores focus");

  if (mobile) chatButton.click();

  function press(key) {
    document.activeElement.dispatchEvent(new KeyboardEvent("keydown", {key, bubbles: true, cancelable: true}));
  }
  q("#home-tab-overview").focus();
  press("ArrowRight");
  check(document.activeElement.id === "home-tab-shots" && document.activeElement.getAttribute("aria-selected") === "true", "Arrow key selects and focuses the next tab");
  press("End");
  check(document.activeElement.id === "home-tab-settings" && q("#kzHomeBody").getAttribute("aria-labelledby") === "home-tab-settings", "End selects the last tab and updates its label");
  await wait(() => q("#kzSettings"), "Runtime settings failed to load");
  const form = q("#kzSettings");
  check(form.querySelectorAll(".settings-group").length === 5 &&
    form.elements.budget_tokens.labels[0]?.textContent === "Token budget", "Runtime settings group and label the controls");
  form.elements.budget_tokens.value = "123456";
  form.requestSubmit();
  await wait(() => q("#kzSetState").textContent.startsWith("Saved"), "Runtime settings did not save");
  const persisted = await fetch("/api/settings/runtime").then(response => response.json());
  check(persisted.settings.budget_tokens === 123456, "Runtime settings persist the requested change");

  if (mobile) window.scrollTo(0, 160);
  const workspaceScrollY = scrollY;
  if (!mobile) {
    const home = q("#homeView");
    const width = home.getBoundingClientRect().width;
    chatButton.click();
    check(!q("#chatPanel").getClientRects().length && home.getBoundingClientRect().width > width, "Closing desktop chat gives the workspace the full column");
  }
  chatButton.click();
  const inputBounds = input.getBoundingClientRect();
  check(chatButton.getAttribute("aria-expanded") === "true" && document.activeElement === q("#chat") &&
    inputBounds.top >= q(".top").getBoundingClientRect().bottom && inputBounds.bottom <= innerHeight, "Opening chat makes the entire composer visible and focuses the conversation");
  check(input.dir === "auto", "The composer follows the direction of typed text");
  if (mobile) {
    check(!q("#homeView").getClientRects().length && scrollY === 0, "Chat has its own mobile view");
    const draftSetting = form.elements.budget_tokens;
    draftSetting.value = "123457";
    chatButton.click();
    check(q("#kzSettings") === form && draftSetting.value === "123457", "Back to workspace preserves an unfinished settings edit");
    check(workspaceScrollY > 0 && scrollY === workspaceScrollY, "Back to workspace restores the original scroll position");
    chatButton.click();
  }

  const chatTools = q("#chatTools");
  input.value = "پیش‌نویس";
  input.dispatchEvent(new Event("input"));
  q("#chatToolsToggle").click();
  await wait(() => chatTools.matches(":popover-open") && chatTools.style.left, "Chat tools did not open");
  const bounds = chatTools.getBoundingClientRect();
  check(bounds.left >= 0 && bounds.right <= innerWidth && bounds.top >= 0 && bounds.bottom <= innerHeight, "Chat tools stay inside the viewport");
  const starter = q("#quick button");
  const originalFetch = window.fetch;
  let chatRequests = 0;
  try {
    window.fetch = (url, ...args) => {
      if (url === "/api/chat") chatRequests++;
      return originalFetch(url, ...args);
    };
    starter.click();
    check(input.value === "پیش‌نویس\n\n" + starter.dataset.t && document.activeElement === input, "Prompt starter appends to the draft and restores focus");
    check(!chatTools.matches(":popover-open") && chatRequests === 0, "Prompt starter closes tools without sending a request");
  } finally {
    window.fetch = originalFetch;
  }

  if (mobile) {
    const draft = input.value;
    q("#homeBtn").click();
    check(!q("#chatPanel").getClientRects().length && q("#kzSettings") === form, "Tapping the current workspace closes chat and restores the existing view");
    chatButton.click();
    check(input.value === draft, "A draft survives leaving and reopening mobile chat");
  }
  const sendButton = q("#form .send");
  const changeDraft = text => {
    input.value = text;
    input.dispatchEvent(new Event("input"));
  };
  changeDraft("");
  const collapsedHeight = input.getBoundingClientRect().height;
  check(sendButton.disabled, "An empty draft cannot be sent");
  check(!q("#chatLatest").getClientRects().length, "The latest-message shortcut stays hidden in an empty conversation");
  const starterButton = q(".chat-starters button");
  starterButton.click();
  check(input.value === starterButton.dataset.t && !sendButton.disabled, "An empty conversation starter fills the composer");
  changeDraft(Array(35).fill("A multiline draft").join("\n"));
  check(input.getBoundingClientRect().height > collapsedHeight && input.getBoundingClientRect().height < 180 &&
    input.scrollHeight > input.clientHeight && input.getBoundingClientRect().bottom < innerHeight, "Long drafts grow, then scroll inside the composer");
  changeDraft("Attachment test");
  const {attachProjectImage} = await import("/ui/media.js");
  const fetchUpload = window.fetch;
  let releaseUpload;
  const uploadGate = new Promise(resolve => { releaseUpload = resolve; });
  window.fetch = async (url, ...args) => {
    if (url === "/api/upload-image") await uploadGate;
    return fetchUpload(url, ...args);
  };
  try {
    const upload = attachProjectImage("example-project", "assets/sample.png");
    check(sendButton.disabled && q("#attachmentStatus").textContent.includes("Uploading"), "Sending waits for the attachment upload");
    releaseUpload();
    await upload;
    check(q("#form #attachmentStrip img") && !sendButton.disabled, "Image previews appear inside the composer");
    q("#attachmentStrip button").click();
    check(q("#attachmentStrip").hidden && document.activeElement === input, "Removing the last attachment returns focus to the draft");
  } finally {
    releaseUpload();
    window.fetch = fetchUpload;
  }
  const transcript = q("#chat");
  clearChat();
  addUser("بررسی پیام فارسی");
  addAI("A response with a long URL " + "x".repeat(300) + "\n\n```text\n" + "y".repeat(300) + "\n```");
  for (let i = 0; i < 12; i++) addAI("Long conversation sample. ".repeat(30));
  transcript.scrollTo({top: 0, behavior: "instant"});
  await wait(() => !q("#chatLatest").hidden, "Latest messages control did not appear");
  addAI("An incoming answer");
  check(transcript.scrollTop === 0 && transcript.scrollWidth <= transcript.clientWidth, "Incoming answers preserve the reading position and long text stays in bounds");
  q("#chatLatest").click();
  check(nearBottom() && q("#chatLatest").hidden, "Latest messages jumps to the end");
  return {ok: true, passed: checks.length, checks};
})()
