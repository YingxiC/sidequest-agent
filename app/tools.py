"""Every tool the harness can run: one registry over all three pipelines.

Each pipeline exposes a tools module with:
    TOOLS           OpenAI/LiteLLM-format declarations (what the model sees)
    TOOL_FUNCTIONS  tool name -> Python function
    run_tool(name, args, session_id) -> dict   never raises
    clear_session(session_id)                  optional

To add your pipeline, import its tools module and append it to PIPELINES.
"""

import json

from agents.adaptation import tools as adaptation_tools

# TODO: add agents.reality.tools (match_theme) and agents.story.tools (build_sidequest).
PIPELINES = [adaptation_tools]

TOOLS = [decl for module in PIPELINES for decl in module.TOOLS]

_OWNER = {name: module for module in PIPELINES for name in module.TOOL_FUNCTIONS}
assert len(_OWNER) == sum(len(m.TOOL_FUNCTIONS) for m in PIPELINES), "duplicate tool name"


def run_tool(name: str, args: dict, session_id: str) -> str:
    """Run one tool call and return its result as a JSON string for the model.

    Models invent tool names and arguments; never let that crash the loop.
    """
    module = _OWNER.get(name)
    if module is None:
        result = {"ok": False, "error": f"Unknown tool '{name}'.",
                  "fix": f"Use one of: {', '.join(_OWNER)}."}
    else:
        try:
            result = module.run_tool(name, args, session_id)
        except Exception as e:
            result = {"ok": False, "error": f"{name} crashed: {type(e).__name__}: {e}",
                      "fix": "Tell the user this step failed and offer to try again."}
    return json.dumps(result, ensure_ascii=False, default=str)


def clear_session(session_id: str) -> None:
    for module in PIPELINES:
        clear = getattr(module, "clear_session", None)
        if clear:
            clear(session_id)
