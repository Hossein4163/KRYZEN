# System reliability audit — 2026-10-24

Scope: existing Jarvis UI/runtime, PC bridge, shared plans, settings, coding utilities and local service integration. Preserve the shared Obsidian sources and user project contents. All mutation tests use disposable fixtures.

Acceptance criteria:
1. Events keep stable cursors through retention, reconnect and restart; unfinished runs persist and are clearly recoverable.
2. Chat/run controls stay attached to the selected session and project; duplicate submits and stale UI requests cannot corrupt another view.
3. Model failures, incomplete streams, invalid tool arguments and failed bridge commands are reported accurately with bounded retries.
4. File/plan edits reject stale revisions and new-file creation cannot truncate existing files.
5. Bridge project operations stay inside validated project paths; resume counts table and checkbox tasks consistently and tolerates truncated journals.
6. Failed settings changes restore the exact prior skill/tool/agent configuration.
7. Services report actual health and command failures. Existing navigation, editor, canvas and plans remain usable at phone/tablet/desktop sizes.
8. Targeted regression tests, browser persistence tests and a bounded live read-only model/tool smoke test establish concrete evidence.

Validation: stdlib unit/integration suite; Python/JavaScript syntax; disposable browser fixture; localhost service health; one read-only live agent smoke. No assertion that arbitrary future input or third-party services are bug-free.
