# Mesh and Flow design verification

2026-10-24

## Result

The user's latest feedback restores circular agent cores, glowing halos, orbiting tool satellites and a distinct central Orchestrator. The desktop/tablet layout is elliptical; phones use a readable explorable orbit with a visible panning hint. Connections and attached capabilities follow dragged nodes. Layouts persist locally under `jarvis.mesh.orbit.v3`, separately for desktop and mobile, without altering Obsidian routing. Earlier rectangular layouts remain stored separately and are not applied.

Grouped controls provide layers, motion, layout reset, pan, zoom and fit. Motion respects Appearance settings, OS reduced motion and document visibility. Actual working state remains distinct from ambient movement. Navigation has its own band so controls do not cover the orbit. Reset determines the visible viewport mode before clearing saved layout, including an immediate click after opening a previously hidden mesh.

Flow composition, routing, selection and navigation controls have clearer hierarchy. Center selected and Deselect work for cards/connections. Routing and generated/read-only states stay visible on phones, with editing restrictions preserved. Mobile/coarse-pointer targets are at least 44px; lower-priority detail hides at overview zoom.

## Verification

- Existing **49** backend/session/API tests passed as the baseline; this iteration changes only the client and documentation.
- Existing **17** browser regression scenarios passed with the updated client: editor/plan/chat/pause behavior, project creation, continuation and specialist controls.
- **8** mesh/flow browser scenarios passed after final refinements: dynamic team display, keyboard movement and following paths, zoom/fit/layer/motion controls, appearance animation preference, actual activity hooks, reset, Flow centering/deselection, native geometry save and routing preservation.
- **3** phone browser scenarios passed: usable targets/no overflow, visible routing states and selection controls, generated read-only state and disabled editing. Independent evaluation measured targets at least **44×44px** at 375px; root checked 390px.
- Native pointer drag moved Marketing from `[600,80]` to approximately `[639.53,109.64]`, updated connections, kept the editor closed and persisted rounded `[640,110]` after reload. The desktop layout restored when the mesh was shown.
- OS reduced-motion emulation: motion button disabled/false, CSS animation `none`, SVG animations paused. Appearance motion-off is also covered by the browser checks.
- At 1440×900, Fit places the lowest card at about y=742 while navigation begins at y=785, leaving clearance. Screenshots reviewed at 390, 768 and 1440px; no document horizontal overflow. Browser console and page-error reports are empty.
- Client inline JavaScript, `studio.js` and browser-check scripts pass syntax checks.
- Independent design evaluation: **PASS**, followed by refinements and a second **PASS**. The second review confirmed all eight interaction and three responsive scenarios, visible badges, touch targets and navigation clearance. Only the available model provider was used; no cross-provider review is claimed.

## Evidence and limits

Current circular screenshots: `screenshots/circular-mesh-1440.png`, `circular-mesh-390.png`. Earlier control-design evidence: `mesh-design-1440.png`, `mesh-design-768.png`, `mesh-design-390.png`, `flow-controls-1440.png`, `flow-controls-390.png`.

Reproducible checks: `tests/browser_mesh.js`, `tests/browser_mesh_responsive.js`, existing `browser_checks.js` and `browser_capabilities.js`, all against `tests/browser_fixture.py`. The phone check expects a 390px viewport. Tests mutate only disposable projects/canvases and use a fake engine; no paid model calls or user project changes were required. Real touch hardware and coarse-pointer runtime were not tested; coarse-pointer CSS was inspected. Flow cards remain a pan/zoom workspace rather than fitting every card at readable size on one phone screen.

Source backup and design brief: `/tmp/jarvis-mesh-design-t02wfmfk`. Implementation: `index.html`, `studio.js`, `studio.css`. Behavior/design notes: `docs/design/MESH.md`.

## Circular iteration

Brief and source backup: `/tmp/jarvis-circular-mesh-o9wbvt3n`. Independent evaluation **PASS**: 11 actual circular bodies, glowing/rotating orbital decoration, preserved movement/persistence, navigation clearance and phone targets. The eight mesh interaction scenarios, original seventeen browser regressions and three responsive scenarios pass on the circular client. An immediate-after-reload Reset regression was reproduced and fixed; the strict first-click reset assertion now passes on a fresh page. Optional counts hide at low overview scales to keep names clear.

Final circular native-drag check persisted Marketing at rounded `[473,648]` and restored it after reload with the editor closed. At phone Fit (about 52%), optional metadata is hidden while node names remain visible; document width remains390px. Live Jarvis serves the circular assets and reports healthy; final JavaScript syntax checks pass.
