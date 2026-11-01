# Project agents and continuation verification

2026-10-24

## Delivered

- Marketing, Product, Content, SEO and Operations specialists; 11 total agents and 32 skills. Each specialist has defined artifacts, role skills, actual tools and checkpoint handoffs. Added the optional specialists to the active mission canvas while preserving existing cards, geometry and extension fields.
- Repeatable `capability_pack.py --install` installer with rollback on workflow rebuild failure. Both workflows were regenerated; the main agent workflow contains the expanded team and Auto-Resume references that workflow.
- Uilora, ForgeUI, Uiverse, Sileo and Blobatar builder defaults, with Browser/Search/Fetch tools available to Build and a per-project source/compatibility record. See [source decisions](../references/UI-SOURCES.md).
- Header New Project dialog shared with Control > Projects. Labeled fields, slug validation, duplicate protection, preserved failure input, guarded unsaved edits, one submission at a time, focus restoration and optional intake. Creation selects the new project before any intake run.
- Dedicated `/api/continue` with explicit project validation, a fresh runtime resume snapshot and duplicate project-run protection. Resume considers active jobs (including project subdirectories), interrupted changes, blockers, current plan tasks and plan revision. Completed tasks lead to verification rather than restarting the build. Recent persisted job metadata is included.
- Locally generated Blobatar user avatar, with no runtime external requests. Compact, evenly spaced skill markers and clearer agent labels support the larger mesh; optional specialists do not appear as mandatory lifecycle phases.

## Evidence

- **49 automated tests passed**, covering the existing reliability/studio/API behavior plus continuation priorities, stale checkpoint reconciliation, nested project jobs, duplicate creation, installer idempotence/rollback, project-scoped continuation, duplicate active runs, fresh runtime context and the local avatar endpoint.
- **17 browser scenarios passed** in disposable fixture workspaces using the real HTTP handlers, bridge handlers and frontend. The original nine editor/plan/chat/pause/search checks pass. Eight additional scenarios cover dialog validation and focus, duplicate creation, unsaved edits, submission locking, create-only behavior, registration/resume context, optional intake/new-project isolation, Blobatar rendering, project/Plan Continue and specialist controls.
- Six new skills pass the skill-creator validator. Python compilation and inline/client JavaScript syntax checks pass. Installer rerun reports zero changed source files.
- Browser screenshots reviewed at **390, 768 and 1440 pixels**; document scroll width equals viewport width at each size. New Project dialog fits at 390 pixels and focuses its title field. Browser console and page-error reports are empty.
- Imported both updated workflows into n8n successfully; active-workflow listings were empty before and after, preserving draft status. Reloaded Jarvis and PC Bridge only after confirming zero active runs/jobs. Live endpoints expose 11 agents, 32 skills, the local avatar (HTTP 200) and structured continuation. Jarvis, PC Bridge, n8n and SearXNG report healthy.

Evidence images: `screenshots/capabilities-390.png`, `capabilities-768.png`, `capabilities-1440.png`, `new-project-390.png`.

## Limits

Browser chat tests use a deterministic fake engine, make no paid model calls and mutate only temporary fixture projects. Compiled role prompts/tool assignments and active routing were inspected. Actual marketing campaign quality, deployment to external infrastructure and future project-specific component integrations were not exercised. No campaigns were published, no outreach was sent and no ads were purchased. UI libraries are builder defaults; compatibility and access are verified again for each project, rather than blindly installing incompatible packages.

Backup before implementation: `/tmp/jarvis-growth-vh4hfutv`.
