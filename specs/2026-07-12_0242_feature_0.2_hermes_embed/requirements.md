# Feature 0.2 — hermes embed spike + CLI diagnostic agent: Requirements

> **One sentence:** Prove (or disprove) the Techstack-v3 hermes-agent bet by embedding
> `run_agent.AIAgent` as a library behind our own service class, driving a full diagnostic
> conversation on a laptop, and answering the four make-or-break questions with evidence.

---

## Context

Feature 0.1 concluded: **hybrid** knowledge layer wins — exact error-code lookup fast-path,
LLM reasoning over narrowed candidates, and the LLM's real home is the *conversation*
(see `Repair_Logic_Agent/knowledge_spike/FINDINGS.md`). Feature 0.2 builds that conversation.

| Asset | Status | Location |
|---|---|---|
| Hybrid knowledge layer (winner 0.1) | Working | `Repair_Logic_Agent/knowledge_spike/spike_a_structured.py` (+ `spike_c_hybrid.py`) |
| Golden cases (20) | Validated | `Research_Data/07_golden_test_cases/golden_cases.yaml` |
| hermes-agent upstream | Cloned + inspected | github.com/NousResearch/hermes-agent |
| API keys | Gemini (3 free-tier keys) | `Repair_Logic_Agent/.env` |

**Pinned commit (D1):** `4281151ae859241351ba14d8c7682dc67ff4c126` (upstream HEAD, 2026-07-11).

---

## The four spike questions (from Roadmap / Techstack v3)

1. **Streaming structure** — does the hermes stream expose enough structure to map to our
   typed SSE events (`thinking`, `hypothesis`, `question`, `tool_call`, `tool_result`,
   `diagnosis`, `guidance`, `done`)?
2. **Library mode** — do skills/memory work when `AIAgent` is driven purely as a library
   (no CLI, no gateway session store)?
3. **Tenant isolation** — does per-`HERMES_HOME` isolation hold (two parallel sessions,
   zero state bleed)?
4. **Trajectory export** — can we export a session trajectory in hermes' trajectory format?

A **GO/NO-GO decision** on hermes must be documented with evidence for all four.
If we fight the framework, we drop to the escape hatch (LiteLLM tool-calling + plain loop)
and the rest of the roadmap is unchanged.

---

## Scope

### In Scope

1. `Repair_Logic_Agent/agents/hermes_service.py` — `HermesAgentService` embedding
   `run_agent.AIAgent` (pinned commit), with:
   - `start_session(session_id) -> None`
   - `handle_user_turn(text, media_paths=None) -> list[StepEvent]`
   - exactly **one** registered tool: `knowledge_retrieval(query)`
   - typed step events, validated before emission
2. `Repair_Logic_Agent/agents/run_cli.py` — interactive CLI; logs typed step JSON per step.
3. `Repair_Logic_Agent/agents/spike_checks.py` — runnable evidence for the four questions.
4. GO/NO-GO findings documented in this spec folder.

### Out of Scope

| Item | Why Not Now |
|---|---|
| FastAPI / SSE endpoints | Feature 1.3 |
| Pydantic event models | Feature 1.3 (spike uses dataclasses; schema names/fields already match) |
| Media handling (photos/audio) | Features 2.3/2.4 — `media_paths` param exists but is rejected with a clear message |
| Egress isolation container | Feature 2.5 — containment here is the tool allowlist |
| Langfuse tracing | Cross-cutting, Phase 1 |
| Postgres persistence | Feature 1.1 |

---

## Key Decisions

### D1: Pin `4281151ae859241351ba14d8c7682dc67ff4c126`

Upstream HEAD at spike time. No semver upstream; upgrades are deliberate and gated by the
golden harness (Techstack v3). Install into a **dedicated venv** (`.venv-hermes`) — hermes
exact-pins its dependencies (e.g. `openai==2.24.0`) and must not fight the knowledge-spike venv.

### D2: `knowledge_retrieval` = the structured spine; the agent IS the LLM half of the hybrid

Feature 0.1's winner is "exact lookup fast-path + LLM over narrowed candidates". Embedded in
an agent, the second half is the agent itself. The tool therefore returns structured data only:

- exact error-code hit → full alarm record(s), `confidence=1.0`, no LLM anywhere
- no/ambiguous hit → top-5 TF-IDF-narrowed candidates for the *agent* to reason over

No nested LLM call inside a tool (cheaper, no double-reasoning, exactly the FINDINGS
recommendation). Reuses `spike_a_structured.py` — no new retrieval code.

### D3: OpenAI-compatible `base_url`; spike runs direct-Gemini, production runs LiteLLM proxy

`AIAgent` speaks the OpenAI protocol to any `base_url` — that is the actual bet being tested.
The spike defaults to Google's OpenAI-compatible endpoint
(`https://generativelanguage.googleapis.com/v1beta/openai/`) with the existing free-tier keys
and `gemini-3.1-flash-lite` (same free-tier reality as documented in 0.1's FINDINGS §Model note).
Production swaps `REPAIR_LLM_BASE_URL` to the LiteLLM proxy (Gemini 2.5 Flash primary /
Claude fallback via `AIAgent(fallback_model=...)`) — a config change, zero code. No Anthropic
key exists in `.env`, so the Claude fallback is configured-but-not-exercised in this spike.

### D4: Typed events via callbacks + an NDJSON output protocol

- `tool_call` / `tool_result` come from hermes' `tool_start_callback` / `tool_complete_callback`.
- Diagnostic events (`thinking`, `hypothesis`, `question`, `diagnosis`, `guidance`, `done`)
  come from the model itself, constrained to emit **one JSON object per line** by a protocol
  prompt injected via `ephemeral_system_prompt` — which hermes *appends* to its own built
  system prompt (verified in `agent/conversation_loop.py:517`), so skills/memory scaffolding
  stays intact (this is what makes Q2 answerable).
- Every parsed event is validated against required fields; invalid output is sanitized into a
  `thinking` event and logged — raw output is never forwarded (Feature 2.5 rule, applied early).

### D5: Tenant isolation = one process, one `HERMES_HOME`

The isolation check runs two subprocesses with distinct `HERMES_HOME` dirs and distinct tenant
marker strings, then asserts neither home's state (sessions, memory, skills, trajectories)
contains the other tenant's marker. This mirrors the production pattern (per-tenant
`HERMES_HOME`, Techstack §Guardrails 3).

### D6: Allowlist of one, enforced and asserted

A custom toolset `repair_knowledge` containing exactly `knowledge_retrieval` is registered;
`AIAgent(enabled_toolsets=["repair_knowledge"])`. At startup the service asserts the resolved
tool definitions contain **no terminal, browser, code-execution, or delegation tools** and
fails loudly otherwise. Whatever hermes core still injects (e.g. memory/skill helper tools) is
recorded in FINDINGS — that list is an input to Feature 2.5's guardrail design.

---

## Acceptance (from Roadmap)

- `python agents/run_cli.py` — interactive; input
  `"Controller: SINUMERIK 840D, AL 309. Rattling when jogging X."` streams
  thinking → hypothesis (JSON) → question → …; CLI log contains typed step JSON per step.
- `python agents/spike_checks.py` — answers the four questions, writes evidence JSON.
- GO/NO-GO documented in `specs/2026-07-12_0242_feature_0.2_hermes_embed/FINDINGS.md`.

---

*Feature 0.2 · Stand: 12. Juli 2026*
