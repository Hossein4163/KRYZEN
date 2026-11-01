# K.R.Y.Z.E.N super upgrade — plan

| Field | Value |
|---|---|
| Status | 🟢 shipped 2026-10-27 (see Delivery below) |
| Date | 2026-10-26 |
| Scope | Web UI only (http://127.0.0.1:8770). No desktop package. |
| Goal | See exactly what every agent does, spend far fewer tokens, run more work in parallel, and make the studio faster, smarter and easier to drive. |

## Where we start (measured 2026-10-26)

| Area | Today | Problem |
|---|---|---|
| Tokens | No usage is recorded at all. Every model step resends system prompt + all tool schemas + up to 30 history messages + every tool result (≤14 000 chars each). Orchestrator adds ≤40 000 chars of ledger memory every turn. | Cost grows ~quadratically with steps (Build: up to 90 steps). No way to see or cap it. |
| Prompts | Orchestrator 6.7K chars + 25 tool schemas; specialists 2–3.4K + 6–16 tools. | Every agent pays for every tool it *might* use, on every step. |
| Memory (RAM) | Sessions stay in `LIVE` forever; 4 000 events each; chat/Activity DOM never virtualized. | Long days → growing memory and slower UI. |
| Memory (agent) | Only the execution ledger + checkpoints. No durable "what we decided / learned" per project. | Agents rediscover the same facts; repeat research. |
| Parallel | Task DAG with exact file ownership, 3 workers, global gate of 2 model streams. One run per project. | Fixed concurrency; no per-lane isolation for code; no queue of runs. |
| Visibility | Activity log: 400 lines, 240-char previews. No per-model-call data. | You cannot see prompts, full tool I/O, latency, retries or why a step was taken. |
| Dashboard | Mesh / Flow / Plan / Code / Control views. | No single "what is happening across everything" screen. |
| UI code | `index.html` 2 000 lines + 4 overlapping stylesheets. | Hard to change safely; slow to iterate. |
| Ops | Docker bridges lost their IPs today (DNS via 172.17.0.1 broke every container). | Not detected; it looked like "Jarvis is broken". |

## Principles

1. **Measure first.** Every model call and tool call becomes a recorded span; all later work is judged by those numbers.
2. **Full data on disk, small data in context.** Agents get summaries + pointers; humans can always open the full thing.
3. **Each milestone ships alone** and is verified with the existing test suite + browser checks before the next starts.
4. **No build step.** Plain ES modules served by `server.py`; no npm toolchain required to run.

---

## M1 — Trace foundation (observability core) · size M

Everything else depends on this.

- **Span store**: one JSONL file per run in `sessions/<id>/trace-<turn>.jsonl`. Span types: `model_call` (agent, model, prompt chars + tokens, completion tokens, latency, time-to-first-token, retries, finish reason), `tool_call` (args, full output, exit code, duration, files touched), `delegation`, `lane`, `pause/stop`.
- **Real token counts**: request `stream_options: {include_usage: true}` from NIM; fall back to a char/4 estimate when usage is missing.
- **Full tool output stored** as a blob (`sessions/<id>/blobs/<sha>.txt`); events carry only a preview + blob id.
- API: `GET /api/trace?session=&turn=`, `GET /api/blob?id=` (lazy, size-capped).
- **Accept:** a finished run shows exact tokens per agent and per step; every tool call's full output opens from the UI; trace writing adds < 2 % run time.

## M2 — Token & memory diet · size L

Target: **−50 to −70 % prompt tokens** on a long Build run (measured with M1 traces on a fixed replay task).

- **Observation masking**: after the model has used a tool result, replace it in later steps with a one-line summary + blob pointer (`read_blob` tool to re-open it). Keep the last 2 results verbatim.
- **Head/tail tool results**: large outputs go to the model as head + tail + match lines (for search/test logs), not the first 14 000 chars.
- **Rolling conversation memory**: messages older than the last 6 turns are folded into a running summary (cheap model), stored with the session.
- **Ledger digest**: send a ≤2 000-char digest of completed work instead of ≤40 000 chars; add `ledger_lookup(task_id)` for details.
- **Per-step tool subsetting**: expose a core tool set + tools relevant to the current task/skill; others listed by name only and enabled on request.
- **Stable prompt prefix**: order system → skills index → tool schemas → dynamic context so provider-side prefix caching can hit.
- **Model tiers**: small/fast model for summaries, classification, file triage and commit messages; large model for planning and code. Configurable in Control › Models.
- **Budgets**: per-run token and time caps (soft warning at 80 %, pause at 100 %), shown live.
- **Server RAM**: evict idle sessions from memory after 15 min (reload on demand); keep only the active turn's token events; history already persisted.
- **Browser RAM**: virtualize chat, Activity and trace lists (render only visible rows).
- **Accept:** replay benchmark shows the token target met with equal task success; server RSS flat over a 4-hour soak.

## M3 — Live log & trace views ("see exactly what happens") · size M

- **Run timeline**: horizontal swimlanes per agent/lane; bars for model calls (colored by latency) and tool calls; retries and rate-limit waits visible as gaps; click any bar → inspector.
- **Inspector**: the exact messages sent (system, history, masked results), the model's reasoning summary, the raw tool args, full output, files changed with diff, tokens and timing.
- **Log view**: filter by agent / kind / status / text, follow mode, jump to time, copy, export JSONL. Errors pinned at top.
- **Delegation tree**: who asked whom for what, with each handoff's STATUS/DONE/NEXT/BLOCKERS.
- **Step-through replay** of a finished run.
- **Accept:** for any past run you can answer "why did it do X?" from the UI alone.

## M4 — Super dashboard · size M

New default view **Home**:

- **Now**: active runs with live lanes, current step per agent, queue, rate-limit cooldown, pause/stop per run.
- **Projects**: plan progress bars, last activity, next task, blockers, one-click Continue.
- **Spend**: tokens today / this week, per project and per agent; most expensive steps (links into M3).
- **Health**: engine, bridge, backend, search, Docker networking/DNS (detects today's failure and shows the fix), disk space.
- **Attention inbox**: approvals agents are waiting on, failed tools, finished runs you haven't seen.
- Browser notifications when a run finishes, fails or needs approval.
- **Accept:** from Home alone you can see and steer everything that is running.

## M5 — Parallel work v2 · size L

- **Run queue**: start several runs (different projects or tasks); they wait for capacity instead of being refused.
- **Adaptive concurrency**: the request gate grows/shrinks from 429 / Retry-After feedback (start 2, range 1–6) instead of a fixed 2.
- **Isolated code lanes**: each code-writing lane works in its own `git worktree`; the coordinator merges, runs checks, and shows conflicts for review.
- **Lane controls**: pause, retry, cancel or reassign a single lane without stopping the whole run.
- **Accept:** a 4-lane task finishes faster than serial with no file conflicts; a 429 storm slows down instead of failing.

## M6 — Intelligence · size L

- **Project memory**: `.devpilot/memory.md` of decisions, conventions, gotchas and facts, updated at the end of each run (reviewable in Plan Studio); relevant entries retrieved per task (keyword first, embeddings via NIM later).
- **Repo map**: symbol/outline index per project (ctags-style) so agents read the right 40 lines instead of whole files.
- **Plan → act → verify**: every task carries acceptance criteria; a short self-check step runs before handoff; QA gates "done".
- **Failure playbooks**: recognized tool/test failures trigger targeted recovery (missing dep, port in use, type error) instead of generic retries.
- **Accept:** fewer repeated research calls (trace-measured), higher first-pass QA rate on the benchmark tasks.

## M7 — UI/UX overhaul · size L

- Split `index.html` into ES modules (`chat`, `mesh`, `studio`, `code`, `control`, `dashboard`, `trace`) and one design-token stylesheet replacing the 4 overlapping ones.
- **Command palette** (Ctrl+K): every action, project, session, file, agent and setting.
- Resizable, remembered panes everywhere; consistent empty/loading/error states; keyboard-first navigation; full RTL support for Persian.
- **Review mode**: optionally approve file writes as diffs before they are applied.
- Session search and pinning; export a conversation with its trace.
- **Accept:** browser QA suite passes at 390 / 960 / 1440 px; Lighthouse-style interaction latency < 100 ms during a streaming run.

## M8 — Skills v2 · size M

- Usage stats per skill (loaded, by whom, run outcome) from traces.
- **Learned skills**: propose a new skill from a repeated successful pattern; you approve before it's installed.
- Versioning + diff + rollback; per-project skill overrides; a test prompt per skill.
- Import skills from `~/.claude/skills` and other packs.

## Also worth doing

- **Safety**: approval policy per tool class (shell, network, git push, paid APIs); secret scan before any write; per-run budget caps (from M2).
- **Ops watchdog**: periodic check for Docker bridge IPs and container DNS; one-click "repair backend" (recreate network) in Control › Services.
- **Backups**: nightly export of sessions, vault and `.devpilot/` folders.
- **Benchmarks**: a fixed set of replayable tasks used to compare tokens, time and success before/after every milestone.

## Order and dependencies

```
M1 Trace ──► M2 Token diet ──► M6 Intelligence
   │            │
   ├──► M3 Log/trace views ──► M4 Dashboard
   │
   └──► M5 Parallel v2
M7 UI overhaul runs alongside (dashboard + trace views are built as the first new modules)
M8 Skills after M1 (needs usage data)
```

Recommended start: **M1 → M3 → M2** (see everything, then cut tokens with real numbers), then M4, M5, M6, M8, with M7 folded in.

## Decisions (made 2026-10-27, changeable in Home › Runtime settings)

1. Small model: `nvidia/nemotron-3.5-bolt-e4b` (verified, 0.5 s), falls back to the orchestrator model.
2. Git worktrees: **not used** — lanes already write only declared, disjoint files with revision checks and cannot run shell, so worktrees add no isolation. Effort went to the run queue, adaptive concurrency and per-lane cancel instead.
3. Budgets: 400 K tokens / 60 min per run; warn at 80 %, pause at 100 %, Resume adds 50 %.
4. Review mode: off by default; toggle in Runtime settings or the command palette.

## Delivery (2026-10-27)

| Milestone | Shipped | Where |
|---|---|---|
| M1 Trace | Spans per model/tool/delegation call, real NIM token usage (`stream_options.include_usage`, estimate fallback), TTFT/latency/attempts, content-addressed blobs (prompt messages + full tool output), global usage ledger | `telemetry.py`, `engine.py`, `/api/trace`, `/api/blob` |
| M2 Token diet | Observation masking (`read_blob` to reopen), head/tail/error-line truncation, history folding by the small model (cached per session), ledger digest + `ledger_lookup`, on-request tools (`enable_tools`), per-run budgets, idle-session eviction, `content-visibility` lists | `diet.py`, `runtime_settings.py`, `server.py`, `ui/kryzen.css` |
| M3 Trace view | Timeline lanes per agent/lane, filterable log (agent/kind/failures/text), inspector with exact messages (masked ones marked), full tool I/O, delegation tree, per-agent table, step-through replay (↑/↓, Prev/Next, slider), JSONL export, live follow | `ui/trace.js` |
| M4 Home | Now (runs, budget bars, lanes with cancel, pause/stop), attention inbox, run queue, spend (today/7 days, by agent/project), projects with Continue, deep health (incl. Docker bridge + container DNS) with Repair backend, recent conversations, notifications | `ui/dashboard.js`, `ops.py` |
| M5 Parallel v2 | Run queue (send while busy → queued, auto-start FIFO), adaptive request concurrency (−1 per 429, +1 per 10 clean calls, max setting), configurable lanes, per-lane cancel | `server.py`, `orchestration.py` |
| M6 Intelligence | Project memory (`.devpilot/memory.md`, `recall`/`remember`, relevant facts injected per turn, auto-extraction after runs), `repo_map`, plan→act→verify policy, failure playbooks appended to failed tool results | `brain.py`, `engine.py` |
| M7 UI/UX | Command palette (Ctrl+K), Home/Trace as ES modules with shared tokens, review mode (diff approval dialog + inbox), queued-message bubbles, usage footer per reply, Activity lines for model calls/budget/memory/rate limits | `ui/*.js` |
| M8 Skills v2 | Usage stats from traces, version snapshots on every save + rollback, imports from `~/.claude/skills`/`~/.agents/skills`, skill drafts from a run (approve to install), per-project overrides, test prompts | `skills2.py`, Home › Skills |

Not done / partial:
- The legacy `index.html` script (2 000 lines) was **not** split into modules; new features are modules and the legacy code only gained small hooks. Splitting it is a separate refactor.
- Embedding-based memory retrieval is not implemented; recall is keyword-ranked.
- Provider prefix caching cannot be verified on NIM; prompts keep static content first.

Verification: 84 unit tests (15 new), 7 existing browser suites (52 scenarios) on the disposable fixture, UI checked at 1440 and 960 px, and one live read-only NIM run (real usage reported, repo_map + recall used, small-model memory extraction ran).
