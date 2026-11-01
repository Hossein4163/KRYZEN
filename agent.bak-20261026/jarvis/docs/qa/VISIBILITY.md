# K.R.Y.Z.E.N visibility and responsive repair — 2026-10-24

The installed 1.1.0-5 client aborted while restoring its panel layout: `applyLayoutCollapses()` called `meshGeometry()` while `cfg` was null. The exception occurred before the startup request, so agents, projects and session controls stayed empty. Reproduced against the actual engine at port 8770.

## Repairs

- Guard graph geometry until configuration exists, load configuration through a recoverable Retry state, and show K.R.Y.Z.E.N from the initial HTML.
- Replace conflicting final desktop overrides with explicit desktop, tiled-window and phone layouts. Phones show the active workspace before the conversation. Preserve panel collapse settings and keyboard-accessible expand buttons.
- Fit agent nodes to actual SVG height and keep the navigation band separate. Fit large Flow canvases below their old 15% zoom floor; simplify card decoration at overview scale.
- Keep inactive Agy logs hidden; prevent saved collapsed side panels from appearing in Flow, Plan, Code or Control. Wrap side tabs so panel controls stay accessible.
- Ignore stale project-session responses after a newer conversation request. The existing project-creation regression reproduced intake losing its new session before this guard; all eight capability scenarios pass afterwards.

## Verification

- Python backend regression suite: **55 tests passed**.
- JavaScript syntax checks: inline client, Studio and layout regression passed.
- Browser layout matrix: **360×780, 390×844, 600×800, 768×900, 1000×700, 1100×800, 1280×577, 1440×900**. All five workspaces remain visible, inactive workspaces stay hidden, expanded/collapsed states fit horizontally, and desktop workspaces remain inside the window. Mesh circles stay within the SVG and Flow Fit contains every card.
- Saved collapsed panels survive a fresh page load without blocking startup.
- Simulated `/api/config` HTTP 503 shows a useful error; Retry restores all **11 agents**.
- GTK4/WebKit 6 native smoke test: **7 scenarios passed**, no uncaught page errors, actual tiled viewport **923×1048**. This uses the same native engine as the package, not browser emulation.
- Capability browser regression: **8 scenarios passed**, including project creation, dirty-buffer cancellation, intake, continuation and specialist availability.
- Additional browser regressions: **9** chat/plan/code reliability, **8** mesh/Flow interactions, **3** phone controls, **11** editor/image scenarios, all passed. Combined with capability checks: **39 browser scenarios**.
- The reliability check requires a fresh fixture with exactly two seeded projects; running it after project-creation tests fails its setup precondition. Rerun on a fresh fixture passed all nine checks.
- Built `packaging/dist/kryzen-1.1.0-6-any.pkg.tar.zst`; extracted UI assets match source bytes. Applied the same three assets to `~/.local/share/kryzen/app/agent/jarvis/`, preserving previous versions in `~/.local/share/kryzen/ui-backup-20261024-visibility/`. The live engine at 8770 loads **11 rendered agents and 2 projects** without page errors; no engine restart was needed. Existing windows need F5 to load the repaired assets.
- `/usr/lib/kryzen` remains managed by the existing installed 1.1.0-5 package. The new 1.1.0-6 archive is ready for a normal package upgrade; its UI fixes are already present in the current user runtime.

Reproduce with a disposable fixture (`python3 agent/jarvis/tests/browser_fixture.py --port 8774`), then run `tests/browser_layout.js` through agent-browser at the required viewport. Native verification: `python3 agent/jarvis/tests/native_ui_smoke.py http://127.0.0.1:8774`.

Screenshots: `screenshots/visibility-mesh-390.png`, `screenshots/visibility-flow-390.png`, `screenshots/visibility-mesh-1440.png`. Screenshots use disposable data. No paid model calls were used.
