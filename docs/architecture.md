# Day as Someone — Architecture

## Main Components

### App / Orchestrator

Coordinates the feature pipelines and passes structured state between them.

Location:

`app/`

### Reality / Places

Responsible for place discovery, real-world constraints, and feasibility.

Location:

`agents/reality/`

### Story / Experience

Responsible for transforming viable places into a coherent SideQuest experience.

Location:

`agents/story/`

### Adaptation / Memory

Responsible for session state and repairing an active SideQuest when conditions change.

Location:

`agents/adaptation/`

## Shared Contracts

Proposed flow:

UserRequest
→ PlaceCandidate[]
→ SideQuest
→ QuestState
→ Repaired SideQuest

Concrete schemas are still TBD.

## Integration Boundary

External services should be isolated under:

`integrations/`

The three feature pipelines should not directly depend on provider SDKs.

## Orchestration

Preferred structure:

app/orchestrator
├── Reality pipeline
├── Story pipeline
└── Adaptation pipeline

The three original tools do not need to call each other directly.

## Open Decisions

- Shared schemas
- State persistence
- Places provider
- Weather integration
- Routing strategy
- LLM boundary
- Frontend
- Error / fallback contract
