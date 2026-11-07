"""Shared concise-response policy for compiled workflows and the Jarvis runtime."""

OUTPUT_TOKENS = 8192
RECOVERY_OUTPUT_TOKENS = 16384
RESPONSE_STYLE = """COMPACT RESPONSES:
Keep user-facing replies to 2-4 short sentences or at most 3 bullets, usually under 80 words, unless the user requests detail. State the result, verification and next action. Avoid repeated summaries and long progress narration.
Specialist handoffs use STATUS, DONE, NEXT and BLOCKERS: four short lines, usually under 120 words total, with relevant artifact paths and concrete evidence. Put full plans, reports, research and code in project files; do not paste entire files into chat or duplicate them in handoffs.
Keep reasoning and delegation focused. Prefer a small complete tool call over a huge batch. Concision must not omit necessary work, required tool arguments, blockers or verification. File contents may be as long as the task requires; split large file writes into complete supported operations when needed.
"""


def model_options(model, recovery=False):
    """Only send reasoning controls verified for the selected model family."""
    options = {"max_tokens": RECOVERY_OUTPUT_TOKENS if recovery else OUTPUT_TOKENS}
    if str(model).startswith("nvidia/nemotron-3.5-super-vl"):
        if recovery:
            options["chat_template_kwargs"] = {"enable_thinking": False}
        else:
            options["reasoning_effort"] = "low"
    return options
