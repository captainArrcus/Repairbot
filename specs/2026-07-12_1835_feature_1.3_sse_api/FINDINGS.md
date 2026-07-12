# Feature 1.3 — FastAPI wrapper + SSE stream: Findings / Acceptance

**Status: COMPLETE — all live acceptance criteria pass (2026-07-12). The pending
`uv run pytest -q` re-run passed during Feature 1.4 acceptance: 12 passed.**

## Acceptance evidence (live uvicorn + curl, dev stack)

| Check | Result |
|---|---|
| `curl -X POST /api/v1/sessions` (no body) | `{session_id}` (`ad851666-…`) |
| POST turn `"… AL 309. Rattern …"` + machine_context | `{turn_id}` (agent turn, `84e38751-…`) |
| `curl -N …/stream` | 9 SSE frames: `thinking, tool_call, tool_result, 4× hypothesis, question, done` — each `event:` + `id: 1.N` + `data: {json}` |
| `Last-Event-ID: 1.6` reconnect | replays only `question (1.7)` + `done (1.8)` |
| Replay `…/turns/{tid}/events?after=6` | `question, done` only |
| Duplicate POST (same `idempotency_key`) | same `turn_id`, no duplicate rows |
| Unknown session / turn | 404 on turns, stream, replay |
| Migration 002 applied | `ALTER TABLE` + unique partial index OK |
| `uv run pytest -q` | **12 passed** (re-run 2026-07-12 during Feature 1.4; first run had hung in the SSE test — TestClient drains unbounded bodies; test rewritten to drive the generator directly) |
| `ruff check app tests db` + `ruff format --check` | clean (verified before the outage) |

## Notes for later features

- **Feature 1.4 (web prototype):** open the stream once per session and keep it —
  events for every turn arrive on the same connection (`event:`/`id:`/`data:` framing,
  15 s `: keep-alive` comments). On reconnect send `Last-Event-ID` (format
  `turn_index.event_index`) and nothing is lost — all events are persisted before
  they are streamed.
- **Feature 2.1 (Data Bridge):** hypotheses/hypothesis_updates rows and
  `GET /api/v1/sessions/{id}` (state + history) deliberately deferred here.
- **Feature 2.5 (real agent):** replace `agent_service._scripted_diagnosis()` with the
  hermes embed (Feature 0.2 spike wired to live callbacks); the API layer, event
  models, persistence and SSE framing need no change. Also: swap DB-poll tail
  (`POLL_S = 0.5`) for in-process push if latency matters, tenant_id from auth,
  psycopg pool if load demands.
- **TestClient cannot consume an unbounded SSE body** (it drains the response) — the
  stream test drives the `_event_stream` generator directly with a one-poll fake
  request; HTTP-level behavior is covered by the curl evidence above.

## Deviations from Roadmap (ratified in requirements.md, Roadmap corrected)

- `EventSourceResponse` is `sse-starlette`, not FastAPI → manual SSE framing, no new
  dependency (D2).
- Replay cursor `after` = integer per-turn `event_index`, not event uuid (D5).
- `POST /turns` returns the **agent** turn id — the handle the replay endpoint needs (D9).
- Event models: + `ThinkingEvent`, `DoneEvent`, required `GuidanceEvent.safety_level`
  (canonical SSE section wins over the shorter 1.3 model list, D8).

---

*Feature 1.3 · Stand: 12. Juli 2026*
