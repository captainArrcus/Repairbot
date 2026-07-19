# Techstack — RepairRöpi (v3)

> **Governing principle:** Every technology choice must justify itself against the alternative of "plain Python function." If a framework doesn't save us meaningful complexity, we don't use it.

> **v3 change:** The agent backbone moves from smolagents to an **embedded hermes-agent** ([NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent), MIT). Decision drivers: built-in learning loop (skills, memory, curator) that turns field sessions into cloud assets, ready-made trajectory generation/compression tooling for the Data Bridge, and a tool-calling loop (not code-as-action) that eliminates the arbitrary-code-execution sandbox problem. Deployment is **central cloud, multi-tenant**; the mobile app stays the only channel in Phase 1.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   RepairRöpiApp                         │
│         (Mobile Frontend — React Native + Expo)         │
│         Camera · Mic · Touch · Streaming UI             │
└─────────────────────┬───────────────────────────────────┘
                      │  SSE / HTTP
                      │  (Standardized API Contract)
┌─────────────────────▼───────────────────────────────────┐
│                Repair_Logic_Agent                        │
│                                                         │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────┐ │
│  │  FastAPI     │  │  AgentService    │  │  Knowledge │ │
│  │  API Layer   │──│  wraps embedded  │──│  Layer     │ │
│  │  (SSE Stream)│  │  hermes AIAgent  │  │  (hybrid)  │ │
│  └─────────────┘  └────────┬─────────┘  └────────────┘ │
│                            │ 4 domain tools, allowlisted│
│  ┌─────────────┐  ┌────────▼────────┐  ┌────────────┐  │
│  │  LiteLLM    │  │  Session Store  │  │ Media Store│  │
│  │  Proxy      │  │  (Postgres)     │  │ (S3-comp.) │  │
│  └─────────────┘  └─────────────────┘  └────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Learning Pipeline (per-tenant hermes state:     │   │
│  │  trajectories · skills · memory → curation →     │   │
│  │  fleet knowledge)                                │   │
│  └──────────────────────────────────────────────────┘   │
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

### Agent Framework: hermes-agent (embedded) — Acknowledged as a Bet

| Component | Choice | Version | Rationale |
|---|---|---|---|
| Agent Backbone | **hermes-agent** (NousResearch) | **pinned git commit** — no stable API guarantee upstream | Learning loop + trajectory tooling + tool-calling loop |
| Entry Point | **`run_agent.AIAgent`** (embedded as library) | — | Programmatic conversation loop; no CLI/gateway needed |
| Process Model | **Worker process per session** (`agents/hermes_worker.py` in `.venv-hermes`; JSONL over stdio) | — | Hermes exact-pins its deps and `HERMES_HOME` is process-global → the agent cannot live in the app venv/process (spec 2.5 D1). Domain tools execute **parent-side via stdio RPC** (spec 2.5 D2): no DB/S3 credentials in the agent process; its only egress need is the LLM endpoint. |
| Model Access | Direct OpenAI-compatible `base_url` now (`REPAIR_LLM_*` env); **LiteLLM proxy at deploy (3.1)** — pin major (e.g. ~1.77) | swap is an env change (user-ratified, spec 2.5 D11) | `AIAgent` speaks the OpenAI protocol to any `base_url`; LiteLLM proxy does provider routing behind it in prod |
| Event Mapping | **`AgentService`** (ours: `agent_service.py` + `hermes_backend.py`) | — | Maps the worker stream to our typed SSE events; validation authority is the parent (spec 2.5 D4) |

#### Why hermes-agent over smolagents / a plain loop?

Honest answer:

**What hermes gives us that we'd otherwise build ourselves:**
- **A learning loop** — the strategic reason. Skills are created autonomously after complex tasks and self-improve during use; the memory manager and curator build durable knowledge across sessions. What a technician on the ground teaches the agent becomes a cloud asset (see §Learning Pipeline).
- **Trajectory generation and compression** (`batch_runner.py`, `trajectory_compressor.py`, datagen configs) — purpose-built tooling to turn tool-calling traces into training data. The Data Bridge gets a concrete fine-tuning pipeline instead of a bespoke export format.
- **Tool-calling loop, not code-as-action.** The LLM never writes arbitrary Python. The entire CodeAgent-sandbox problem from v2 disappears; containment reduces to a tool allowlist plus network egress isolation (see §Guardrails).
- Streaming, iteration budgets, context compression, multimodal message handling — built in and battle-tested across their CLI/gateway deployments.

**What we deliberately do NOT use (Phase 1):**

| Unused | Why |
|---|---|
| CLI / TUI | Our channel is the mobile app via FastAPI |
| Gateway + messaging channels (Telegram, WhatsApp, …) | Deferred to Phase 3+ (validated option — relay-connector contract exists) |
| Terminal execution tools (all 6 backends) | The repair agent has no business running shell commands |
| The 40+ general-purpose tools, MCP extras, cron, subagents | Tool allowlist is our 4 domain tools + hermes' 4 learning-loop tools (see §Guardrails 1) |

**What's genuinely risky:**
- **Single-user design.** Hermes state (memory, skills, sessions) lives file-based under `HERMES_HOME` — built for one user per instance. Multi-tenant operation requires strict per-tenant isolation (see §Guardrails). Cross-tenant knowledge leakage is our #1 integration risk.
- **Fast-moving repo, no semver.** We pin a commit and upgrade deliberately behind the golden test harness.
- **Feature entanglement.** Some learning features may assume the CLI/gateway session store. The embed spike (Roadmap Feature 0.2) must verify skills/memory work when driven purely through `AIAgent`.

**Our mitigation:**
- **Abstraction boundary:** The FastAPI layer never imports hermes directly. A thin `AgentService` interface wraps it. If hermes dies or pivots, we replace the internals without touching the API layer.
- **Escape hatch:** unchanged from v2 — `LiteLLM tool-calling + a Python loop`. Embedding `AIAgent` as a library (not adopting the whole platform) keeps this exit cheap.

> [!WARNING]
> **Review trigger:** If we find ourselves monkey-patching hermes internals, fighting the single-user assumptions, or the learning loop doesn't function without the gateway — we drop to the escape hatch. The governing principle applies ruthlessly here.

#### Guardrails — hermes runs inside a fence

Hermes is a general-purpose agent framework with wide capabilities. We embed it with defense in depth:

1. **Tool allowlist.** The agent is constructed with exactly the four domain tools below **plus hermes' four learning-loop tools** (`memory`, `skills_list`, `skill_view`, `skill_manage`) — the learning loop only functions through its own tools (Feature 0.2 finding, ratified 2026-07-12; they are file-based and tenant-scoped). Terminal execution, browser, image generation, MCP servers, subagent spawning — never registered. No code-execution path exists. The exact exposed-tool set is asserted at every session start: worker-side assert + `ready` handshake checked against `hermes_backend.ALLOWED_TOOLS` (one place); mismatch fails the session safe (verified — it caught a real name-gating surprise, spec 2.5 FINDINGS #1). **Never reuse a hermes built-in tool name for a domain tool** (hermes name-gates e.g. `web_search` on its own config — ours is `repair_web_search`).
2. **Network egress isolation.** We adopt the dual-network Docker pattern from hermes' own `docs/security/network-egress-isolation.md` (`infra/docker-compose.agent.yml`, `AGENT_RUNNER=docker`): the worker container has no default route; a squid proxy allows an explicit host allowlist. Because domain tools run parent-side (RPC), the agent's allowlist is **LLM endpoint domains + models.dev only** — S3/Langfuse egress belongs to the API process, not the agent. Prompt-injection exfiltration has nowhere to go. Verified by `tests/agent/test_egress_isolation.py` + a live turn through the isolated container.
3. **Tenant isolation.** One `HERMES_HOME` per tenant — memory, skills, and session state never share a directory across customers. Postgres remains the source of truth; hermes file/SQLite state is a rebuildable cache tier. A cross-tenant leak test is part of the golden harness.
4. **Physical-safety approval.** `guidance` events carry `safety_level`. High-safety steps (electrical work, lockout/tagout) require explicit technician confirmation in the app before follow-up steps stream — hermes' command-approval concept mapped to physical actions.
5. **Output validation.** Every event is Pydantic-validated before streaming (unchanged from v2). Invalid agent output is sanitized and logged to Langfuse, never forwarded raw.

#### Agent Architecture: Monolithic Core + Tools

Single embedded `AIAgent` with tools — not a multi-agent society. Hermes supports subagent spawning; we don't use it.

**Tools (Phase 1):**

| Tool | Purpose | Implementation |
|---|---|---|
| `VisionAnalysisTool` | Analyze photos: identify parts, read error codes, assess damage | pytesseract OCR + brand heuristic; LiteLLM multimodal fallback when OCR sees no brand (Feature 2.3) |
| `KnowledgeRetrievalTool` | Search/retrieve from CNC knowledge base | Interface to Knowledge Layer (see below) |
| `ErrorCodeLookupTool` | Structured lookup of error codes by controller family | Direct DB/structured data lookup — NOT semantic search |
| `WebSearchTool` | Fallback: search web for error codes, symptoms, part numbers | Thin `ddgs` wrapper `app/tools/web_search.py`, registered as `repair_web_search` (spec 2.5 D9 — unified_search.py's engine zoo not adopted; Tavily is the upgrade path) |

> [!IMPORTANT]
> The agent does **not** get a "generate repair steps" tool. The agent *itself* reasons about diagnosis and repair using its context. Tools provide information; the agent provides reasoning.

#### Structured Output Contract

The agent streams typed SSE events (`hypothesis`, `question`, `diagnosis`, etc.). This requires **structured output from the LLM at every step** — not free-form text parsing.

Implementation: hermes' `AIAgent` runs a tool-calling loop with typed tool calls and streamed assistant messages. Tool calls/results map directly to `tool_call`/`tool_result` events. For the diagnostic events (`hypothesis`, `question`, `diagnosis`, `guidance`), the agent's system prompt enforces a JSON output schema per event type; `AgentService` parses the stream, validates with Pydantic, and emits SSE.

**Model compatibility:** structured-output behavior differs across providers. The LiteLLM proxy abstracts invocation, not output schema behavior. Our `AgentService` layer normalizes this — it's the one place where model-specific output parsing lives. This matters doubly now: the planned later switch to open models (see below) must not touch anything above `AgentService`.

### LLM Strategy

| Stage | Model | Rationale |
|---|---|---|
| **Now (build + validation):** primary reasoning + vision | **Gemini 2.5 Flash** | Cost-effective, fast, strong multimodal |
| **Now:** complex/fallback diagnosis | **Claude Sonnet** | Higher accuracy ceiling for edge cases |
| **Later MVP stage:** production models | **Open models — Mistral, GLM, DeepSeek** | Cost + EU data sovereignty. Switch is a LiteLLM proxy config change; the golden test harness gates the swap (no migration below the harness threshold). |
| **Phase 4+ option:** fine-tuned repair model | Open base + our trajectories | The learning pipeline collects the training set from day one (hermes trajectory format) |

> **Dev reality (0.1/0.2/2.5 runs):** all spikes and acceptance runs used `gemini-3.1-flash-lite` — the 2.5 Flash free tier (~20 req/day/project) is unusable for development. Flash-lite results are a lower bound on LLM value; paid Flash remains the prod intent. Known flash-lite weakness: imperfect language discipline (English replies to German input, 2.5 finding #5) — golden-harness item, Feature 3.2.

---

## Learning Pipeline — Field → Cloud

> **Status: implemented (Feature 2.7, 2026-07-19).** `app/services/learning_pipeline.py`,
> triggered by POST /outcome. Trajectories are per-session via a session-scoped worker CWD
> and uploaded as **raw** gzipped ShareGPT JSONL — `trajectory_compressor` is deferred until
> trajectories exceed its token budget (spec D3). Curation gate = tenant-string scrub +
> `python -m app.services.learning_pipeline promote <id>`; fleet skills sync into tenant
> homes at worker start. See `specs/2026-07-19_2229_feature_2.7_learning_pipeline/`.

> **This is what the hermes bet buys us.** The agent doesn't just log sessions — it learns from them, and we pipeline those learnings centrally. "Everything the user on the ground learns, the fleet learns."

Three artifact streams flow from each tenant's agent state to the cloud:

| Artifact | Produced by | Cloud destination | Use |
|---|---|---|---|
| **Trajectories** | Every diagnostic session (hermes trajectory format, compressed via `trajectory_compressor`) | S3 + Postgres refs, alongside Data Bridge traces | Fine-tuning dataset for the Phase 4+ repair model |
| **Skills** | Hermes' autonomous skill creation after complex diagnoses (e.g., a reusable procedure for a recurring SINUMERIK fault) | **Curation queue** | Reviewed → generalized → promoted to the shared fleet skill base → redistributed to all tenants |
| **Memory / insights** | Hermes memory manager (tenant's machine park, recurring faults, site specifics) | Stays **tenant-scoped**, backed up centrally | Better per-tenant diagnosis; never crosses tenants |

**The curation gate is non-negotiable.** Nothing crosses a tenant boundary without passing curation: automated scrubbing of tenant-identifying data, then human review (Phase 1–3; automate later). This is both GDPR hygiene and competitive isolation between customers.

**Relationship to the Data Bridge:** unchanged as the source-of-truth schema (Postgres, below). Hermes trajectories are an *additional, training-ready* export format of the same sessions — the Data Bridge records what happened; the trajectory pipeline packages it for model training.

---

## Knowledge Layer (Document Processing)

> **Status: Phase 0 spike COMPLETE (2026-07-10).** Winner: **Hybrid (Spike C)** — exact error-code lookup fast-path + LLM reasoning over narrowed candidates. Top-1 accuracy 0.75 at $0.0066/run. See `Repair_Logic_Agent/knowledge_spike/FINDINGS.md`. The section below is kept as the decision record.

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

> **Status: implemented (Feature 2.2, 2026-07-18).** `app/tools/knowledge_layer.py`
> (`KnowledgeRetrieval`) + `app/tools/error_code_lookup.py` (`ErrorCodeLookup`, owns the
> query-time code normalization). `search_semantic` is Postgres full-text search over the
> `error_codes` rows (bilingual configs, no new dependency) — embeddings/pgvector deferred
> until the PDF manual corpus is ingested. `get_page_image`/`get_compiled_article` are
> honestly empty (no document corpus, no wiki pipeline) per the shootout outcome.
> See `specs/2026-07-18_1740_feature_2.2_knowledge_tools/`.
>
> **Corpus ingestion = future knowledge crawler** (manuals + CNC online forums), Roadmap
> Feature 4.4 — deliberately out of Phase 2/3 scope (ratified 2026-07-19). Until then the
> knowledge layer stays the structured error-code spine.

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

## Visual Grounding & Image Augmentation (Phase 4+ track — decision record)

> Strategic direction (2026-07-18): understanding technical sketches and pointing to the problem **in the real world** becomes a core competence. Prototype provenance: [zurich_physical_hack](https://github.com/edavidk7/zurich_physical_hack) — Docling-parsed datasheets → Gemini agents → camera-calibrated SO-ARM100 arm probing an Arduino board. The robot arm is out; the grounding pipeline is the transferable asset.

| Concern | Prototype component | RepairRöpi equivalent |
|---|---|---|
| Sketch/schematic understanding | Docling parsing (layout, tables, figures) | Same — `docling` already a core dependency |
| Locating features on the physical object | `find_board_keypoints.py`, `pose_estimation.py`, ArUco/checkerboard calibration | OpenCV keypoint matching diagram ↔ photo; no calibration targets on a factory floor — single-photo homography, degrade gracefully to text-only |
| Pointing in the real world | 6-DOF arm + multimeter probe | Guidance overlay drawn on the technician's own photo (Pillow/OpenCV, server-side → S3, `annotated_media_key` on guidance events); live camera overlay later |
| Task planning from docs | Gemini TaskPlanner agent | Already covered: hermes agent + `guidance` events |

**Phasing:** Feature 2.3 (VisionAnalysisTool) already returns `annotated_images[]` — that output path is the seed. Phase 4.2 turns it into guidance overlays; Phase 4.3 adds schematic-to-photo projection (Roadmap Phase 4).

**New dependency when the track starts:** `opencv-python`. Nothing added now.

**Machine-agnostic invariant:** the knowledge layer, session schema (`machine_family`/`controller_family`) and tool interfaces are vertical-neutral. Verticals ship as **machine knowledge packs** (error-code seeds, taxonomy, corpus, prompts, golden cases — Roadmap Feature 4.1); the core never learns what a "CNC" is beyond its pack.

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
| **STT (Speech-to-Text)** | **Whisper large-v3** (local) | German Tier 1 language, <5% WER on clean audio. Factory noise adds 5–15% WER — acceptable with audio preprocessing. Run locally for privacy/latency. **Implemented (Feature 2.4):** `app/tools/stt.py`, `WHISPER_MODEL` config (large-v3 default; no-GPU dev boxes run `base`), forced German via `STT_LANGUAGE`. **Open deploy decision (Feature 3.1):** large-v3 needs a GPU — GPU host vs. smaller model vs. hosted STT, decided before VPS sizing. |
| **STT preprocessing** | Noise reduction before Whisper | Spectral subtraction / noise gate. Factory floors are loud. **Implemented (Feature 2.4):** noisereduce spectral gating softened to 0.75 — full-strength gating measurably *hurts* Whisper (noise-robust by training); re-tune against field recordings (spec 2.4 D3). |
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
| **Automated eval** | Run golden set on every model/prompt change | CI job: `pytest tests/eval/` — fail if **top-1 accuracy** drops below threshold (top-3 recall is a metric artifact until the golden-label taxonomy is aligned with the alarm DB — 0.1 finding, first task of Feature 3.2) |
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
| Session traces | **PostgreSQL** | Structured diagnostic traces (Data Bridge). JSONB for flexible evolution. **Source of truth.** |
| Hermes agent state | **Per-tenant `HERMES_HOME`** (files + SQLite) | Memory, skills, session cache. Rebuildable cache tier — backed up to S3, never authoritative. |
| Media (images, audio) | **Cloud S3** (Hetzner Object Storage / Scaleway / AWS S3) | No self-hosted MinIO for Phase 1. Less to operate. |
| Trajectories | **S3** (hermes trajectory format) + Postgres refs | Training-data stream of the Learning Pipeline |
| Configuration | **YAML + env vars** | Simple, version-controllable |
| DB access | **psycopg (direct SQL)** | A handful of tables doesn't justify SQLAlchemy. Plain SQL, no ORM. |

**Multi-tenancy:** `diagnostic_sessions` gains `tenant_id TEXT NOT NULL` (Phase 1 pilots: one tenant per customer). Every query is tenant-scoped; every S3 key is tenant-prefixed; every `HERMES_HOME` is tenant-dedicated.

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
    tenant_id TEXT NOT NULL,
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

### Error-code lookup table (Feature 1.1)

The exact-lookup fast path of the hybrid knowledge winner. Columns mirror the curated
`Research_Data/01_error_code_databases/*.yaml` entries; list/object fields are JSONB.
Codes are stored as printed in the manual (`AL 309`, `F07011`) — query-time normalization
belongs to the ErrorCodeLookupTool (Feature 2.2). `software_version`/`source` exist because
alarm meanings are firmware-version-specific.

```sql
CREATE TABLE error_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    controller_family TEXT NOT NULL,
    code TEXT NOT NULL,
    category TEXT,                  -- NC | DRV | PLC | HMI
    severity TEXT,                  -- error | warning | fault
    message_de TEXT,
    message_en TEXT,
    probable_causes JSONB NOT NULL DEFAULT '[]',
    recommended_actions JSONB NOT NULL DEFAULT '[]',
    related_components JSONB NOT NULL DEFAULT '[]',
    discriminating_questions JSONB NOT NULL DEFAULT '[]',
    manual_reference TEXT,
    spare_part_refs JSONB NOT NULL DEFAULT '[]',
    software_version TEXT,
    source TEXT,
    UNIQUE (controller_family, code)
);
```

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
   (Content-Type header must equal the requested content_type — it is signed;
    feature_1.2 spec D1)
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
                                                   (NOT implemented — the stream endpoint
                                                   replays the full session on fresh
                                                   connect, which covers app restore;
                                                   spec 2.6 D3. Build when a consumer
                                                   actually needs it.)
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

> **Decision LOCKED (2026-07-19, Feature 2.6): React Native + Expo (SDK 57), TypeScript strict.**
> The rule was "the choice follows the frontend developer's expertise" — the builder turned
> out to be the coding agent on a Node-only machine (no Flutter/Dart, no Android SDK).
> RN reuses the 1.4 prototype's JS contract logic, and Expo Go provides the on-phone dev
> loop with zero SDK install. See `specs/2026-07-19_0309_feature_2.6_mobile_app/`.

### Requirements
- Camera (photo + video), Microphone (voice on noisy floors)
- SSE streaming consumption, Presigned S3 uploads
- Android-first (rugged devices: CAT, Samsung XCover, Ulefone)
- Visual-first UI (diagram-heavy, reduces multilingual burden)

### As built (Feature 2.6, `RepairRöpiApp/mobile/`)

| Concern | Choice | Notes |
|---|---|---|
| Framework | **React Native + Expo SDK 57** | `create-expo-app` blank-typescript; APK via EAS cloud or `expo prebuild`+gradle (BUILD.md) |
| SSE client | **react-native-sse** (pure JS) | Lib auto-reconnect off; screen reconnects with fresh `Last-Event-ID`; monotonic-id reducer dedupes replays |
| Session restore | **SSE full replay** | Fresh connect replays the session — no `GET /sessions/{id}` needed (spec D3) |
| Camera / Audio | **expo-image-picker / expo-audio** | System camera app; m4a voice notes, live metering = ambient-noise indicator |
| Local state | **AsyncStorage** | Phone-local session list, user-turn log, offline pending-turn queue (per-media media_key write-back, fixed idempotency_key) |
| Navigation | **none** | Two screens, conditional render — react-navigation when a third screen exists |

### Decision record

| Framework | Pros | Cons |
|---|---|---|
| **React Native** ✅ | JS ecosystem, strong native modules, Expo for rapid prototyping | Requires JS/TS expertise |
| **Flutter** | AOT-compiled perf, pixel-perfect rendering across rugged device skins, excellent camera plugin | Dart ecosystem smaller; no toolchain on the build machine |
| **PWA** | No app store | **Ruled out** — insufficient camera control on rugged hardware |

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
| Deployment | **Cloud-first, multi-tenant** | Single VPS or managed containers. No k8s for Phase 1. |
| Object Storage | **Cloud S3** (Hetzner/Scaleway/AWS) | No self-hosted MinIO. Less to operate. |
| Secrets | **.env** (local), **CI secrets** (prod) | Document migration path for SME security audits. |
| Agent containment | **Egress-isolated container + tool allowlist** | No code-execution path (tool-calling only). Dual-network Docker pattern per hermes' egress-isolation doc; proxy allowlists **LLM endpoint domains + models.dev only** — domain tools run parent-side via RPC, so S3/Langfuse egress belongs to the API process, not the agent (2.5 finding, verified). |
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
hermes-agent @ git+https://github.com/NousResearch/hermes-agent@<pinned-commit>
                           # no semver upstream — upgrade deliberately, gated by golden harness
                           # NOT in pyproject.toml: hermes exact-pins its deps (openai==2.24.0)
                           # → dedicated venv .venv-hermes (Feature 1.0 spec D2); process
                           # boundary = worker subprocess, JSONL over stdio (Feature 2.5 D1);
                           # same image recipe: infra/Dockerfile.agent (egress-isolated runner)
litellm ~= 1.77            # proxy mode; pin major version
ddgs                       # keyless web search behind repair_web_search (Feature 2.5 D9)

# Document Processing
docling                    # baseline PDF parser (spike will evaluate alternatives)

# Speech
openai-whisper             # local STT (Feature 2.4; model size via WHISPER_MODEL)
noisereduce                # spectral gating before Whisper, softened (spec 2.4 D3)

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

- [x] **Phase 0 Knowledge Spike** — DONE 2026-07-10. Winner: hybrid (structured lookup + LLM over narrowed candidates). See `knowledge_spike/FINDINGS.md`.
- [x] **hermes embed spike** — DONE 2026-07-12, **GO** (commit `4281151` pinned). All four questions pass: (a) streaming maps to our SSE types, (b) skills/memory work as a library — but only with hermes' own learning tools on the allowlist (`skills_list`, `skill_view`, `skill_manage`, `memory`; amends "exactly 4 domain tools" in §Guardrails), (c) per-tenant `HERMES_HOME` isolation holds (parallel sessions, zero bleed), (d) trajectory export works (ShareGPT JSONL). See `specs/2026-07-12_0242_feature_0.2_hermes_embed/FINDINGS.md`.
- [x] **Frontend framework locked** — DONE 2026-07-19 (Feature 2.6). "Who builds it" resolved to the coding agent; React Native + Expo SDK 57 chosen (Node toolchain present, Expo Go dev loop, 1.4 JS contract reuse). See `specs/2026-07-19_0309_feature_2.6_mobile_app/requirements.md` D1.
- [x] **Langfuse deployed** — DONE 2026-07-12 (Feature 1.0). Self-hosted v3 in `Repair_Logic_Agent/infra/docker-compose.yml` (web + worker + ClickHouse + Redis; Postgres/MinIO shared with the dev stack). Dev keys provisioned via `LANGFUSE_INIT_*` — see `specs/2026-07-12_1518_feature_1.0_project_skeleton/FINDINGS.md`.

---

*Stand: Juli 2026 — v3: hermes-agent backbone, multi-tenant cloud, learning pipeline; 2026-07-18: visual-grounding track + machine-knowledge-pack invariant added; Feature 2.5 landed: worker-process embed, parent-side tool RPC, egress isolation verified (specs/2026-07-18_2246_feature_2.5_agent_service/); 2026-07-19: findings review — egress table corrected (LLM+models.dev only), eval metric → top-1 accuracy, dev-model reality noted, STT GPU decision → 3.1, corpus ingestion → knowledge crawler (Roadmap 4.4); Feature 2.6 landed: frontend locked to React Native + Expo SDK 57, app built (specs/2026-07-19_0309_feature_2.6_mobile_app/); Feature 2.7 landed: learning pipeline v1 — per-session trajectories → S3+refs, skill curation queue + fleet promotion, memory backup (specs/2026-07-19_2229_feature_2.7_learning_pipeline/)*
