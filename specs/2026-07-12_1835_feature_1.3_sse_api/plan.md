# Feature 1.3 — Plan

## Files

| File | Content |
|---|---|
| `db/migrations/002_turn_idempotency.sql` | `idempotency_key` column + partial unique index (D6) |
| `app/models/events.py` | 8 Pydantic event models, canonical fields (D8) |
| `app/db.py` | `connect()` — psycopg connection per request (pool later) |
| `app/services/agent_service.py` | `create_session()`, `handle_turn()` — scripted diagnostician (D1), persists turns + events |
| `app/api/sessions.py` | 4 routes; manual SSE framing (D2), DB-tail generator (D3/D4), replay (D5) |
| `app/main.py` | mount sessions router |
| `tests/test_sessions.py` | model schema tests (always) + flow/SSE/idempotency tests (skip w/o Postgres) |

## Order

1. Migration 002 → apply to dev DB
2. events.py → db.py → agent_service.py → sessions.py → main.py
3. Tests, ruff
4. Live acceptance: uvicorn + curl (session → turn → `curl -N` stream → replay)
5. FINDINGS.md + mirror decisions into Roadmap.md (mark 1.3 DONE, correct
   EventSourceResponse/`after` wording) — Techstack needs no change (contract implemented as written)

## Test flow (needs dev Postgres, else skip)

create session → POST turn "AL 309 …" → replay shows
`thinking, tool_call, tool_result, hypothesis×n, question, done` → duplicate POST
(same idempotency_key) returns same turn_id → `?after` cursor tails → SSE stream
frames `event:/id:/data:` and replays from start; no-code turn asks for photo; unknown
session → 404.

---

*Feature 1.3 · Stand: 12. Juli 2026*
