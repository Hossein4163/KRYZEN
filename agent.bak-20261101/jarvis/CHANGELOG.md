# Changelog

## 2026-10-27 — Super upgrade

- Trace every model/tool/delegation call with real token usage, latency and full inputs/outputs; new Trace view with timeline, log, inspector, replay and export.
- Home dashboard: running work, run queue, approvals, spend, projects, deep health with backend repair, skills, project memory and runtime settings.
- Token diet: masked old tool results, smarter truncation, folded history, ledger digest, on-request tools and per-run budgets.
- Run queue, adaptive request concurrency and per-lane cancel; project memory, repo map, failure playbooks and verify policy.
- Command palette, review mode for file writes, notifications; skills usage, versions, imports, drafts and per-project overrides.
- Web UI only (desktop package removed); backend containers restart automatically.

## 1.1.0-10 — 2026-10-25

- Execute independent project tasks in three bounded lanes with real dependency joins and exact source ownership.
- Queue all model attempts with two concurrent streams, spaced starts and a shared provider cooldown.
- Save coordinator/task tool checkpoints and incremental history; resume exact saved graphs and reuse unchanged completed work.
- Require source reconciliation for changed or uncertain interrupted work; preserve concurrent user edits.
- Add live Tasks pane and expandable dependency graph with request queue, saved handoffs and reload recovery.
- Restore usable mesh space in short native windows and honor the configured workspace in code tools.

## Unreleased — 2026-10-24

- Restyle the native studio with charcoal glass cards, bright inset edges, blue actions, pill navigation and real team/tool/skill counts, following the supplied visual reference.
- Add pointer and keyboard resizing to both side panels, separate responsive dimensions, saved preferences, bounds and double-click reset.
- Keep resize controls hidden for collapsed/inactive panels and adapt them to stacked phone/tablet layouts.
- Package the theme and resizing assets in Arch release 1.1.0-7.


- Fix cold startup crashing before configuration, projects and sessions load when restoring panel layout.
- Fit the full agent mesh and large Flow canvases into the available viewport; provide a retry for missing configuration.
- Restore responsive desktop, tiled-window and phone layouts; put the active workspace first on narrow screens.
- Fix inactive Agy logs and collapsed side panels leaking into other workspaces, clipped panel controls and keyboard access to expand controls.
- Ignore stale session-list responses after a new conversation starts, preventing project intake from losing its session.
- Add browser layout regressions and opt-in native GTK4/WebKit verification; rebuild Arch release 1.1.0-6.


- Make agent replies and specialist handoffs concise while keeping detailed work in project files.
- Set explicit output budgets and efficient reasoning for the verified Nemotron 3.5 model family.
- Recover once from output-length failures without executing truncated tool calls or replaying completed work.
- Verify 54 automated tests and a successful live NIM/local-tool check.

- Restore the user's preferred circular/orbital mesh: colored cores, glowing halos and moving tool satellites, retaining drag/keyboard movement and all improved controls.
- Separate circular layout persistence from older rectangular layouts and fix first-click Reset after opening a hidden mesh.

- Redesign Mesh with readable agent cards, following connections, pointer/keyboard positioning and separate saved phone/desktop layouts.
- Add grouped layer/motion controls, layout reset, pan/zoom/fit and a separate navigation band.
- Improve Flow control groups, selection centering/clearing, visible mobile routing/read-only badges and 44px touch targets.
- Verify 28 browser scenarios, native drag persistence, reduced motion, responsive screenshots and independent design review.

- Add Marketing, Product, Content, SEO and Operations agents, six role skills and optional active-canvas handoffs.
- Add verified Uilora/ForgeUI/Uiverse/Sileo/Blobatar builder guidance and browser research tools for Build.
- Add header New Project dialog; fix new-project intake targeting, duplicate creation and unsaved-change handling.
- Add fresh structured continuation context, nested/background job recovery and duplicate project-run protection.
- Add a local Blobatar avatar and improve larger-team mesh readability.
- Verify 49 automated tests, 17 disposable browser scenarios and responsive layouts at 390/768/1440 pixels.

- Add editable Obsidian Canvas workspace with notes, linked agents, edges, inspector, pan/zoom, keyboard controls and import/export.
- Add canonical Markdown plan workspace with milestone progress, editing, preview, approval and explicit run actions.
- Add optional specialist routing from a saved canvas and revision checks for concurrent edits.
- Add cooperative pause/resume and project plan tools/context in the runtime.
- Add 18 curated role-assigned skills, searchable library and responsive graphite interface.
- Add isolated backend/HTTP/runtime tests and browser QA evidence.

### Reliability audit

- Persist active chats atomically and recover interrupted runs; stabilize SSE cursors and replay.
- Fix pause response ordering, duplicate sends, project/session isolation and fast response rendering.
- Reject stale editor/plan/control saves and protect existing files; add explicit editor Reload.
- Fix Code dock tab collisions, search errors, script quoting and Git commit failure handling.
- Validate tool inputs and stream completion; report failed tools accurately and bound retries.
- Share plan parsing with the bridge; validate project paths and tolerate partial journals.
- Preserve job metadata/output, terminate timed-out process groups and restore failed skill changes.
- Compile role skill assignments into both runtimes; add real service health and failure reporting.
- Expand to 37 automated tests plus a repeatable 9-scenario disposable browser suite.
