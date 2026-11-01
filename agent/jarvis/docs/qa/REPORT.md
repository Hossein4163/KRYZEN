# Jarvis Studio verification — 2026-10-24

Result: PASS for the implemented local UI, API and runtime configuration behavior.

## Automated evidence

`python3 -m unittest discover -s agent/jarvis/tests -v`: **17 tests passed**, exit 0.

Tests use temporary storage and a fake bridge; no user projects or model APIs are changed. Covered:
- Canvas round trips, extension preservation, duplication, stale revision rejection, schema/path validation and generated-file protection.
- Active routing derives its allowlist from linked agent files and fails closed if the active canvas disappears.
- Canonical Markdown task updates preserve surrounding content, reject stale revisions and respect project boundaries.
- Approval is tied to the plan revision and becomes outdated after edits.
- Real HTTP handlers enforce same-origin mutation protection, object-shaped JSON, invalid-input errors and active-run guards.
- Pause holds the next operation until resumed; Stop releases paused work. HTTP controls and session status expose those flags.
- Runtime integration includes assigned skill names, filters specialist delegation and grants plan read/update tools according to file permissions.

Python syntax compilation passed for server, engine, studio and skill pack. `node --check` passed for studio.js and the extracted original index script.
All 18 new skills passed the skill-creator validator. A second actual skill pack installation created 0 files, changed 0 assignments, retained 26 skills and preserved the custom canvas hash across workflow regeneration.

## Live local integration

The Jarvis service is active at http://127.0.0.1:8770. Its Studio overview reports 3 canvases, 26 vault skills, 6 agents and 21 catalog tools. Live project plan GETs work for both existing projects. The authenticated PC bridge discovers and reads the new skills. Runtime construction for an existing selected project includes the plan context and role skills without calling a model. A POST lacking the required header returned 403.

## Browser evidence

Chromium via agent-browser tested the actual local app at 1440×1000, 768×1000 and 390×844, plus independent evaluation at 375px. No JavaScript page errors or horizontal document overflow were observed. The tablet canvas now has 742px of usable width at a 768px viewport. Mobile short-plan content uses its natural height instead of a large blank region.

A disposable server on port 8771 used the same production HTTP handlers and real UI with temporary canvas storage and an in-memory project bridge. Browser actions verified:
- Edit a note in its inspector → Save → read persisted content from the API.
- Add a linked Build agent → connect to a note with a label → Save → Activate routing.
- Approve a saved plan → mark a task complete → observe `[x]` in the actual canonical Markdown and outdated approval.
- Edit/save plan source and approve through an unsaved-source save.

The fixture disabled model execution and did not touch real project plans or approval files. Its browser and process were closed after testing.

Additional browser smoke verified skill searching/filtering, agent/card and edge inspectors, node/edge removal, Code navigation and keyboard card selection. The independent design evaluation returned PASS. Skills-page WCAG A/AA automated checks reported no violations; this is not a full application accessibility audit.

Screenshots:
- [Desktop Flow](screenshots/flow-1440.png)
- [Tablet Flow](screenshots/flow-768.png)
- [Mobile Flow](screenshots/flow-390.png)
- [Desktop Plan](screenshots/plan-1440.png)
- [Mobile Plan](screenshots/plan-390.png)

## Practical limits

- No live NVIDIA inference, autonomous coding job, external deployment or n8n import was run during this work.
- Canvas connections guide the orchestrator; they are not a deterministic workflow executor. The active canvas restricts linked specialist delegation for subsequent Jarvis turns only.
- Pause/Stop act at model/tool boundaries; an in-progress operation can finish first.
- Approval is content-specific; even a task progress edit makes its recorded revision outdated. Existing user-authorized scope is still represented in conversation/checkpoints.
- Canvas-only control files remain read-only to agent bridge tools. Users edit them through Jarvis or Obsidian.
- The workspace has no Git repository, so no commit was created.
