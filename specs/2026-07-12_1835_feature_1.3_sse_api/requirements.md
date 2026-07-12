# Feature 1.3 — FastAPI wrapper + SSE stream: Requirements

> **One sentence:** Sessions API (`create session` → `submit turn` → `SSE stream` → `replay`)
> streaming the canonical typed events, backed by an `AgentService` **stub** — the
> Wizard-of-Oz backend for the Phase 1 field test (Feature 1.4 web prototype).

---

## Context

Phase 1 is explicitly "Wizard of Oz": the API contract and event stream must be real,
the intelligence may be scripted. The real embedded hermes `AIAgent` (plus the
process-boundary decision — hermes lives in `.venv-hermes`) lands in Feature 2.5;
the FastAPI layer must not change when it does (Techstack abstraction boundary).

## Scope (from Roadmap Feature 1.3)

1. `POST /api/v1/sessions` → `{session_id}`
2. `POST /api/v1/sessions/{id}/turns` → `{turn_id}` (Techstack turn payload:
   `idempotency_key`, `text`, `media_keys`, `machine_context`)
3. `GET /api/v1/sessions/{id}/stream` → SSE (`event:`/`id:`/`data:` framing,
   Last-Event-ID resume, keep-alive comments)
4. `GET /api/v1/sessions/{id}/turns/{tid}/events?after={cursor}` → replay JSON
5. `app/models/events.py` — Pydantic schemas, canonical Roadmap names/fields
6. `app/services/agent_service.py` — stub that converts steps to events and persists them
7. `db/migrations/002_turn_idempotency.sql`, `tests/test_sessions.py`

Out of scope: `GET /api/v1/sessions/{id}` (state+history → Feature 2.1 Data Bridge),
hypotheses/hypothesis_updates rows (→ 2.1), media consumption (→ 2.3/2.4),
real agent + tenancy/auth (→ 2.5).

## Decisions

### D1: AgentService = scripted stub over seeded `error_codes` — no LLM, no hermes

Roadmap 1.3 says "AgentService stub"; hermes embed is Feature 2.5 (dedicated venv →
process boundary decided there). The stub is still real enough for a field test:
exact error-code lookup against the Feature 1.1 table (the fast path of the hybrid
knowledge winner), hypotheses from `probable_causes` (fixed confidence ladder),
question from `discriminating_questions[0]` (the seed rows carry
`evidence_type`/`expected_format` — they map 1:1 onto `QuestionEvent`). No code
found → question asking for a photo of the panel (`evidence_type: photo`).
Stub emits: `thinking → tool_call → tool_result → n×hypothesis → question → done`.
Module-level functions, not a class — the stub has no state; Feature 2.5 reshapes.

### D2: Manual SSE framing — no new dependency

Roadmap's `fastapi.responses.EventSourceResponse` does not exist in FastAPI (it's
`sse-starlette`); the Roadmap itself allows "or manually stream text/event-stream".
Framing is 3 lines over `StreamingResponse`. Roadmap wording corrected (mirrored).

### D3: Persist-then-stream; stream = DB replay + polling tail

Every event is written to `diagnostic_turn_events` (in the turn's transaction)
**before** any client sees it. The stream endpoint replays persisted events from a
cursor, then tails the table (0.5 s poll, 15 s `: keep-alive` comment). Consequences:
- Roadmap acceptance order (POST turn *then* connect) works naturally.
- Last-Event-ID resume is free — reconnect replays from the DB.
- No in-process pub/sub; upgrade to push in Feature 2.5 if poll latency matters.

### D4: SSE `id` = `{turn_index}.{event_index}` (session-monotonic composite)

`Last-Event-ID` support needs a monotonic cursor across the whole session;
`(turn_index, event_index)` is exactly that (Postgres row comparison). The `data:`
payload `id` stays a per-event UUID per the canonical schema — the SSE wire id and
the event id serve different purposes.

### D5: Replay `after` = integer `event_index` within the turn

Roadmap writes `after={event_id}`; the natural per-turn cursor is `event_index`
(the UUID is unordered). Response: `{"events": [{event_index, event_type,
event_data}, ...]}`. Roadmap wording corrected (mirrored).

### D6: Idempotency = DB unique index, duplicate POST returns the same turn

Migration 002: `diagnostic_turns.idempotency_key` + partial unique index on
`(session_id, idempotency_key)`. Retry (flaky factory WiFi) returns the original
agent `turn_id`; the concurrent-duplicate race resolves via the constraint
(`UniqueViolation` → return first writer's turn).

### D7: `tenant_id='dev'`, `machine_family` defaults `'cnc'`

No auth/tenant context until Feature 2.5 (same pattern as media_key tenant prefix,
feature 1.2 D2). Session create body is optional; `controller_family` may be set at
create or discovered later from a turn's `machine_context.controller`
(`COALESCE` update — progressive context per Techstack).

### D8: Event schemas = canonical Roadmap SSE section, superset of the 1.3 model list

The Roadmap's canonical SSE section ("must be implemented verbatim") includes
`thinking`, `done`, and `guidance.safety_level` which the 1.3 Pydantic list omits.
Implemented: all 8 models; `GuidanceEvent.safety_level` is **required**
(`low|medium|high`) — it gates the physical-safety approval flow (Techstack
guardrail 4), a default would be a hole. `tool_call` and `tool_result` are separate
models per the canonical section.

### D9: `POST /turns` returns the **agent** turn id

That's the turn holding the streamed events — the handle the client needs for the
replay endpoint. The user turn is persisted too (Data Bridge) but not returned.

---

## Acceptance (Roadmap)

- `curl -X POST http://localhost:8000/api/v1/sessions` → `{session_id}`
- POST turn (`AL 309` text) → `{turn_id}`
- `curl -N http://localhost:8000/api/v1/sessions/{id}/stream` → `event: hypothesis\ndata: {...}` etc.
- Replay endpoint returns the turn's events after a cursor
- `uv run pytest` green (flow tests skip without dev Postgres), ruff clean

---

*Feature 1.3 · Stand: 12. Juli 2026*
