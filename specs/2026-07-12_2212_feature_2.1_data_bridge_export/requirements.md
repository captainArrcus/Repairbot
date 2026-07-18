# Feature 2.1 — Data Bridge completion & export: Requirements

> **One sentence:** Sessions become complete, training-ready traces — hypotheses and
> outcomes land in their first-class tables, and `GET /sessions/{id}/export` returns
> the Roadmap training JSON.

---

## Context

Feature 1.1 created all six trace tables; Feature 1.3 fills three of them
(`diagnostic_sessions`, `diagnostic_turns`, `diagnostic_turn_events`). Hypotheses
exist only as SSE events, `session_outcomes` has no write path at all — so no
session can be reconstructed as a Techstack Training Example. This feature closes
that gap. The hermes trajectory export (richer format) stays in Feature 2.7.

## Scope (from Roadmap Feature 2.1)

1. `app/services/agent_service.py` — persist `hypotheses` + `hypothesis_updates`
   rows at event-emission time
2. `POST /api/v1/sessions/{id}/outcome` — write path for `session_outcomes` (D3)
3. `app/services/traces.py` — assemble export JSON (+ Pydantic schema)
4. `app/api/sessions.py` — `GET /api/v1/sessions/{id}/export` route
5. `tests/traces/test_export_schema.py` — export validates against the schema

Out of scope: hermes trajectory format + S3 upload (→ 2.7), tenant scoping of
export (→ 2.5), any UI for recording outcomes (→ 2.6).

## Decisions

### D1: No new migration

Roadmap 2.1 says "tables with SQL migrations" — all six tables shipped in
`db/migrations/001_create_schema.sql` (Feature 1.1). Nothing to migrate.

### D2: Hypotheses persisted where they are emitted, upsert by (session_id, description)

`agent_service` is the single writer, inside the existing per-turn transaction.
First sighting of a description → INSERT into `hypotheses`; re-sighting with a
different confidence → `hypothesis_updates` row (before/after, evidence = user
turn text + first media key) and confidence UPDATE. SELECT-then-INSERT is fine
under the one-transaction-per-turn model; no unique index needed yet.

### D3: `POST /api/v1/sessions/{id}/outcome` (not in Roadmap — ratified 2026-07-12)

Without a write path, `session_outcomes` stays empty and every export lacks its
training label (`outcome` is the supervision signal of the Training Example).
User cleared adding it where needed: the API — the mobile app (2.6) will call it,
the field test can curl it.

Body: `outcome` (resolved|escalated|failed, required), `final_diagnosis` (text),
`repair_action`, `verification_media_ref`, `resolution_time_minutes`,
`technician_confidence` (1–5). Upsert `ON CONFLICT (session_id) DO UPDATE` — a
technician may correct the outcome. Also sets `diagnostic_sessions.status`.

`final_diagnosis` text is matched against the session's `hypotheses.description`;
match → `is_final_diagnosis = true` + `final_diagnosis_id`. No match → new
hypothesis row (confidence 1.0, `is_final_diagnosis = true`): the technician
naming a diagnosis the agent never raised is exactly the training signal we want.

### D4: Export shape = Roadmap JSON; chain entries carry both roles

`{session_id, machine_context, initial_observation, diagnostic_chain,
final_diagnosis, outcome}`. `diagnostic_chain` = every turn in order:
`{turn_index, role, content, media_keys, events}` (events only on agent turns) —
the user turns are the `evidence_presented` of the Techstack ideal; the
hypotheses_before/after view stays reconstructable from the first-class tables
and is not duplicated into the export (revisit in 2.7 if the trajectory
compressor wants it).

### D5: Export schema is Pydantic, lives in traces.py

The "training schema" the acceptance test validates against is the response
model itself — one source of truth, FastAPI validates on the way out, the test
validates the parsed JSON round-trip.

### D6: Export works mid-session

`final_diagnosis` and `outcome` are `null` until an outcome is posted — export
must not 500 on an open session. 404 only for unknown session ids.

---

## Acceptance (Roadmap)

Run session in dev → `GET /api/v1/sessions/{id}/export` → JSON validates against
training schema (`tests/traces/test_export_schema.py`).

---

*Feature 2.1 · Stand: 12. Juli 2026*
