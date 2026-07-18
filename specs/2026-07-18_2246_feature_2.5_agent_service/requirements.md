# Feature 2.5 — AgentService: embedded hermes AIAgent + guardrails: Requirements

> **One sentence:** The scripted diagnostician's internals are replaced by the
> embedded hermes `AIAgent` (pinned commit, productionized from the 0.2 spike)
> running as a tenant-isolated worker process behind `agent_service`, with the
> ratified 8-tool allowlist, parent-side Pydantic validation of every event,
> the physical-safety approval gate, and Docker egress isolation for the agent
> process — while Postgres stays the source of truth and the SSE contract is
> unchanged.

---

## Context

Feature 1.3 shipped `agent_service` as a scripted stub; 2.2–2.4 gave it real
tools (lookup, knowledge, vision, STT). The 0.2 spike proved the hermes embed
(GO, commit `4281151`) and left the open items that land here: multi-session
concurrency in one deployment, the egress-isolation container, and the
models.dev allowlist decision. The two-venv reality (hermes exact-pins its
deps → `.venv-hermes`; the app lives in `Repair_Logic_Agent/.venv`) makes the
"process boundary between API layer and agent" (Techstack 1.0-D2 pointer) the
central design constraint.

## Scope (from Roadmap Feature 2.5)

1. `agent_service` embeds hermes `AIAgent` (worker process) with the ratified
   tool allowlist (4 domain + 4 learning tools), per-tenant `HERMES_HOME`
2. Event mapper hermes → Pydantic events; invalid output sanitized + Langfuse
   error, never forwarded raw
3. `guidance` safety_level=high approval gate
4. Tenant plumbing: sessions carry a real tenant_id; media_key gains the
   tenant prefix (1.2 forward pointer)
5. Egress isolation: agent container on an internal Docker network, egress
   proxy allowlist, verified by a test
6. Acceptance: events persisted to diagnostic_turn_events, SSE streams valid
   typed events, cross-tenant zero-bleed test

Out of scope: LiteLLM proxy service (deferred to 3.1 — **user-ratified**),
mobile app (2.6), learning pipeline collection (2.7), auth (tenant comes from
a header until then), CORS tightening (3.1, real origins unknown until
deploy).

## Decisions

### D1: Process boundary = worker subprocess per session, JSONL over stdio

Hermes cannot live in the app venv (exact-pins, e.g. openai==2.24) and
`HERMES_HOME` is process-global env — so the agent runs as a **worker
process** (`agents/hermes_worker.py`, executed with `.venv-hermes/bin/python`)
spawned per session, speaking newline-delimited JSON over stdin/stdout.
Per-tenant isolation is per-worker env: `HERMES_HOME=<root>/<tenant_id>` and
CWD = tenant dir (trajectories append to CWD — spike finding #5, ready for
2.7). Workers stay alive across turns (in-memory hermes history); one turn at
a time per session (concurrent turn → 409). Worker death → respawn with
degraded context rebuilt from persisted turns.
<!-- ponytail: degraded respawn = prior turn texts, not full hermes state;
     full session-cache restore only if field data shows it matters -->

### D2: Domain tools execute parent-side via stdio RPC — the agent process holds no credentials

When hermes calls a domain tool, the worker emits a `tool` request line and
blocks; the parent executes the real implementation (`app/tools/…` — DB, S3,
OCR, web) and replies. Consequences:

- DB/S3 credentials, torch, whisper, tesseract never enter the agent process.
- The agent's only egress need is **the LLM endpoint** (+ models.dev metadata,
  spike finding #7) — the egress allowlist shrinks below what the Roadmap
  assumed (S3/Langfuse egress is the *parent's* need, not the agent's).
- `tool_call`/`tool_result` events are synthesized parent-side at RPC time —
  live streaming and honest result summaries in one place.
- Media keys the agent may analyze are guarded: an RPC for a media_key not
  uploaded in this session is refused (trust boundary).

Vision moves from inline (2.3) to **agent-called** — the protocol prompt
instructs the agent to call `vision_analysis` on new photo media keys, which
is what Roadmap 2.3 always said ("agent calls VisionAnalysisTool"). STT stays
inline (2.4 D7): it is an input adapter, and deliberately NOT on the agent's
tool list (Techstack Phase-1 tool table has no STT row).

### D3: Allowlist = 4 domain + 4 learning tools, asserted via handshake

`vision_analysis`, `error_code_lookup`, `knowledge_retrieval`,
`repair_web_search` (renamed from `web_search` during acceptance — hermes
name-gates its own `web_search` by config, FINDINGS #1)
(domain, RPC-proxied) + `memory`, `skills_list`, `skill_view`, `skill_manage`
(hermes learning loop — file-based, tenant-scoped; 0.2 finding, ratified).
The worker registers exactly these, asserts the exposed set, and reports it in
its `ready` handshake; the parent hard-fails the session (error event, worker
killed, Langfuse error) on any mismatch. No terminal, no browser, no MCP, no
subagents — never registered. Enforcement lives in ONE place
(`ALLOWED_TOOLS` in `app/services/hermes_backend.py`, checked at every
session start — Techstack cross-cutting requirement).

### D4: Parent-side Pydantic validation; incremental event persistence

The worker parses the NDJSON protocol (0.2 spike format — model discipline
was perfect) but the **validation authority is the parent**: every event op is
built into an `app/models/events.py` model; ValidationError / unknown type /
raw prose → sanitized `ThinkingEvent` (truncated content) + Langfuse error via
`app/services/observability.py`. Raw output is never forwarded.
`introduced_at_turn` is injected parent-side (the model doesn't know turn
indexes).

Events are now persisted **incrementally** (commit per event) instead of one
transaction per turn, so the existing SSE DB-poll tail streams mid-turn — no
change to the SSE endpoint or wire contract. The agent turn row is created
before streaming; content/tools_called are finalized at turn end. If the
backend dies mid-turn, the shell appends an error `thinking` + `done` — a turn
never 500s and never leaves a stream hanging.

### D5: Safety gate = suppress follow-up steps after high-safety guidance

After a `guidance` with `safety_level="high"` streams, all further events of
that turn except `done` are suppressed (logged to Langfuse, not persisted) and
the turn ends `done: awaiting_user_input`. The protocol prompt additionally
instructs the agent to stop after a high-safety step and ask for confirmation
— prompt instructs, shell enforces. The technician's next turn is the
explicit confirmation; the agent continues from history. Enforced in the
shared persistence loop (one place, backend-agnostic).

### D6: Tenant identity = `X-Tenant-Id` header, default "dev"

No auth exists in Phase 1 pilots (one tenant per customer); the header is the
honest minimal carrier and the API shape auth will later fill.
`POST /sessions` stores it; `POST /media/upload-url` prefixes the media_key
(`<tenant>/<uuid>` — the 1.2 forward pointer lands). Turn media_keys must
match the session's tenant prefix (bare legacy keys allowed for `dev` only) —
cheap trust-boundary check, 422 otherwise.

### D7: Scripted diagnostician stays as the deterministic backend (`AGENT_BACKEND`)

`AGENT_BACKEND=scripted|hermes` (default **scripted**: CI has no hermes venv
and no LLM key; no surprise token costs). The 2.2–2.4 pipeline tests keep
their meaning against the scripted backend, and Feature 3.2's golden harness
needs exactly this deterministic mock. Both backends produce the same event
stream through the same persistence shell — `handle_turn` is backend-agnostic;
the backend seam is one generator function. Dev `.env` opts into hermes.

### D8: Egress isolation = worker container only (user-ratified)

`infra/Dockerfile.agent` (python:3.13-slim + hermes pinned commit — no torch,
no app deps, thanks to D2) + `infra/docker-compose.agent.yml`: an
`internal: true` Docker network (no default route) and a squid egress proxy
allowlisting only the LLM endpoint domains + models.dev.
`AGENT_RUNNER=docker` wraps the worker spawn in `docker run -i` on the
internal network with `HTTPS_PROXY` pointed at the proxy (stdio RPC works
across the container boundary unchanged). `AGENT_RUNNER=subprocess` remains
the dev/test default. `tests/agent/test_egress_isolation.py` (docker-gated)
proves: direct egress from the container fails, non-allowlisted host via
proxy is blocked, allowlisted LLM host via proxy connects.

### D9: WebSearchTool = thin ddgs wrapper, not unified_search.py

Techstack said "already built (unified_search.py)" — but that module is an
800-line multi-engine zoo needing 6 extra deps and 3 API keys, with broken
indentation in its current state. The agent needs one function:
`web_search(query) → [{title, href, body}]`. `app/tools/web_search.py` wraps
`ddgs` (DuckDuckGo, keyless, one small dep), exposed to the agent as
`repair_web_search` (D3). Tavily is the documented upgrade path (key already
in `.env`) when result quality demands it. Techstack row amended.

### D10: `stream_events` stays the SSE DB-tail in the API layer

Roadmap names `AgentService.stream_events(session_id)`; the existing
`sessions._event_stream` **is** that generator and is HTTP-lifecycle-bound
(Last-Event-ID, disconnect polling). Moving it into agent_service would be
churn without behavior. agent_service owns event *production and
persistence*; the API layer owns event *delivery*. Roadmap annotated.

### D11: LLM endpoint = direct provider URL (user-ratified)

`REPAIR_LLM_BASE_URL` / `REPAIR_LLM_MODEL` / `REPAIR_LLM_API_KEY` (falls back
to `GOOGLE_API_KEY`), same as the spike. LiteLLM proxy lands with the 3.1
deploy; the swap is an env change by design. Claude fallback stays available
via `AIAgent(fallback_model=…)` when a key exists. The 2.3 config comment
("proxy endpoint comes with 2.5") is corrected to 3.1.

---

## Acceptance (Roadmap)

- Events persisted to `diagnostic_turn_events`, SSE streams valid typed
  events — with `AGENT_BACKEND=hermes` end-to-end (live run, FINDINGS).
- Cross-tenant test: two parallel sessions, different tenant_ids, zero state
  bleed (per-tenant homes, verified file-level).
- Allowlist asserted at session start; handshake mismatch fails safe.
- Invalid agent output sanitized + Langfuse error; never forwarded raw.
- High-safety guidance gates follow-up steps until user confirmation.
- Egress test: non-allowlisted egress from inside the agent container fails.

---

*Feature 2.5 · Stand: 18. Juli 2026*
