# Reference redesign and panel resizing — 2026-10-24

## Design

Adapted the supplied visual reference into the existing AI studio: charcoal glass surfaces, bright inset borders, 24px corners, separate pill navigation/branding, blue actions, compact SVG icons, and real agent/tool/skill counts. Mesh, Flow, Plan, Code and Control retain their existing behavior. Design tokens and adaptation notes are in `docs/design/REFERENCE.md`.

The independent same-provider design evaluation passed. It identified active navigation hover contrast and an oversized right-panel header; both were corrected. Cross-provider evaluation was unavailable. Existing compact metadata stays secondary to the workspace's primary content.

## Resize behavior

- Drag the divider beside chat or logs/files. Panel sizes persist per desktop, tablet and phone layout.
- Focus a divider with Tab; arrow keys resize 10px, Shift+arrow 40px, Home/End use the bounds. Double-click resets the dimension. Escape cancels a pointer drag.
- Desktop panels resize horizontally while retaining at least 320px for the central workspace. In tiled windows, the logs/files handle resizes the lower rail height. Stacked phone panels resize vertically.
- Collapsed and inactive panels hide their dividers. Window resizing clamps the effective dimensions without discarding the saved preference.

## Validation

- **55 backend tests passed**, including HTTP/runtime fixtures.
- **39 existing browser scenarios passed**: reliability9, editor11, mesh8, phone3, capabilities8.
- Layout and resize suites passed at **360×780, 390×844, 600×800, 768×900, 1000×700, 1280×577, 1440×1000**. Both collapse states, all five modes, overflow, fit, hidden dividers, keyboard resizing, limits, persisted preferences and reset were checked.
- Actual browser pointer drag changed chat to320px and logs/files to300px; both survived a page reload.
- Native GTK4/WebKit smoke test: **7 checks passed**, no page errors at actual tiled viewport923×1048.
- Client JavaScript syntax checks passed.

Reproduce using `tests/browser_fixture.py --port 8774`, `tests/browser_layout.js`, `tests/browser_panel_resize.js`, `tests/browser_resize_pointer.py <agent-browser-session>` and `tests/native_ui_smoke.py http://127.0.0.1:8774`. These checks use disposable projects and a fake engine; no paid model calls are required.

## Delivery

Arch package: `packaging/dist/kryzen-1.1.0-7-any.pkg.tar.zst`. New CSS/JS are explicit server assets in the release.

The user's live engine had an active run, so the runtime HTML embeds the theme and resize assets directly. Existing server routes can serve this self-contained update without restarting the engine or disturbing the active run. Source server/assets are also copied for the next normal service start. Previous runtime UI files are retained in `~/.local/share/kryzen/ui-backup-20261024-reference/`. Reload with F5 after preserving any unsaved editor content.
