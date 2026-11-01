# Durable parallel project execution — 2026-10-25

Release 1.1.0-10 adds real project task graphs, durable tool history, source-aware continuation and a visible dependency view. Open **Tasks** in the application header for the full graph, or the Tasks side pane for live progress.

Independent tasks use up to three worker lanes. Every model attempt, including retries, shares a two-stream queue with at least 0.5 seconds between starts. Provider Retry-After cooldown applies to all queued requests. Paused waiters do not block unrelated runnable requests; stop removes queued requests.

Tasks declare exact source inputs, owned output files and prerequisite IDs. Conflicting source access waits; dependencies receive actual predecessor results. Parallel lanes use revision-checked file tools. The coordinator runs shell commands, project-wide builds and QA after the join. A completed lane is a saved handoff, not proof that the entire project passed QA.

Each selected project stores task definitions, states, results and source hashes in `.devpilot/execution.json`. Coordinator and task tool transcripts are checkpointed before side effects and after each result in `.devpilot/task-history/*.json`, with incremental append-only `.jsonl` journals. These local histories are added to the project's `.gitignore`. Reload restores the visible graph; a new coordinator receives previous work and checkpoint references.

`resume_parallel_tasks` reuses exact saved graph definitions. Unchanged completed work uses cached results without invoking its agent again. Changed source, failed tasks and uncertain effects after restart require reconciliation with existing files and history. Verified later task writes can supersede earlier output; unrelated concurrent user edits are never adopted as verified work. The scheduler does not blindly replay interrupted writes.

Validation:

- 69 backend tests, including 14 orchestration tests: true overlapping threads, dependency joins, source conflict serialization, cache reuse after reload, concurrent user edits, source ownership, revision conflicts, durable coordinator/task checkpoints, interrupted recovery, request bounds, pacing, cancellation and shared cooldown.
- Six browser execution checks using the real scheduler, disposable source files and controlled fake model streams. Three saved nodes and results restore after reload; repeated execution reuses completed tasks without changing their start timestamps.
- 39 existing browser checks across reliability, editor, mesh, phone and project capabilities.
- Seven layout checks at 923×516 in Chromium and native GTK4/WebKit, including cold configuration load and recovery. Compact-height styling restores usable mesh space.
- Six packaging regressions. No paid model calls were used for this feature's automated QA.

Package/build sources and the primary release remain under `/home/kry`; activation preserves settings, secrets, project data and chat sessions.
