# Feature 2.5 — AgentService (embedded hermes) : Findings

**Run:** 2026-07-18 · hermes commit `4281151` · model `gemini-3.1-flash-lite`
(direct Google endpoint, spec D11) · all acceptance criteria pass.

## Verdict: DONE — the hermes AIAgent is the production diagnosis backend

| Acceptance (Roadmap) | Result |
|---|---|
| Events persisted + SSE typed events, end to end | **PASS** — live 3-turn AL-309 session: 25 events in `diagnostic_turn_events`, streamed with session-monotonic wire ids (`1.0`…`3.7`), Last-Event-ID resume verified across an API restart |
| Cross-tenant zero bleed | **PASS** — `test_cross_tenant_parallel_zero_bleed` (parallel turns, tenants A/B, file-level tree scan) + live homes `acceptance/` vs `acceptance-docker/` |
| Tool allowlist asserted at session start | **PASS** — worker asserts + `ready` handshake checked against `ALLOWED_TOOLS` (one place, `hermes_backend.py`); breach → 503, nothing persisted (`test_allowlist_breach_fails_safe`) — and the check caught a real breach in the container run (below) |
| Invalid output sanitized + Langfuse error | **PASS** — parent-side Pydantic validation; `test_invalid_output_sanitized_and_logged` |
| High-safety guidance gates follow-ups | **PASS** — `test_high_safety_guidance_gates_followup`; live turn 3 emitted `safety_level: high` LOTO guidance and stopped at `awaiting_user_input` |
| Egress: non-allowlisted egress from the agent container fails | **PASS** — 3 docker-gated tests (direct egress fails, proxy blocks example.com, proxy passes the LLM endpoint) + a full live turn through the isolated container |

## Live acceptance transcript (mission core loop, verbatim run)

Tenant `acceptance`, session `d610f23a…`: turn 1 "SINUMERIK 840D, AL 309,
Rattern X-Achse" → agent calls `error_code_lookup`, then
`knowledge_retrieval`, streams 3 hypotheses + a verification question. Turn 2
(user confirms AL 309) → **exact AL 309 hit** → golden-case hypotheses (ball
screw bearing 0.5 / coupling 0.3 / guide rail 0.2) + the tactile axial-play
question. Turn 3 ("0.5mm Spiel") → h2/h3 eliminated (0.05, `eliminated_at_turn`
set), **diagnosis h1 at 0.95**, LOTO guidance `safety_level: high`, done.
Hypotheses/updates mirrored into their first-class tables (3
`hypothesis_updates`); `trajectory_samples.jsonl` in the tenant home (2.7-ready).
Turns 2–3 ran on a **respawned worker after an API restart** — the degraded
history-context path works in production conditions.

## What we had to learn (integration cost, honestly)

1. **hermes name-gates `web_search` by config, regardless of who registered
   it.** Our RPC-proxied domain tool named `web_search` was exposed on the dev
   host (search API keys in env) but silently dropped from
   `get_tool_definitions` inside the container (no keys) → handshake mismatch
   → fail-safe 503. Exactly the class of ambiguity the allowlist assert
   exists for. Fix: rename to **`repair_web_search`** — a name hermes has no
   opinions about. Rule of thumb recorded: *never reuse a hermes built-in
   tool name for a domain tool.*
2. **The 2.2-D2 family-string gap bites for real:** the model passes
   `controller_family="SINUMERIK"`, seeds store `SINUMERIK_840D_sl` → exact
   lookup missed on turn 1. Dispatcher now retries `family=None` on a family
   miss (a family filter must never hide an exact code hit). Proper family
   normalization stays the open 2.2-D2 item.
3. **`docker run -i` carries the stdio protocol across the container boundary
   unchanged** — the same `Worker` class drives both runners; only the spawn
   command differs. models.dev is allowlisted in squid (0.2 finding #7
   resolved: allow, don't pre-seed).
4. **Worker stdout must be defended:** the worker dups fd 1 for the protocol
   and points `sys.stdout` at stderr before hermes imports — one stray print
   would corrupt the JSONL stream.
5. **Language discipline is imperfect on flash-lite:** turns 2–3 replied
   partly in English despite German user text (prompt says "technician's
   language"). Not a blocker; goes on the golden-harness/prompt-tuning list
   (Feature 3.2).
6. **Scripted backend kept (spec D7)** — `AGENT_BACKEND` defaults to
   `scripted` so pytest/CI never burn tokens; dev opts into hermes with
   `AGENT_BACKEND=hermes` when starting uvicorn. This is deliberate: the .env
   stays scripted, otherwise every flow test would spawn real LLM workers.

## Deployment notes

- Egress-isolated mode: `docker compose -f infra/docker-compose.agent.yml up
  -d egress-proxy && … build agent-worker`, then run the API with
  `AGENT_RUNNER=docker`. Verified live: full diagnostic turn with the worker
  on the internal network, LLM reached only via squid.
- The agent process needs egress **only to the LLM endpoint** (+ models.dev):
  tool RPC keeps DB/S3/Langfuse/OCR/Whisper in the parent (spec D2). The
  Roadmap's assumed S3/Langfuse egress for the agent container is obsolete.
- Media keys are now tenant-prefixed (`<tenant>/<uuid>`, 1.2 forward pointer
  landed); turn media outside the session's tenant → 422; vision RPC for keys
  not uploaded in the session → refused.

## Open items → later features

| Item | Where it lands |
|---|---|
| LiteLLM proxy service (env swap by design) | Feature 3.1 (user-ratified) |
| CORS tightening to real origins | Feature 3.1 |
| Trajectory upload to S3 + skill curation queue (tenant homes now produce `trajectory_samples.jsonl` per session) | Feature 2.7 |
| Prompt language discipline + golden-case eval of the hermes backend | Feature 3.2 |
| Controller-family normalization (retry masks it, doesn't solve it) | 2.2-D2 backlog |
| Worker idle reaper / per-tenant home concurrency beyond one technician | when pilot load demands |

---

*Feature 2.5 · Stand: 18. Juli 2026 · 61 tests green (unit + stub-worker flows + egress), live acceptance complete.*
