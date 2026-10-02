"""Web server + agent harness, based on the gemini-web-tool-calling starter.

Changes from the starter:
- tools come from app/tools.py, which merges all three pipelines,
- run_agent() passes session_id through so tools can read/write the
  session's SideQuest (the model never sees or chooses it),
- malformed tool arguments are reported to the model instead of crashing,
- /clear also forgets the session's SideQuest.

Run from the repo root:  uv run python -m app.main
"""

import json
import uuid
from pathlib import Path

import litellm
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.tools import TOOLS, clear_session, run_tool
from api.events import router as events_router

# --- Config ---

SYSTEM_PROMPT = (
    "You are Day as Someone, an agent that turns the user's free time in a city into a "
    "SideQuest: a short, themed real-world itinerary told as chapters, experienced 'as "
    "someone' (a persona like a 1950s novelist or a 90s indie filmmaker).\n"
    "For a brand-new SideQuest, first call match_theme to find a diverse, explainable "
    "shortlist of real places in one supported NYC neighborhood. If the user has not "
    "chosen a neighborhood, ask them to choose Morningside Heights, Greenwich Village, "
    "Chinatown, or DUMBO. Do not invent places. Twenty ready-made personas are available: "
    "struggling novelist, urban detective, indie filmmaker, architecture apprentice, "
    "city naturalist, independent magazine editor, jazz age drifter, street photographer, "
    "hidden history archivist, thrift fashion scout, neighborhood food chronicler, and "
    "waterfront poet, campus intellectual, avant garde theater actor, urban sketch artist, "
    "community radio producer, romantic city wanderer, industrial design student, museum "
    "time traveler, and midnight mystery writer. For any other persona, infer 3-6 "
    "desired_tags, optional avoid_tags, and a short story_tone from the match_theme schema; "
    "never invent tags outside its enum.\n"
    "Once a SideQuest exists, keep it alive across the conversation:\n"
    "- When something changes (a venue is closed, an event is cancelled, it rains, the "
    "budget or time changes, the user doesn't want to walk that far, or wants to skip a "
    "stop), call repair_sidequest. Do not re-plan the whole trip. Keep the same persona "
    "and theme.\n"
    "- If the user mentions the weather or asks whether it'll rain, call get_weather first.\n"
    "- To answer questions about the current plan, call get_current_sidequest.\n"
    "- If a tool returns ok=false, follow its `fix` field: retry with corrected arguments "
    "or ask the user the question it suggests.\n"
    "After a repair, tell the user briefly which chapters changed and why, in the "
    "persona's voice."
)
MAX_TOOL_ROUNDS = 5

# --- The Harness ---


def run_agent(messages: list[dict], session_id: str) -> tuple[str, list[dict]]:
    """Complete until the model answers without asking for a tool.

    Returns the final text and a record of every tool call made along the way.
    """
    tool_calls = []

    for _ in range(MAX_TOOL_ROUNDS):
        reply = litellm.completion(
            model="vertex_ai/gemini-3.5-flash-lite",
            vertex_location="global",
            messages=messages,
            tools=TOOLS,
        ).choices[0].message

        # Append assistant's reply (text, tool calls, or both) to the context.
        # model_dump() keeps it a plain dict: the raw object carries provider-specific
        # fields that trip Pydantic when LiteLLM re-serializes it next round.
        messages += [reply.model_dump()]

        if not reply.tool_calls:
            return reply.content, tool_calls

        # The harness, not the model, runs each tool and appends the result
        for call in reply.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as e:
                args = {}
                result = json.dumps({"ok": False, "error": f"Arguments were not valid JSON: {e}",
                                     "fix": "Call the tool again with a valid JSON object."})
            else:
                result = run_tool(call.function.name, args, session_id)
            tool_calls += [{"name": call.function.name, "args": args, "result": result}]

            messages += [{"role": "tool", "tool_call_id": call.id, "content": result}]

    return "Sorry, I hit my tool-call limit before finishing.", tool_calls


# --- Session Store ---

# session_id -> list of messages. In-memory, single process.
# Each pipeline keeps its own per-session state (e.g. the current SideQuest),
# keyed by the same session_id.
sessions: dict[str, list] = {}

# --- FastAPI App ---

app = FastAPI()
app.include_router(events_router)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list[dict]


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    # Get or create the session
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Append user's message to the context
    sessions[session_id] += [{"role": "user", "content": request.message}]

    try:
        response, tool_calls = run_agent(sessions[session_id], session_id)
    except Exception as e:
        # Auth, billing, a model that is not running: show it in the chat, not as a 500.
        response, tool_calls = f"Model call failed: {type(e).__name__}: {str(e)[:300]}", []

    return ChatResponse(response=response, session_id=session_id, tool_calls=tool_calls)


@app.post("/clear")
def clear(session_id: str | None = None):
    sessions.pop(session_id, None)
    if session_id:
        clear_session(session_id)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
