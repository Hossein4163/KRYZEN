// Autonomous Bots (Rakazo persistent teammates) workspace view.
import {$, $$, esc, api, toast, onMode, activeMode, setMode} from "./core.js";

const root = () => $("#botsView");
let bots = [];
let selectedId = localStorage.getItem("kryzen.selectedBot") || "devpilot-orchestrator";
let currentTab = localStorage.getItem("kryzen.botTab") || "chat";
let filter = "all";
let botLogs = {};
let isExecuting = false;

function shell() {
  if (activeMode() !== "bots") return;
  const el = root();
  if (!el) return;

  const filteredBots = bots.filter(b => {
    if (filter === "active") return b.status === "running" || b.active_jobs_count > 0;
    if (filter === "routines") return (b.routines || []).length > 0;
    if (filter === "custom") return !b.is_default;
    return true;
  });

  const selectedBot = bots.find(b => b.id === selectedId) || bots[0];
  if (selectedBot && selectedBot.id !== selectedId) {
    selectedId = selectedBot.id;
  }

  el.innerHTML = `
    <div class="kz-pad" style="max-width:1400px;margin-inline:auto;padding-bottom:50px;">
      <header class="workspace-heading" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
        <div>
          <div style="font-size:11px;font-weight:700;letter-spacing:0.08em;color:var(--accent-text);text-transform:uppercase;margin-bottom:4px;">
            Rakazo Autonomous Mesh · Antigravity CLI (agy)
          </div>
          <h1 style="font-size:22px;font-weight:700;margin:0;color:var(--color-text);">Autonomous Teammates</h1>
          <p style="margin:4px 0 0;font-size:13px;color:var(--muted);">
            Persistent AI bots with durable identities, memory, computer sandboxes, routines, and agy CLI engine.
          </p>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          <button type="button" class="btn" id="newBotBtn" style="background:var(--accent);color:var(--bg);font-weight:600;">
            <i class="icon-plus" aria-hidden="true"></i><span>New Teammate</span>
          </button>
          <button type="button" class="btn" id="refreshBotsBtn" title="Refresh Teammates">
            <i class="icon-refresh-cw" aria-hidden="true"></i>
          </button>
        </div>
      </header>

      <!-- Filter Bar -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:18px;margin-bottom:20px;border-bottom:1px solid var(--rule-soft);padding-bottom:12px;flex-wrap:wrap;gap:12px;">
        <div class="kz-tabs" role="tablist" style="display:flex;gap:8px;">
          <button class="btn ${filter === 'all' ? 'primary on' : ''}" data-filter="all">All Teammates (${bots.length})</button>
          <button class="btn ${filter === 'active' ? 'primary on' : ''}" data-filter="active">Active (${bots.filter(b => b.status === 'running' || b.active_jobs_count > 0).length})</button>
          <button class="btn ${filter === 'routines' ? 'primary on' : ''}" data-filter="routines">With Routines (${bots.filter(b => (b.routines || []).length > 0).length})</button>
          <button class="btn ${filter === 'custom' ? 'primary on' : ''}" data-filter="custom">Custom (${bots.filter(b => !b.is_default).length})</button>
        </div>
        <div style="font-size:12px;color:var(--soft);">
          Engine: <span style="color:var(--accent-text);font-family:var(--mono);">agy (Antigravity CLI)</span>
        </div>
      </div>

      <!-- Main Two-Column Layout -->
      <div style="display:grid;grid-template-columns:360px minmax(0,1fr);gap:24px;align-items:start;">
        <!-- Left Column: Teammates Cards -->
        <div style="display:flex;flex-direction:column;gap:12px;" id="botCardsContainer">
          ${filteredBots.map(b => renderBotCard(b, b.id === selectedId)).join("")}
          ${filteredBots.length === 0 ? `<div style="padding:30px;text-align:center;color:var(--muted);border:1px dashed var(--rule);border-radius:8px;">No teammates matching filter.</div>` : ""}
        </div>

        <!-- Right Column: Selected Bot Detail & Workstation -->
        <div id="botDetailWorkspace">
          ${selectedBot ? renderBotWorkspace(selectedBot) : `<div style="padding:40px;text-align:center;color:var(--muted);">Select a teammate on the left.</div>`}
        </div>
      </div>
    </div>

    <!-- Create/Edit Bot Modal Dialog -->
    <dialog id="botModal" class="cw-quick-dialog" style="max-width:580px;padding:24px;background:var(--color-surface);border:1px solid var(--rule);border-radius:12px;color:var(--color-text);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h3 id="modalTitle" style="margin:0;font-size:17px;font-weight:700;">Create Autonomous Teammate</h3>
        <button type="button" class="btn" id="closeBotModalBtn"><i class="icon-x" aria-hidden="true"></i></button>
      </div>
      <form id="botForm" style="display:flex;flex-direction:column;gap:14px;">
        <input type="hidden" id="formBotId" value="">
        <div>
          <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--soft);">Bot ID (slug)</label>
          <input type="text" id="formId" required placeholder="e.g. backend-reviewer" style="width:100%;padding:8px 10px;background:var(--color-bg);border:1px solid var(--rule);border-radius:6px;color:var(--color-text);font-family:var(--mono);font-size:13px;">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--soft);">Name</label>
            <input type="text" id="formName" required placeholder="e.g. Backend Reviewer" style="width:100%;padding:8px 10px;background:var(--color-bg);border:1px solid var(--rule);border-radius:6px;color:var(--color-text);font-size:13px;">
          </div>
          <div>
            <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--soft);">Role</label>
            <input type="text" id="formRole" required placeholder="e.g. Security & API Auditor" style="width:100%;padding:8px 10px;background:var(--color-bg);border:1px solid var(--rule);border-radius:6px;color:var(--color-text);font-size:13px;">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--soft);">Model</label>
            <select id="formModel" style="width:100%;padding:8px 10px;background:var(--color-bg);border:1px solid var(--rule);border-radius:6px;color:var(--color-text);font-size:13px;">
              <option value="agy/gemini-3.8-flash">agy/gemini-3.8-flash (Recommended)</option>
              <option value="agy/gemini-3-pro">agy/gemini-3-pro</option>
              <option value="agy/gemini-3-flash">agy/gemini-3-flash</option>
              <option value="agy/auto">agy/auto</option>
              <option value="ollama/qwen2.5-coder">ollama/qwen2.5-coder (Local)</option>
              <option value="openai/gpt-4o">openai/gpt-4o</option>
            </select>
          </div>
          <div>
            <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--soft);">Color Accent</label>
            <select id="formColor" style="width:100%;padding:8px 10px;background:var(--color-bg);border:1px solid var(--rule);border-radius:6px;color:var(--color-text);font-size:13px;">
              <option value="red">Red</option>
              <option value="blue">Blue</option>
              <option value="purple">Purple</option>
              <option value="green">Green</option>
              <option value="yellow">Yellow</option>
              <option value="orange">Orange</option>
              <option value="gray">Gray</option>
            </select>
          </div>
        </div>
        <div>
          <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--soft);">Description</label>
          <input type="text" id="formDesc" placeholder="Brief summary of duties" style="width:100%;padding:8px 10px;background:var(--color-bg);border:1px solid var(--rule);border-radius:6px;color:var(--color-text);font-size:13px;">
        </div>
        <div>
          <label style="display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--soft);">System Prompt & Instructions</label>
          <textarea id="formInstructions" rows="4" placeholder="Specific persona, coding constraints, and rules for this teammate..." style="width:100%;padding:8px 10px;background:var(--color-bg);border:1px solid var(--rule);border-radius:6px;color:var(--color-text);font-family:var(--sans);font-size:13px;resize:vertical;"></textarea>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:10px;">
          <button type="button" class="btn" id="cancelBotModalBtn">Cancel</button>
          <button type="submit" class="btn primary" id="saveBotModalBtn">Save Teammate</button>
        </div>
      </form>
    </dialog>
  `;

  attachEvents();
}

function renderBotCard(bot, isSelected) {
  const colorMap = {
    red: "var(--color-red, #e53e3e)",
    blue: "var(--color-blue, #3182ce)",
    purple: "var(--color-purple, #805ad5)",
    green: "var(--color-green, #38a169)",
    yellow: "var(--color-yellow, #d69e2e)",
    orange: "var(--color-orange, #dd6b20)",
    gray: "var(--muted)",
  };
  const accent = colorMap[bot.color] || colorMap.blue;
  const isRunning = bot.status === "running" || bot.active_jobs_count > 0;

  return `
    <div class="bot-card ${isSelected ? 'selected' : ''}" data-bot-id="${esc(bot.id)}" style="
      background: ${isSelected ? 'var(--color-surface-raised, #18181b)' : 'var(--color-surface, #111)'};
      border: 1px solid ${isSelected ? 'var(--accent, #E60000)' : 'var(--rule, #27272a)'};
      border-radius: 8px;
      padding: 14px 16px;
      cursor: pointer;
      position: relative;
      transition: all 0.15s ease;
      box-shadow: ${isSelected ? '0 0 16px rgba(230,0,0,0.12)' : 'none'};
    ">
      <div style="display:flex;align-items:flex-start;gap:12px;">
        <div style="
          width:36px;height:36px;border-radius:6px;
          display:grid;place-items:center;flex-shrink:0;
          background:${accent}22;color:${accent};
          border:1px solid ${accent}55;font-weight:700;font-size:14px;
        ">
          ${bot.name.substring(0, 2).toUpperCase()}
        </div>
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
            <strong style="font-size:14px;color:var(--color-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(bot.name)}</strong>
            <span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;color:${isRunning ? 'var(--color-green, #38a169)' : 'var(--muted)'};">
              <span style="width:7px;height:7px;border-radius:50%;background:${isRunning ? 'var(--color-green, #38a169)' : 'var(--rule)'};${isRunning ? 'box-shadow:0 0 8px var(--color-green);' : ''}"></span>
              ${isRunning ? 'Working' : 'Idle'}
            </span>
          </div>
          <div style="font-size:12px;color:var(--soft);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            ${esc(bot.role)}
          </div>
          <div style="display:flex;align-items:center;gap:6px;margin-top:8px;flex-wrap:wrap;">
            <span style="font-size:10px;font-family:var(--mono);padding:2px 6px;border-radius:4px;background:var(--color-bg);color:var(--accent-text);border:1px solid var(--rule-soft);">
              ${esc(bot.model.replace(/^agy\//, ''))}
            </span>
            ${(bot.routines || []).length > 0 ? `
              <span style="font-size:10px;padding:2px 6px;border-radius:4px;background:var(--color-bg);color:var(--color-text);border:1px solid var(--rule-soft);">
                ${bot.routines.length} routine${bot.routines.length > 1 ? 's' : ''}
              </span>
            ` : ''}
            <span style="font-size:10px;padding:2px 6px;border-radius:4px;background:var(--color-bg);color:var(--muted);border:1px solid var(--rule-soft);">
              ${esc(bot.memory_scope)}
            </span>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderBotWorkspace(bot) {
  const isRunning = bot.status === "running" || bot.active_jobs_count > 0;
  const history = botLogs[bot.id] || [];

  return `
    <div style="background:var(--color-surface);border:1px solid var(--rule);border-radius:10px;overflow:hidden;">
      <!-- Workspace Top Bar -->
      <div style="padding:18px 24px;border-bottom:1px solid var(--rule-soft);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">
        <div style="display:flex;align-items:center;gap:14px;">
          <div style="
            width:42px;height:42px;border-radius:8px;
            display:grid;place-items:center;
            background:var(--accent-soft);color:var(--accent-text);
            border:1px solid var(--accent);font-weight:700;font-size:15px;
          ">
            ${bot.name.substring(0, 2).toUpperCase()}
          </div>
          <div>
            <div style="display:flex;align-items:center;gap:8px;">
              <h2 style="margin:0;font-size:18px;font-weight:700;color:var(--color-text);">${esc(bot.name)}</h2>
              <span style="font-size:11px;font-family:var(--mono);padding:2px 6px;border-radius:4px;background:var(--accent-soft);color:var(--accent-text);">
                ${esc(bot.model)}
              </span>
            </div>
            <div style="font-size:13px;color:var(--soft);margin-top:2px;">${esc(bot.role)}</div>
          </div>
        </div>

        <div style="display:flex;align-items:center;gap:10px;">
          ${!bot.is_default ? `
            <button type="button" class="btn" id="editBotBtn" data-bot-id="${esc(bot.id)}"><i class="icon-pencil" aria-hidden="true"></i><span>Edit</span></button>
            <button type="button" class="btn stop" id="deleteBotBtn" data-bot-id="${esc(bot.id)}"><i class="icon-x" aria-hidden="true"></i><span>Delete</span></button>
          ` : `
            <span style="font-size:11px;color:var(--muted);border:1px solid var(--rule);padding:4px 8px;border-radius:4px;">Default Specialist</span>
          `}
        </div>
      </div>

      <!-- Workspace Sub-tabs -->
      <div style="display:flex;gap:4px;padding:0 24px;border-bottom:1px solid var(--rule-soft);background:var(--color-bg);">
        <button class="btn ${currentTab === 'chat' ? 'primary on' : ''}" data-tab="chat" style="border-radius:0;border:0;border-bottom:2px solid ${currentTab === 'chat' ? 'var(--accent)' : 'transparent'};padding:12px 16px;">Console & Prompt</button>
        <button class="btn ${currentTab === 'computer' ? 'primary on' : ''}" data-tab="computer" style="border-radius:0;border:0;border-bottom:2px solid ${currentTab === 'computer' ? 'var(--accent)' : 'transparent'};padding:12px 16px;">Computer Sandbox</button>
        <button class="btn ${currentTab === 'routines' ? 'primary on' : ''}" data-tab="routines" style="border-radius:0;border:0;border-bottom:2px solid ${currentTab === 'routines' ? 'var(--accent)' : 'transparent'};padding:12px 16px;">Routines (${(bot.routines || []).length})</button>
        <button class="btn ${currentTab === 'config' ? 'primary on' : ''}" data-tab="config" style="border-radius:0;border:0;border-bottom:2px solid ${currentTab === 'config' ? 'var(--accent)' : 'transparent'};padding:12px 16px;">Instructions & Persona</button>
      </div>

      <!-- Tab Content Arena -->
      <div style="padding:24px;">
        ${currentTab === 'chat' ? renderChatTab(bot, history) : ''}
        ${currentTab === 'computer' ? renderComputerTab(bot) : ''}
        ${currentTab === 'routines' ? renderRoutinesTab(bot) : ''}
        ${currentTab === 'config' ? renderConfigTab(bot) : ''}
      </div>
    </div>
  `;
}

function renderChatTab(bot, history) {
  return `
    <div style="display:flex;flex-direction:column;gap:18px;">
      <!-- Quick Starters -->
      <div>
        <div style="font-size:12px;font-weight:600;color:var(--soft);margin-bottom:8px;">Suggested Actions for ${esc(bot.name)}:</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button type="button" class="btn prompt-starter" data-prompt="Analyze active project state and give your recommendations based on your role.">
            Status Review
          </button>
          <button type="button" class="btn prompt-starter" data-prompt="Verify current project changes, inspect uncommitted git diffs, and report next tasks.">
            Inspect Git & Diff
          </button>
          <button type="button" class="btn prompt-starter" data-prompt="Run Antigravity CLI (agy) in background to implement the next high-priority task.">
            Implement with agy
          </button>
          <button type="button" class="btn prompt-starter" data-prompt="Perform an exhaustive security and boundary audit on current project files.">
            Security Audit
          </button>
        </div>
      </div>

      <!-- Execution Logs Window -->
      <div style="border:1px solid var(--rule);border-radius:8px;background:var(--color-bg);min-height:220px;max-height:440px;overflow-y:auto;padding:14px;font-family:var(--mono);font-size:12px;">
        ${history.length === 0 ? `
          <div style="color:var(--muted);text-align:center;padding:40px 0;">
            Ready to execute. Enter a prompt below or pick a suggested action to dispatch ${esc(bot.name)} through Antigravity CLI (agy).
          </div>
        ` : history.map(item => `
          <div style="margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--rule-soft);">
            <div style="display:flex;justify-content:space-between;color:var(--soft);margin-bottom:4px;">
              <span><strong>Task:</strong> ${esc(item.prompt)}</span>
              <span style="font-size:11px;">${new Date(item.ts).toLocaleTimeString()}</span>
            </div>
            <div style="color:var(--color-text);white-space:pre-wrap;background:var(--color-surface);padding:8px 10px;border-radius:6px;border:1px solid var(--rule-soft);">
              ${esc(item.output || item.status || "Executing...")}
            </div>
          </div>
        `).join("")}
      </div>

      <!-- Prompt Input Form -->
      <form id="botPromptForm" style="display:flex;gap:10px;align-items:flex-end;">
        <div style="flex:1;">
          <textarea id="botPromptInput" rows="3" placeholder="Instruct ${esc(bot.name)}... (runs via agy in isolated sandbox)" style="
            width:100%;padding:10px 12px;background:var(--color-bg);border:1px solid var(--rule);
            border-radius:8px;color:var(--color-text);font-family:var(--sans);font-size:13px;resize:vertical;
          "></textarea>
        </div>
        <button type="submit" class="btn primary" id="sendBotPromptBtn" ${isExecuting ? 'disabled' : ''} style="min-height:44px;padding:0 20px;font-weight:600;">
          <i class="icon-sparkles" aria-hidden="true"></i><span>${isExecuting ? 'Running...' : 'Run with agy'}</span>
        </button>
      </form>
    </div>
  `;
}

function renderComputerTab(bot) {
  return `
    <div style="display:flex;flex-direction:column;gap:18px;">
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));gap:14px;">
        <div style="padding:14px;background:var(--color-bg);border:1px solid var(--rule);border-radius:8px;">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase;">Sandbox Environment</div>
          <strong style="display:block;margin-top:4px;font-size:14px;color:var(--color-text);">Bubblewrap (bwrap)</strong>
          <span style="font-size:12px;color:var(--soft);">Host filesystem protected</span>
        </div>
        <div style="padding:14px;background:var(--color-bg);border:1px solid var(--rule);border-radius:8px;">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase;">Working Directory</div>
          <strong style="display:block;margin-top:4px;font-size:13px;color:var(--accent-text);font-family:var(--mono);">~/Projects/devpilot/</strong>
          <span style="font-size:12px;color:var(--soft);">Isolated workspace root</span>
        </div>
        <div style="padding:14px;background:var(--color-bg);border:1px solid var(--rule);border-radius:8px;">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase;">Browser Engine</div>
          <strong style="display:block;margin-top:4px;font-size:14px;color:var(--color-text);">Obscura V8 / Chromium</strong>
          <span style="font-size:12px;color:var(--soft);">DOM scraping & visual QA ready</span>
        </div>
      </div>

      <div style="border:1px solid var(--rule);border-radius:8px;padding:16px;background:var(--color-bg);">
        <h4 style="margin:0 0 10px;font-size:14px;color:var(--color-text);">Sandbox Privileges & Boundaries</h4>
        <ul style="margin:0;padding-left:18px;font-size:13px;color:var(--soft);line-height:1.6;">
          <li>All command execution runs in a sandboxed sub-shell under Bubblewrap isolation.</li>
          <li>Antigravity CLI operations pass <code style="font-family:var(--mono);color:var(--accent-text);">--sandbox --dangerously-skip-permissions</code> automatically.</li>
          <li>Screen actions and browser automation use isolated browser sessions with zero host leak.</li>
        </ul>
      </div>

      <div style="display:flex;gap:10px;">
        <button type="button" class="btn" id="checkComputerStatusBtn">
          <i class="icon-refresh-cw" aria-hidden="true"></i><span>Refresh Sandbox Status</span>
        </button>
      </div>
    </div>
  `;
}

function renderRoutinesTab(bot) {
  const routines = bot.routines || [];
  return `
    <div style="display:flex;flex-direction:column;gap:18px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <h4 style="margin:0;font-size:14px;color:var(--color-text);">Automated Triggers & Routines</h4>
        <button type="button" class="btn" id="addRoutineBtn"><i class="icon-plus" aria-hidden="true"></i><span>Add Routine</span></button>
      </div>

      <div style="display:flex;flex-direction:column;gap:10px;">
        ${routines.map(r => `
          <div style="padding:14px;background:var(--color-bg);border:1px solid var(--rule);border-radius:8px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
            <div>
              <div style="display:flex;align-items:center;gap:8px;">
                <strong style="font-size:14px;color:var(--color-text);">${esc(r.title)}</strong>
                <span style="font-size:11px;font-family:var(--mono);background:var(--color-surface);padding:2px 6px;border-radius:4px;border:1px solid var(--rule-soft);">
                  ${esc(r.schedule)}
                </span>
                <span style="font-size:11px;color:${r.active ? 'var(--color-green)' : 'var(--muted)'};">
                  ${r.active ? '● Active' : '○ Paused'}
                </span>
              </div>
              <div style="font-size:12px;color:var(--soft);margin-top:4px;">${esc(r.prompt)}</div>
            </div>
            <button type="button" class="btn run-routine-btn" data-bot-id="${esc(bot.id)}" data-routine-id="${esc(r.id)}">
              <i class="icon-sparkles" aria-hidden="true"></i><span>Run Now</span>
            </button>
          </div>
        `).join("")}
        ${routines.length === 0 ? `
          <div style="padding:30px;text-align:center;color:var(--muted);border:1px dashed var(--rule);border-radius:8px;">
            No routines configured for this bot yet. Add a scheduled prompt or event trigger above.
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

function renderConfigTab(bot) {
  return `
    <div style="display:flex;flex-direction:column;gap:18px;">
      <div>
        <label style="display:block;font-size:12px;font-weight:600;margin-bottom:6px;color:var(--soft);">System Prompt & Persona</label>
        <div style="padding:14px;background:var(--color-bg);border:1px solid var(--rule);border-radius:8px;font-size:13px;line-height:1.6;color:var(--color-text);white-space:pre-wrap;">
          ${esc(bot.instructions)}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
        <div style="padding:14px;background:var(--color-bg);border:1px solid var(--rule);border-radius:8px;">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase;">Memory Boundary</div>
          <strong style="display:block;margin-top:4px;font-size:14px;color:var(--color-text);text-transform:capitalize;">${esc(bot.memory_scope)} Memory</strong>
          <span style="font-size:12px;color:var(--soft);">
            ${bot.memory_scope === 'shared' ? 'Knowledge shared across Space teammates' : 'Strictly isolated to this bot'}
          </span>
        </div>
        <div style="padding:14px;background:var(--color-bg);border:1px solid var(--rule);border-radius:8px;">
          <div style="font-size:11px;color:var(--muted);text-transform:uppercase;">Reasoning Effort</div>
          <strong style="display:block;margin-top:4px;font-size:14px;color:var(--color-text);text-transform:capitalize;">${esc(bot.thinking_level || 'high')} Thinking</strong>
          <span style="font-size:12px;color:var(--soft);">Deep cognitive trace enabled</span>
        </div>
      </div>
    </div>
  `;
}

function attachEvents() {
  const el = root();
  if (!el) return;

  // Bot card selection
  el.querySelectorAll(".bot-card").forEach(card => {
    card.onclick = () => {
      selectedId = card.dataset.botId;
      localStorage.setItem("kryzen.selectedBot", selectedId);
      shell();
    };
  });

  // Filter tabs
  el.querySelectorAll("[data-filter]").forEach(btn => {
    btn.onclick = () => {
      filter = btn.dataset.filter;
      shell();
    };
  });

  // Sub-tabs
  el.querySelectorAll("[data-tab]").forEach(btn => {
    btn.onclick = () => {
      currentTab = btn.dataset.tab;
      localStorage.setItem("kryzen.botTab", currentTab);
      shell();
    };
  });

  // Prompt starters
  el.querySelectorAll(".prompt-starter").forEach(btn => {
    btn.onclick = () => {
      const input = $("#botPromptInput");
      if (input) {
        input.value = btn.dataset.prompt;
        input.focus();
      }
    };
  });

  // Send prompt
  const form = $("#botPromptForm");
  if (form) {
    form.onsubmit = async (e) => {
      e.preventDefault();
      const input = $("#botPromptInput");
      const prompt = input?.value?.trim();
      if (!prompt) return;

      isExecuting = true;
      shell();

      try {
        if (!botLogs[selectedId]) botLogs[selectedId] = [];
        botLogs[selectedId].unshift({
          prompt: prompt,
          status: "Dispatched to Antigravity CLI (agy)...",
          output: "Initializing execution in Bubblewrap sandbox...",
          ts: Date.now(),
        });
        shell();

        const res = await api("/api/bots/run", {
          id: selectedId,
          prompt: prompt,
          background: true,
          mode: "auto",
        });

        if (res.ok) {
          botLogs[selectedId][0].status = `Running job ${res.id || ''}`;
          botLogs[selectedId][0].output = `Command dispatched: ${res.cmd || 'agy task running'}\nJob ID: ${res.id || 'ok'}`;
          toast(`Dispatched to ${res.bot_name || 'bot'}`, "ok");
        } else {
          botLogs[selectedId][0].status = "Error";
          botLogs[selectedId][0].output = res.error || "Execution failed";
          toast(res.error || "Run failed", "err");
        }
      } catch (err) {
        toast(String(err), "err");
      } finally {
        isExecuting = false;
        shell();
      }
    };
  }

  // New Bot Button & Modal
  const newBtn = $("#newBotBtn");
  const modal = $("#botModal");
  if (newBtn && modal) {
    newBtn.onclick = () => {
      $("#modalTitle").textContent = "Create Autonomous Teammate";
      $("#formBotId").value = "";
      $("#formId").value = "";
      $("#formId").disabled = false;
      $("#formName").value = "";
      $("#formRole").value = "";
      $("#formDesc").value = "";
      $("#formInstructions").value = "";
      modal.showModal();
    };
  }

  const closeBtn = $("#closeBotModalBtn");
  const cancelBtn = $("#cancelBotModalBtn");
  if (closeBtn && modal) closeBtn.onclick = () => modal.close();
  if (cancelBtn && modal) cancelBtn.onclick = () => modal.close();

  const botForm = $("#botForm");
  if (botForm && modal) {
    botForm.onsubmit = async (e) => {
      e.preventDefault();
      const botData = {
        id: $("#formId").value.trim().toLowerCase(),
        name: $("#formName").value.trim(),
        role: $("#formRole").value.trim(),
        model: $("#formModel").value,
        color: $("#formColor").value,
        description: $("#formDesc").value.trim(),
        instructions: $("#formInstructions").value.trim(),
        memory_scope: "isolated",
        thinking_level: "high",
        sandbox_type: "bubblewrap",
        tools: ["agy_run", "pc_shell", "pc_read_file", "pc_write_file"],
      };

      try {
        const res = await api("/api/bots/save", botData);
        if (res.ok) {
          toast("Teammate saved", "ok");
          modal.close();
          await refresh();
        } else {
          toast(res.error || "Failed to save", "err");
        }
      } catch (err) {
        toast(String(err), "err");
      }
    };
  }

  // Refresh button
  const refBtn = $("#refreshBotsBtn");
  if (refBtn) refBtn.onclick = () => refresh(true);
}

export async function refresh(force = false) {
  try {
    const res = await api("/api/bots");
    if (res && res.ok && Array.isArray(res.bots)) {
      bots = res.bots;
      if (activeMode() === "bots") shell();
    }
  } catch (err) {
    console.error("Failed to load bots:", err);
  }
}

// Subscribe to mode change
onMode(mode => {
  if (mode === "bots") {
    if (bots.length > 0) shell();
    refresh();
  }
});

// Initial load
refresh().then(() => {
  if (activeMode() === "bots") shell();
});
