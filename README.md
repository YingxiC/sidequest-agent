# Day as Someone

Repository: `sidequest-agent`

Day as Someone is an agentic experience that turns a user's available time, location, constraints, and chosen persona or theme into a real-world SideQuest.

> Current stage: project architecture and repository skeleton.
> Original tool implementations are intentionally deferred.

## Product Concept

A user asks for a temporary way to experience their city "as someone" — a persona, archetype, fictional lens, mood, or theme.

Example:

"I have 3 hours in NYC. Give me a day as a 90s indie filmmaker."

High-level flow:

User Request
→ Interpret theme + constraints
→ Find viable real-world places
→ Build a connected SideQuest
→ Present itinerary + narrative + micro-tasks
→ Adapt when conditions change

## Core Feature Ownership

| Area | Responsibility | Planned Original Tool |
|---|---|---|
| Reality / Places | Place discovery, filtering, theme-to-place matching, feasibility | `match_theme` |
| Story / Experience | SideQuest structure, narrative, ordering, micro-tasks | `build_sidequest` |
| Adaptation / Memory | Session state, constraint changes, rerouting and repair | `repair_sidequest` |

The tool names above are placeholders only. Their implementations will be added later.

## Running Locally

Built on the course's `gemini-web-tool-calling` starter (FastAPI + LiteLLM + Gemini on Vertex AI).

1. A GCP project with billing and the Vertex AI / Agent Platform API enabled
2. `gcloud auth application-default login`
3. From the repo root: `uv run python -m app.main`, then open http://localhost:8000

Tests: `uv run pytest`

To add a pipeline's tools, give it a `tools.py` with `TOOLS`, `TOOL_FUNCTIONS` and
`run_tool(name, args, session_id)` (see `agents/adaptation/tools.py`) and register it in
`app/tools.py`.

## Repository Structure

sidequest-agent/
├── README.md
├── app/
├── agents/
│   ├── reality/
│   ├── story/
│   └── adaptation/
├── integrations/
├── state/
├── data/
├── tests/
└── docs/

## Architecture

The three feature pipelines should remain independently testable and communicate through shared structured data.

User Input
→ App / Orchestrator
→ Reality / Places
→ Story / Experience
→ Shared SideQuest State
→ Adaptation when needed
→ User Experience

## Shared Data

Before implementing tools, the team should agree on shared objects such as:

- UserRequest
- PlaceCandidate
- SideQuest
- QuestState
- RepairContext

Exact schemas are still TBD.

## Integration Layer

Provider-specific code should live under `integrations/`.

Possible integrations:

- Places / Maps API
- Weather
- Routing / Transit
- LLM provider
- Persistence / session storage

## Development Phases

### Phase 1 — Skeleton

- [x] Create repository
- [x] Define project concept
- [x] Define three feature pipelines
- [x] Create repository structure
- [ ] Define shared data contracts
- [ ] Define integration interfaces

### Phase 2 — Feature Pipelines

- [ ] Reality / Places
- [ ] Story / Experience
- [ ] Adaptation / Memory
- [ ] Unit tests

### Phase 3 — Integration

- [ ] Build orchestrator
- [ ] Connect shared state
- [ ] Test end-to-end SideQuest creation
- [ ] Test SideQuest repair

### Phase 4 — Demo

- [ ] Add user-facing interface
- [ ] Add demo scenarios
- [ ] Add fallbacks
- [ ] Prepare final demo
