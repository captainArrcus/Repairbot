# Feature 2.11 — Hermes agent in the field: Plan

Smallest diff that closes feedback item (d). No backend logic changes — the
event stream has existed since 2.5; this is an env default + a render path.

1. **Backend env flip (D1/D2)**
   - `Repair_Logic_Agent/.env`: `AGENT_BACKEND=hermes` (+ comment).
   - `Repair_Logic_Agent/tests/conftest.py` (new): autouse fixture pins
     `config.AGENT_BACKEND = "scripted"` — local suite stays deterministic.

2. **App: thinking bubbles (D3)**
   - `services/events.ts`: `LogEntry.kind` gains `"thinking"`; the
     `thinking` case appends a log entry when content is non-empty.
   - `screens/SessionScreen.tsx`: render `kind === "thinking"` as a
     left-aligned agent bubble (`agentBubble` + `thinkingText` styles).
   - `services/events.test.ts`: one new test — thinking interleaves with tool
     rows in the log, empty content skipped, replay idempotent, done still
     clears the status row.

3. **Verify**
   - `node --test services/events.test.ts`, `npx tsc --noEmit`.
   - Backend suite + ruff (CI scope `app tests`) with the new `.env` in place
     — proves the conftest pin.
   - Live dev run: uvicorn with no shell override (→ hermes via `.env`),
     2-turn AL-309 session over the real API, then the captured SSE replay
     fed through the real app reducer (phone-render stand-in).

4. **Docs**: field runbook section in FINDINGS; Roadmap status mirror.
