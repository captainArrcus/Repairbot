# Techstack — RepairRöpi (v2)

> **Governing principle:** Every technology choice must justify itself against the alternative of "plain Python function." If a framework doesn't save us meaningful complexity, we don't use it.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   RepairRöpiApp                         │
│              (Mobile Frontend — TBD)                    │
│         Camera · Mic · Touch · Streaming UI             │
└─────────────────────┬───────────────────────────────────┘
                      │  SSE / HTTP
                      │  (Standardized API Contract)
┌─────────────────────▼───────────────────────────────────┐
│                Repair_Logic_Agent                        │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  FastAPI     │  │  Agent Core  │  │  Knowledge     │ │
│  │  API Layer   │──│  (see §Agent)│──│  Layer         │ │
│  │  (SSE Stream)│  │  + Tools     │  │  (see §Docs)   │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
│                          │                              │
│  ┌─────────────┐  ┌──────▼──────┐  ┌────────────────┐  │
│  │  LiteLLM    │  │  Session    │  │  Media Store    │  │
│  │  (Model     │  │  Store      │  │  (S3-compat.)  │  │
│  │   Router)   │  │  (Postgres) │  │                 │  │
│  └─────────────┘  └─────────────┘  └────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Langfuse (Observability & Eval)                 │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Backend Stack

### Language & Runtime

| Component | Choice | Version | Rationale |
|---|---|---|---|
| Language | Python | 3.12+ | Team expertise, ML/AI ecosystem |
| Package Manager | uv | latest | Fast, deterministic, replaces pip+venv |
| Linting + Formatting | **ruff** | latest | PEP8 lint + `ruff format` (black-compatible). Single tool, no redundancy. |

### API Layer

| Component | Choice | Rationale |
|---|---|---|
| Framework | **FastAPI** | Async-native, SSE streaming, auto-generated OpenAPI docs |
| Streaming | **SSE (Server-Sent Events)** | HTTP/2 compatible, proxy-friendly, no bidirectional state needed |
| Serialization | **Pydantic v2** | Request/response validation, schema generation |
| HTTP Client | **httpx** | Async-native, replaces `requests` to avoid sync blocking in event loop |

### Agent Framework: smolagents — Acknowledged as a Bet

| Component | Choice | Version | Rationale |
|---|---|---|---|
| Agent Framework | **smolagents** | ≥1.24.0 | Code-as-action, native multimodal, native streaming |
| Agent Type | **CodeAgent** | — | Writes Python to call tools |
| Model Router | **LiteLLM** | pin major (e.g. ~1.77) | Model-agnostic switching. Pin major version — LiteLLM ships breaking changes. |
| Step Control | **StepRunner** (custom) | — | Already built. Wraps smolagents streaming. |

#### Why smolagents over a 200-line plain Python agent loop?

Honest answer:

**What smolagents gives us that's hard to replicate in 200 lines:**
- Native streaming with typed step events (ToolCall, ActionStep, FinalAnswerStep) — our SSE event types map directly to these
- Multimodal memory (images persist across steps via `task_images` and `observation_images`)
- Built-in sandboxed execution options (Docker, E2B, WebAssembly) — critical since CodeAgent executes LLM-generated Python

**What's genuinely risky:**
- Young library (<2 years), HuggingFace-governed — could stall or pivot
- We're already extending it with StepRunner, which suggests friction
- CodeAgent executing arbitrary Python in production requires explicit sandboxing

**Our mitigation:**
- **Sandbox decision (Phase 1): Docker Sandboxes for AI Agents.** We already use Docker Compose, and Docker now offers purpose-built Sandboxes for AI Agents (https://www.docker.com/products/docker-sandboxes/). This gives us robust isolation with resource limits without having to build a hardened container from scratch. `CodeAgent(executor_type="docker")` will be configured to target this.
- **Abstraction boundary:** The FastAPI layer never imports smolagents directly. A thin `AgentService` interface wraps it. If smolagents dies, we replace the internals without touching the API layer.
- **Escape hatch:** If we hit a wall, the replacement is `LiteLLM tool-calling + a Python loop` — not a framework migration. We keep this option open.

> [!WARNING]
> **Review trigger:** If we find ourselves monkey-patching smolagents internals or fighting its abstractions more than using them, we drop it. The governing principle applies ruthlessly here.

#### Agent Architecture: Monolithic Core + Tools

Single CodeAgent with tools — not a multi-agent society.

**Tools (Phase 1):**

| Tool | Purpose | Implementation |
|---|---|---|
| `VisionAnalysisTool` | Analyze photos: identify parts, read error codes, assess damage | Multimodal LLM call via LiteLLM |
| `KnowledgeRetrievalTool` | Search/retrieve from CNC knowledge base | Interface to Knowledge Layer (see below) |
| `ErrorCodeLookupTool` | Structured lookup of error codes by controller family | Direct DB/structured data lookup — NOT semantic search |
| `WebSearchTool` | Fallback: search web for error codes, symptoms, part numbers | Already built (unified_search.py) |

> [!IMPORTANT]
> The agent does **not** get a "generate repair steps" tool. The agent *itself* reasons about diagnosis and repair using its context. Tools provide information; the agent provides reasoning.

#### Structured Output Contract

The agent streams typed SSE events (`hypothesis`, `question`, `diagnosis`, etc.). This requires **structured output from the LLM at every step** — not free-form text parsing.

Implementation: smolagents' CodeAgent naturally produces structured step objects. We map these to our SSE event types in the `AgentService` layer. When the agent calls a tool or produces an action, the step type is already typed.

For the *content* of events (e.g., hypothesis with confidence score), the agent's system prompt enforces a JSON output schema per event type. We validate with Pydantic before streaming.

**Model compatibility:** Gemini 2.5 Flash, Claude Sonnet 4, and GPT-4o all support structured output, but differently. LiteLLM abstracts invocation, not output schema behavior. Our `AgentService` layer normalizes this — it's the one place where model-specific output parsing lives.

### LLM Strategy

| Scenario | Model | Rationale |
|---|---|---|
| Primary reasoning + vision | **Gemini 2.5 Flash** | Cost-effective, fast, strong multimodal |
| Complex/fallback diagnosis | **Claude Sonnet 4** or **GPT-4o** | Higher accuracy ceiling for edge cases |
| Local/privacy-sensitive | **Deferred to Phase 2** | Only if SME demands on-premise |

---

## Knowledge Layer (Document Processing)

> **Status: Phase 0 Spike required.** This is the single biggest determinant of diagnostic quality. We define the approach categories and the spike criteria — not a final architecture.

### The Problem

CNC machine documentation is a nightmare of entropy:
- Scanned PDFs from the 1990s (effectively images)
- German + English + Japanese manuals
- Schematics, exploded views, wiring diagrams
- Error code tables (highly structured) mixed with prose
- Proprietary PLC codes with no public documentation
- Knowledge that exists only in retired technicians' heads

### Approaches to Evaluate (Phase 0 Spike)

| Approach | Description | Strength | Weakness |
|---|---|---|---|
| **Classic RAG** | Parse → chunk → embed → vector search → inject context | Well-understood, scalable | Parsing errors on bad scans, loses spatial layout |
| **Karpathy LLM Wiki** | LLM "compiles" raw docs into structured, interlinked Markdown wiki. Query against the wiki, not raw docs. | Knowledge compounds, LLM-native format, handles messy sources | High upfront token cost to compile, needs maintenance pipeline |
| **Direct VLM Page Feed** | Skip parsing entirely. Feed PDF pages as images to a vision model. | Zero parsing errors, preserves layout perfectly | Token-expensive per query, no pre-indexing |
| **Hybrid** | Structured data (error codes, part numbers) in DB. Prose/schematics via wiki or VLM. | Best of all worlds | Most complex to build |
| **Graph RAG** | Knowledge graph over entities (machine → component → fault → solution) | Relationship-aware retrieval | High construction cost, premature for Phase 1 |

### Phase 0 Spike: Success Criteria

> [!IMPORTANT]
> Before locking the knowledge architecture, run a 1-week spike with real data:
> - **Corpus:** 20 real SINUMERIK error codes + relevant manual pages from a DMG MORI or Hermle machine
> - **Task:** Given an error code + symptom description, retrieve the correct manual page/section
> - **Metric:** Top-3 recall ≥85% across the 20 test cases
> - **Compare:** At minimum, classic RAG vs. direct VLM page feed vs. LLM wiki

### Interface Design

The cofounder correctly identified that a single `search(query, top_k)` interface is biased toward RAG. Different knowledge types need different access patterns:

```python
class KnowledgeLayer(Protocol):
    def search_semantic(self, query: str, top_k: int = 5) -> list[KnowledgeChunk]:
        """Fuzzy semantic search over prose, procedures, descriptions."""
        ...

    def lookup_error_code(self, code: str, controller_family: str) -> ErrorCodeEntry | None:
        """Exact structured lookup. Error codes are data, not prose."""
        ...

    def get_page_image(self, doc_id: str, page: int) -> bytes:
        """Raw page image for direct VLM consumption."""
        ...

    def get_compiled_article(self, topic: str) -> str | None:
        """Retrieve a compiled wiki article (if using LLM wiki approach)."""
        ...
```

### Karpathy LLM Wiki — Why We're Interested

The wiki pattern is particularly compelling for our domain because:
1. **Industrial manuals are messy but stable.** A machine manual doesn't change. You compile it once.
2. **Cross-referencing is critical.** Error AL 309 relates to X-axis drive, which connects to ball screw assembly, which has a specific bearing part number. A compiled wiki captures these links.
3. **Expert knowledge capture.** When we interview retired technicians, their oral knowledge can be "ingested" into the wiki as new articles — same pipeline as documents.
4. **LLM-native.** The agent reads Markdown naturally. No embedding model language bias.

We'll evaluate this alongside classic RAG and VLM in the Phase 0 spike.

---

## Language & Localization

### The Reality

- **User interface:** German-first. English as secondary.
- **Manuals:** Predominantly German + English. Some Japanese for imported machines (Fanuc, Mazak).
- **User base:** ~30% migration background in metalworking sector. Relevant languages: Turkish, Polish, Russian, Arabic.
- **Technical jargon:** Highly domain-specific. Standard STT/embedding models struggle.

### Phase 1 Strategy

| Concern | Approach | Notes |
|---|---|---|
| **UI language** | German + English | Full multilingual UI deferred to Phase 2 |
| **Agent conversation language** | German | System prompts in English (better LLM performance), user-facing output in German. Agent auto-detects user language. |
| **STT (Speech-to-Text)** | **Whisper large-v3** (local) | German Tier 1 language, <5% WER on clean audio. Factory noise adds 5–15% WER — acceptable with audio preprocessing. Run locally for privacy/latency. |
| **STT preprocessing** | Noise reduction before Whisper | Spectral subtraction / noise gate. Factory floors are loud. |
| **Embedding model** (if RAG) | **Multilingual model required** | e.g., `multilingual-e5-large` or Cohere multilingual. Most OSS embedders are Anglo-centric — this is a product-market fit risk. |
| **Prompt language** | English system prompt + German user content | LLMs reason better in English. Output language follows user input. |
| **Manual language detection** | Auto-detect per document | Tag at ingestion time. Route to appropriate processing. |

> [!NOTE]
> Full multilingual support (Turkish, Polish, Arabic UI) is Phase 2+. Phase 1 validates the core diagnostic loop in German. Visual-first guidance (photos, diagrams, annotated images) is inherently language-agnostic and reduces the multilingual burden.

---

## Observability & Evaluation

> [!IMPORTANT]
> Non-negotiable. The Mission mandates ≥40% diagnostic time reduction. You cannot hit a metric you cannot measure.

### LLM Observability

| Component | Choice | Rationale |
|---|---|---|
| **Trace platform** | **Langfuse** (self-hosted) | Open-source, self-hostable (German data sovereignty), traces LLM calls with latency/cost/token counts |
| **Integration** | Langfuse Python SDK + LiteLLM callback | Automatic tracing of every LLM call without code changes |
| **What we trace** | Every agent step: tool calls, LLM invocations, reasoning chains, hypotheses, final diagnosis | Full audit trail per diagnostic session |

### Evaluation Framework

| Component | Purpose | Implementation |
|---|---|---|
| **Golden test set** | Regression testing when swapping models or changing prompts | `pytest`-based harness with 20+ diagnostic scenarios (error code + symptoms → expected diagnosis) |
| **Automated eval** | Run golden set on every model/prompt change | CI job: `pytest tests/eval/` — fail if recall drops below threshold |
| **Trace quality validation** | Ensure Data Bridge traces are actually structured, not raw chat logs | Schema validation on every persisted trace — reject malformed traces |
| **A/B model comparison** | Compare Gemini vs. Claude on same scenarios | Langfuse experiment tracking |

### What a Golden Test Case Looks Like

```yaml
- id: sinumerik_al309_xaxis
  input:
    error_code: "AL 309"
    controller: "SINUMERIK 840D"
    symptom: "Rattling sound when jogging X-axis"
    image: "test_fixtures/spindle_wear_01.jpg"
  expected:
    diagnosis_contains: ["ball screw", "bearing", "X-axis"]
    relevant_manual_section: "Ch. 12.4 Drive Alarms"
    should_not_contain: ["Y-axis", "spindle motor"]
  eval_criteria:
    - top_3_hypothesis_contains_correct: true
    - asks_relevant_clarifying_question: true
```

---

## Data Storage & Session Traces

### Storage Components

| Component | Choice | Rationale |
|---|---|---|
| Session traces | **PostgreSQL** | Structured diagnostic traces (Data Bridge). JSONB for flexible evolution. |
| Media (images, audio) | **Cloud S3** (Hetzner Object Storage / Scaleway / AWS S3) | No self-hosted MinIO for Phase 1. Less to operate. |
| Configuration | **YAML + env vars** | Simple, version-controllable |
| DB access | **psycopg (direct SQL)** | Two tables don't justify SQLAlchemy. Plain SQL, no ORM. |

### Session Trace Schema — Designed Backward from Training Data

The Mission's Data Bridge is an architectural invariant. The schema must reconstruct a future fine-tuning dataset row:

```
Training Example = {
  machine_context,
  initial_observation (image + symptom),
  diagnostic_chain: [
    { evidence_presented, hypotheses_before, hypotheses_after, confidence_delta },
    ...
  ],
  final_diagnosis,
  repair_action_taken,
  outcome (success | escalation | failure),
  verification_evidence (image)
}
```

Therefore, the schema has **first-class tables for hypotheses and outcomes**, not opaque JSONB:

```sql
CREATE TABLE diagnostic_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_family TEXT NOT NULL,
    controller_family TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'active',  -- active | resolved | escalated | failed
    metadata JSONB                 -- user_skill_level, factory, etc.
);

CREATE TABLE diagnostic_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES diagnostic_sessions(id),
    turn_index INT NOT NULL,
    role TEXT NOT NULL,             -- 'user' | 'agent'
    content TEXT,
    media_refs TEXT[],             -- S3 keys
    tools_called JSONB,            -- [{tool, args, result_summary}]
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE hypotheses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES diagnostic_sessions(id),
    introduced_at_turn INT NOT NULL,
    description TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    eliminated_at_turn INT,        -- NULL if still active
    elimination_reason TEXT,
    is_final_diagnosis BOOLEAN DEFAULT false
);

CREATE TABLE hypothesis_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis_id UUID REFERENCES hypotheses(id),
    turn_id UUID REFERENCES diagnostic_turns(id),
    confidence_before FLOAT,
    confidence_after FLOAT,
    evidence_text TEXT,             -- what caused the update
    evidence_media_ref TEXT         -- S3 key if visual evidence
);

CREATE TABLE session_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES diagnostic_sessions(id) UNIQUE,
    outcome TEXT NOT NULL,          -- 'resolved' | 'escalated' | 'failed'
    final_diagnosis_id UUID REFERENCES hypotheses(id),
    repair_action TEXT,
    verification_media_ref TEXT,    -- photo confirming fix
    resolution_time_minutes INT,
    technician_confidence INT,     -- 1-5 self-reported
    created_at TIMESTAMPTZ DEFAULT now()
);
```

> [!NOTE]
> This schema lets us reconstruct full diagnostic chains for fine-tuning: `initial_state → [evidence, hypothesis_update]* → diagnosis → action → outcome`. Every hypothesis has a traceable lifecycle.

---

## API Contract

### SSE Operational Behavior

> [!IMPORTANT]
> Addresses the cofounder's critical concern: SSE must handle flaky factory WiFi gracefully.

**Media uploads:** Presigned upload URLs are the **only** media path. No base64 in request bodies.

```
1. Client requests presigned URL:  POST /api/v1/media/upload-url
   → Returns { "upload_url": "https://s3.../presigned", "media_key": "uuid" }
2. Client uploads directly to S3:   PUT {upload_url} with binary body
3. Client references media_key in turn payload
```

**Resumability:**
- Every SSE event includes a monotonic `id` field (Last-Event-ID support)
- On reconnect, client sends `Last-Event-ID` header → server replays missed events
- Replay endpoint: `GET /api/v1/sessions/{id}/turns/{turn_id}/events?after={event_id}`
- Turn submissions are idempotent via client-generated `idempotency_key`

### Endpoints

```
POST   /api/v1/sessions                         → Create diagnostic session
POST   /api/v1/media/upload-url                  → Get presigned S3 upload URL
POST   /api/v1/sessions/{id}/turns               → Send user turn (text + media_keys)
GET    /api/v1/sessions/{id}/stream              → SSE stream of current agent response
GET    /api/v1/sessions/{id}/turns/{tid}/events   → Replay events for a turn (resumability)
GET    /api/v1/sessions/{id}                     → Get session state + full history
```

### Request: User Turn

```json
{
  "idempotency_key": "client-generated-uuid",
  "text": "Es rattert beim Anfahren der X-Achse",
  "media_keys": ["uuid-of-uploaded-image", "uuid-of-uploaded-audio"],
  "machine_context": {
    "controller": "SINUMERIK_840D",
    "error_code": "AL 309"
  }
}
```

> [!NOTE]
> `machine_context` is **optional and progressive**. The technician doesn't need to know their controller type upfront. The agent identifies it through conversation — from photos of the control panel, error code format, or direct questions.

### SSE Event Types

| Event | Purpose | Frontend Action |
|---|---|---|
| `thinking` | Agent's intermediate reasoning | Display in collapsible "thinking" panel |
| `hypothesis` | Ranked fault hypothesis with confidence | Hypothesis panel with confidence bars |
| `tool_call` | Agent invoking a tool | Subtle "searching..." indicator |
| `tool_result` | Tool response summary | Optional: show retrieved doc snippet |
| `question` | Agent asks technician for evidence | **Primary action:** prominent prompt with input method (📷 photo, 🎤 voice, ✏️ text) |
| `guidance` | Repair step or instruction | Actionable step card |
| `diagnosis` | Final confirmed diagnosis | Prominent display with explanation |
| `escalation` | Agent cannot diagnose confidently | Escalation UI (call expert, contact OEM) |
| `done` | Turn complete | Enable user input for next turn |

### Full Resolved Session Example

```
-- Turn 1: User sends initial report
POST /sessions/{id}/turns
  { "text": "Maschine rattert bei X-Achse", "media_keys": ["img-001"] }

-- Agent streams response:
event: thinking
id: 1
data: {"content": "Analysiere Bild der Spindelzone..."}

event: hypothesis
id: 2
data: {"id": "h1", "description": "Kugelgewindetrieb-Lager verschlissen", "confidence": 0.55}

event: hypothesis
id: 3
data: {"id": "h2", "description": "Kupplung zwischen Motor und Kugelgewindetrieb lose", "confidence": 0.30}

event: question
id: 4
data: {"content": "Können Sie den Maschinentisch in X-Richtung per Hand schieben und mir sagen, ob Sie Spiel spüren?", "evidence_type": "tactile_observation"}

event: done
id: 5
data: {"status": "awaiting_user_input"}

-- Turn 2: User responds
POST /sessions/{id}/turns
  { "text": "Ja, da ist deutliches Spiel, ca. 0.5mm" }

-- Agent streams:
event: thinking
id: 6
data: {"content": "0.5mm Axialspiel bestätigt Lagerverschleiß..."}

event: hypothesis
id: 7
data: {"id": "h1", "description": "Kugelgewindetrieb-Lager verschlissen", "confidence": 0.90}

event: hypothesis
id: 8
data: {"id": "h2", "description": "Kupplung lose", "confidence": 0.05, "eliminated": true}

event: diagnosis
id: 9
data: {"hypothesis_id": "h1", "confidence": 0.90, "explanation": "Axialspiel + Rattergeräusch = klassisches Lagerschadensbild"}

event: guidance
id: 10
data: {"step": 1, "content": "Lager Bestellnummer: 6205-2RS. Wechsel gemäß Servicehandbuch Kap. 8.3."}

event: done
id: 11
data: {"status": "awaiting_verification"}
```

---

## Frontend Stack

> **Decision deferred.** The API contract is framework-agnostic. The frontend is a thin client.

### Requirements
- Camera (photo + video), Microphone (voice on noisy floors)
- SSE streaming consumption, Presigned S3 uploads
- Android-first (rugged devices: CAT, Samsung XCover, Ulefone)
- Visual-first UI (diagram-heavy, reduces multilingual burden)

### Options

| Framework | Pros | Cons |
|---|---|---|
| **React Native** | JS ecosystem, strong native modules, Expo for rapid prototyping | Requires JS/TS expertise |
| **Flutter** | AOT-compiled perf, pixel-perfect rendering across rugged device skins, excellent camera plugin | Dart ecosystem smaller |
| **PWA** | No app store | **Ruled out** — insufficient camera control on rugged hardware |

> [!IMPORTANT]
> **No recommendation until we know who builds it.** Both React Native and Flutter are viable. The choice follows the frontend developer's expertise. The API contract ensures the backend doesn't care.

---

## Code Style

Enforced by tooling, not convention:

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.ruff.format]
# ruff format replaces black — single tool, no redundancy
```

### Rules

1. **PEP8 via ruff (lint + format).** No exceptions. No black (redundant).
2. **No unnecessary comments.** Code is self-explanatory. Comments only for *why*, never *what*.
3. **No docstrings on self-explanatory functions.**
4. **Minimal initialization.** No factory patterns. Plain Python constructors.
5. **No defensive over-engineering.** No `try/except` everywhere. Exceptions propagate to the layer that handles them.
6. **No unnecessary abstraction.** Concrete first. Abstract after three instances.
7. **Type hints everywhere.** Pydantic for data models, plain hints for functions.
8. **No ORM for simple schemas.** `psycopg` + plain SQL. SQLAlchemy only if schema complexity demands it.

---

## Infrastructure (Phase 1)

| Component | Choice | Notes |
|---|---|---|
| Containerization | **Docker + Docker Compose** | Local dev and staging |
| CI/CD | **GitHub Actions** | Lint (ruff), eval suite, tests |
| Deployment | **Cloud-first** | Single VPS or managed containers. No k8s for Phase 1. |
| Object Storage | **Cloud S3** (Hetzner/Scaleway/AWS) | No self-hosted MinIO. Less to operate. |
| Secrets | **.env** (local), **CI secrets** (prod) | Document migration path for SME security audits. |
| Agent sandbox | **Docker executor** | CodeAgent runs in isolated container |
| Rate limiting | **Noted for Phase 2** | Not urgent, but noted. |

---

## Dependency Summary

### Repair_Logic_Agent (Python)

```
# Core
python >= 3.12
fastapi
uvicorn
pydantic >= 2.0
httpx                      # async HTTP client (NOT requests)

# Agent
smolagents >= 1.24.0
litellm ~= 1.77            # pin major version

# Document Processing
docling                    # baseline PDF parser (spike will evaluate alternatives)

# Speech
openai-whisper             # local STT

# Data
psycopg[binary]            # PostgreSQL — direct SQL, no ORM

# Observability
langfuse                   # LLM tracing

# Storage
boto3                      # S3-compatible object storage

# Utilities
python-dotenv
pyyaml
pillow

# Dev
ruff
pytest
```

---

## Pre-Lock Checklist

Before this document becomes binding:

- [ ] **Phase 0 Knowledge Spike** (1 week): RAG vs. VLM page feed vs. LLM wiki on 20 real SINUMERIK error codes
- [ ] **smolagents stress test**: Build the diagnostic conversation loop end-to-end. If we fight the framework, drop it.
- [ ] **Frontend developer identified**: Lock React Native vs. Flutter based on their expertise
- [ ] **Langfuse deployed**: Self-hosted instance running before first agent integration test

---

*Stand: Mai 2026 — v2 incorporating cofounder review*
