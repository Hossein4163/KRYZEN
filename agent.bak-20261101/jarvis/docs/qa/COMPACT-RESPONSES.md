# Compact replies and output-limit recovery

2026-10-24

The reported `finish_reason: length` error previously stopped the turn immediately. Jarvis supplied no explicit output budget. NVIDIA documents that the selected Nemotron 3.5 model enables reasoning by default and counts reasoning plus answer against the same budget, making this a plausible contributor to the observed failure. No claim is made that the original request's token usage was captured.

## Changes

- Shared `workflow/modelpolicy.py` instructs all eleven agents to use short user replies (normally under 80 words) and four-line specialist handoffs (normally under 120 words), while preserving necessary verification/blockers. Substantial plans, research, reports and code belong in project files. Requested detailed answers and full file contents remain supported.
- Every Jarvis request has an 8192-token output budget. Only the verified Nemotron 3.5 family receives `reasoning_effort: low`; arbitrary models do not receive unsupported reasoning fields. The visible-answer prompt limit is separate from the budget available for reasoning and tool arguments.
- A `length` response discards all partial content/tool calls. Jarvis clears the partial preview and retries **once**, using the same completed history with an instruction to return a small, complete answer/tool call. Recovery uses 16384 tokens and turns thinking off for the verified model family. Earlier completed operations are not repeated by the recovery request.
- A second length failure stops with an accurate bounded-retry error. Stop/pause remain cooperative; content-filter and authentication failures are not retried as output-limit recovery. Existing bounded transient-network retries remain.
- Both compiled workflows are regenerated. The eleven n8n model nodes receive their locally verified `maxTokens` option, and shared handoff settings are shortened. The automatic compact-retry implementation is in Jarvis; no equivalent n8n runtime recovery is claimed.

## Evidence

**54 automated tests pass.** New cases check explicit budgets and model-specific options, complete call execution exactly once after discarding truncated arguments, one-retry exhaustion without executing tools, content-filter behavior and cancellation before recovery. Existing stream/session/bridge/flow/project regressions remain passing.

One live NIM run with a local read-only echo tool completed in **2.1 seconds**, called that tool exactly once and returned only `OK`. It accepted the new request options. No project files, external systems or user data were touched by this check. Actual provider-induced output exhaustion was simulated deterministically in tests rather than deliberately consuming a full live token budget.

All eleven compiled agent prompts contain the compact policy; all eleven model nodes have an explicit 8192-token budget. Python syntax checks pass.

Sources: [NVIDIA model reasoning/output-budget guidance](https://docs.nvidia.com/nim/large-language-models/latest/get-started/advanced/get-started-nemotron-3.5-super-vl.html), [hosted model example](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b). The installed n8n `LmChatNvidia.node.js` was inspected to verify the `maxTokens` option; its current UI does not expose model-specific thinking controls, so those are configured only in Jarvis.

Backup: `/tmp/jarvis-compact-asgh0ryv`.

Deployment status: both workflow drafts were imported successfully and remain inactive. All four services report healthy. **Jarvis service reload is pending** because it has a paused turn; the user was asked whether to end that turn and reload or preserve the pause. The running process has not yet loaded the new request/recovery code. After approval (or once the run has safely ended), reload Jarvis and verify its health before marking deployment complete.
