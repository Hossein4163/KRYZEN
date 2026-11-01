# Full system reliability verification — 2026-10-24

The audit repaired concrete failures in Jarvis, its runtime, shared workflow generation, PC bridge, settings and code workspace. This report supersedes the initial Studio report's limitation that no live model/tool test had been run.

## Results

- **37 automated regression/integration tests passed**, exit 0: `python3 -m unittest discover -s agent/jarvis/tests -v`.
- **9 browser regression scenarios passed** against a disposable project/bridge/server fixture: `tests/browser_checks.js`. No JavaScript errors occurred during the run.
- Python compilation and JavaScript syntax checks passed for the changed sources.
- A live NVIDIA NIM streaming agent called the authenticated bridge's read-only project-list tool once and replied `READY 2` in 14.4 seconds. The test exposed only that read-only tool; no project implementation was delegated.
- Authenticated sandbox commands `pwd` and `true` returned exit 0 in the existing hello-counter project. No project source files were changed.
- Jarvis, PC Bridge, n8n and SearXNG health checks all passed. No active Jarvis sessions or background bridge jobs existed before service restarts.
- Both n8n workflows rebuilt and imported successfully. They retain their existing inactive/draft state; this audit did not publish new triggers or background automation.

## Repaired behavior

### Sessions and live runs

Event IDs now increase monotonically through retention and reload. SSE sends event IDs, honors Last-Event-ID and resynchronizes clients whose cursors fell behind retained history. A chat-start response provides the exact replay cursor, so instant replies cannot disappear before the browser connects. Duplicate streamed events are ignored.

Chats persist atomically at turn start, tool/run boundaries and periodically while streaming. Restarted interrupted runs become a clear recovery message exactly once, with the selected project retained. Session IDs and persisted identity are validated. Requests for missing sessions no longer silently create replacements.

Duplicate sends are blocked without inventing extra messages or clearing draft input. Switching projects starts a separate conversation instead of carrying unrelated history into another project. Late session requests cannot replace the selected conversation. Pause requested during engine initialization is retained; delayed HTTP responses cannot overwrite a newer paused state. Stop releases paused runs. Reloading a paused session was verified manually in the browser.

### Model and tool execution

Incomplete/truncated streams cannot execute partial tool calls or masquerade as successful empty responses. Permanent authentication/input failures do not retry; transient retries are bounded and cancelable and clear partial display before replay. Tool arguments are validated before execution. Bridge errors and nonzero exits show failure. Delegation depth is bounded. Step-limit messages no longer falsely claim a checkpoint was saved.

Assigned role skills now reach both compiled n8n prompts and the Jarvis runtime, without duplicating the same instruction in Jarvis.

### Files, plans, bridge and jobs

The bridge uses atomic replacement and revision checks. Code and plan saves reject stale content; New file cannot truncate an existing file. Saving preserves typing made while the request was pending. Explicit Reload provides a recovery path after a conflict. Dirty code blocks an unwanted project switch and page unload. Raw control-file saves also carry revisions and cannot accidentally write a previous root's file into a newly selected root.

The bridge and Studio share one table/checkbox task parser, including milestone headings and fenced-example exclusion. Resume tolerates truncated journal tails, validates project slugs/resolved paths and excludes unrelated jobs. Project lists omit internal/unregistered folders. Checkpoints and generated workflow artifacts are written atomically. Concurrent checkpoint/autoresume changes are serialized.

Timed-out commands terminate their process group. New background jobs persist metadata and saved output; finished output remains available after a bridge restart, and unfinished jobs are identified as interrupted. Bridge restart does not continue a killed command automatically. Web fetch refuses local-file and other non-HTTP schemes.

### Controls and configuration

A global tab-handler collision was repaired: Terminal, Run, Search, Git and Preview now display exactly their own dock pane. Invalid regex searches expose the real error. Package script names are shell-quoted. Failed Git commits are not retried under a fallback identity. Stale file/project/settings responses cannot overwrite another selection. Broken local terminal-history data and malformed appearance JSON no longer prevent startup.

Failed skill rename/delete operations restore the original directory and exact assignments, including repeated changes to the same agent note. Rebuild timeouts return a failure so callers can restore their backups. Configuration writes and runtime loading are serialized. Service actions report actual exit failures and Jarvis has a real health endpoint.

## Repeatable browser checks

Start `python3 agent/jarvis/tests/browser_fixture.py --port 8771`, open that URL with agent-browser, then run:

```sh
agent-browser --session jarvis-checks eval --stdin < agent/jarvis/tests/browser_checks.js
```

The script first requires a fixture-only marker endpoint, so it refuses the normal application. It verifies all five dock tabs; typing during save; external-edit conflicts; canceled project switches and explicit reload; invalid search errors; canonical plan approval/task updates; instant chat responses; delayed pause-response ordering; and skill searching. The fixture uses temporary copies, local fake model responses and disposable projects. No real model runs occur in this test suite.

Additional manual browser checks covered paused-session reload, recovery after removing the active canvas in Obsidian, mobile/tablet Code layout and live Services status. Document widths matched 390px and 768px viewports with no horizontal overflow. Desktop checks used 1440px. The earlier Flow/Plan visual checks remain applicable.

## Scope of the evidence

These checks establish the repaired paths and current service integration. They do not exhaust every possible project, provider response or future network failure. Existing n8n publication settings were preserved. The original pre-audit source backup is `/tmp/jarvis-audit-uReTKler/backup/`; user session data, keys and project sources were not included in that backup. The workspace is not a Git repository, so no commit was created.
