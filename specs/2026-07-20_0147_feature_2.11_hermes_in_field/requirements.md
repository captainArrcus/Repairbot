# Feature 2.11 — Hermes agent in the field: Requirements

> **One sentence:** the interactive thinking/planning agent built in 2.5
> actually reaches the phone — every field test so far exercised the scripted
> mock (feedback round 1, item (d): "the stream just matches input text").

---

## Context

Feedback round 1 (first app field test 2026-07-19), item (d). Root cause: the
field test ran the DEFAULT scripted backend (`AGENT_BACKEND=scripted`, 2.5
D7); the hermes agent is opt-in and never reached the phone. Depends on 2.9
(the conversation view this feature renders into).

## Scope (from Roadmap Feature 2.11)

1. Dev/field environment defaults to `AGENT_BACKEND=hermes` (scripted stays
   the CI/golden default, 2.5 D7); document the switch in the field-test
   runbook.
2. Verify thinking / tool_call / tool_result events render legibly in the 2.9
   conversation view — streamed thinking as an agent bubble, tool calls as
   compact status rows.
3. On-phone field run: panel photo → visible thinking → hypotheses →
   discriminating question → answer → diagnosis.

Out of scope: any hermes_backend/worker change (the raw stream exists since
2.5), rendering question/diagnosis/guidance into the log (they have dedicated
cards since 2.6), LiteLLM proxy / prod env (3.1).

## Decisions

### D1: The default flips in `.env`, not in code

`config.py` keeps `AGENT_BACKEND = os.getenv("AGENT_BACKEND", "scripted")` —
the CI/golden default the Roadmap mandates. The dev/field `.env` (gitignored,
per-box) sets `AGENT_BACKEND=hermes`. CI has no `.env`, so nothing changes
there.

### D2: The test suite gets pinned to scripted (root cause, not symptom)

`config.py` runs `load_dotenv()`, so local pytest would silently inherit the
hermes default from D1 and try to spawn real workers. New
`tests/conftest.py` with one autouse fixture pins `config.AGENT_BACKEND =
"scripted"` for every test; the 2.5 hermes-path tests already opt in via
their own explicit monkeypatch, which wins over the autouse pin. The suite is
now deterministic regardless of the developer's `.env` — which is what 2.5 D7
meant all along.

### D3: Thinking joins the conversation log; the status row stays

2.9 note honored: extend `LogEntry.kind` (now `"user" | "agent" |
"thinking"`), don't fork the list. Every non-empty `thinking` event appends a
log entry (keyed by wire id → replay/reconnect idempotent for free) AND still
updates the transient status row (`view.thinking`, busy spinner). Empty
content (the reducer's clear signal) never becomes a bubble. Rendering:
left-aligned bubble (mirror of the user bubble), dim italic text, 🤔 prefix.
Tool calls stay the compact 🔧/✅ monospace rows from 2.9 — Roadmap wording
exactly.

### D4: Scripted thinking gets bubbles too

The scripted backend's thinking events ("Analysiere das hochgeladene Foto
…") render identically. Deliberate: one render path, and the CI/golden
backend stays a faithful stand-in for the field UI.

## Acceptance (Roadmap, verbatim)

On-phone session against `AGENT_BACKEND=hermes` shows visible
thinking/planning and at least one discriminating question; feedback item (d)
"where is the agent?" closed.
