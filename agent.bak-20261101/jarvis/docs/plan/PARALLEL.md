# Parallel project execution — 2026-10-25

Implement real bounded fan-out/fan-in using named task DAGs, dependencies and exact source-file ownership. All provider attempts share a process-wide FIFO request gate (two concurrent streams, spaced starts, shared Retry-After cooldown). Preserve stop/pause and complete-stream tool invariants.

Persist task definitions, states, results, source revisions and per-agent tool checkpoints inside the selected project's `.devpilot/execution.json`. Continue reuses completed matching tasks only when source fingerprints agree; interrupted effects and externally modified outputs require source reconciliation instead of blindly repeating writes. Supply completed-work memory to the next orchestrator. Maintain model/tool authorization and canvas restrictions.

Parallel lanes may read sources and write only their declared exact files using revision-checked file tools. Shell/custom commands, project-wide mutations, nested delegation and approvals stay in the coordinating lane; run project-wide tests after fan-in. Dependencies pass actual predecessor results. Parallel is an execution policy, not a claim that all work is independent.

Expose saved DAG, task status, source paths, elapsed times and request queue in a Tasks pane and larger dependency view; restore after reload. Keep duplicate agent invocations distinct in chat/activity. Verify with fake engines, controlled barriers, temporary project ledgers, request limits/cancellation/cooldown, continuation/no replay and browser reload. Do not consume live models in automated QA.
