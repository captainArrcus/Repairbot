# Feature 2.11 — Hermes agent in the field: FINDINGS

**Status: BUILT 2026-07-20, dev-verified live end to end. On-phone hermes
session = the field runbook below.**

## What was built

Backend (Repair_Logic_Agent):
- `.env` — `AGENT_BACKEND=hermes`: the dev/field stack now runs the real
  agent by default. Code default stays `scripted` (CI/golden, 2.5 D7).
- `tests/conftest.py` (new) — autouse fixture pins the suite to the scripted
  backend regardless of `.env`; the 2.5 hermes tests opt in explicitly and
  their monkeypatch wins over the pin.

App (RepairRöpiApp/mobile):
- `services/events.ts` — `LogEntry.kind` gains `"thinking"`; non-empty
  thinking events land in the conversation log (wire-id keyed → replay
  idempotent) while still driving the transient status row.
- `screens/SessionScreen.tsx` — thinking entries render as left-aligned
  agent bubbles (dim italic, 🤔); tool_call/tool_result stay the compact
  🔧/✅ rows from 2.9.

## Verification (2026-07-20)

1. **Live 2-turn hermes session through the new default** (uvicorn with NO
   shell override — the `.env` flip did the switching; dev Postgres + MinIO,
   gemini via `.venv-hermes` worker):
   - Turn 1 ("SINUMERIK 840D, AL 309, X-Achse rattert"): `tool_call` +
     `tool_result` (error_code_lookup exact hit) → `thinking` → 3
     `hypothesis` → discriminating `question` (axial-play check) → `done`.
   - Turn 2 ("0,5 mm Spiel, Kupplung fest"): `thinking` → hypothesis updates
     (0.95 / coupling ELIMINATED 0.05 / 0.1) → `diagnosis` conf 0.95 →
     `guidance` → `done`. Outcome posted (worker dropped, 2.7 harvest ran).
2. **Phone-render stand-in**: captured the session's real SSE replay and fed
   it through the actual `applyEvent` reducer — conversation log shows
   2 thinking bubbles interleaved with the tool rows, hypotheses/diagnosis/
   guidance populate their cards. Exactly what SessionScreen renders.
3. **App checks**: `node --test services/events.test.ts` 7/7 (1 new),
   `npx tsc --noEmit` clean.
4. **Backend suite with the flipped `.env`**: 73 passed — the conftest pin
   holds; `ruff check app tests` clean.

## Findings

1. **`load_dotenv()` + a behavior-changing env default is a trap** — without
   the conftest pin, every local pytest run would have silently switched to
   spawning real hermes workers. Any future `.env` default that changes
   behavior needs the same treatment.
2. **Language discipline confirmed live (2.5 finding #5)**: German user text
   → English thinking/hypotheses/question from gemini. Field-usable but
   wrong for technicians; stays gated by the 3.2 harness check (no action
   here — prompt wording belongs to the worker, out of 2.11 scope).
3. Pre-existing (not from 2.11): `ruff format --check app tests` flags
   `app/api/media.py` + `app/tools/error_code_lookup.py` (committed in
   2.10/2.8). Local ruff version drift vs. CI's — cleanup candidate, not
   urgent.
4. Turn latency with gemini-3.1-flash-lite: ~15–60 s per turn (tool round
   trips included) — noticeably slower than scripted. The 2.6 status row
   ("Agent arbeitet …" + spinner) covers the wait; 3.1's background-jobs
   decision also covers this.

## Field runbook (remaining acceptance — closes feedback item (d))

Laptop: `docker compose -f infra/docker-compose.yml up -d` → `.venv/bin/uvicorn
app.main:app --host 0.0.0.0` (`.env` already selects `AGENT_BACKEND=hermes`;
`S3_ENDPOINT_URL` must be the laptop's LAN IP, 1.4 pattern). Phone (Expo Go
or APK, same LAN): new session → panel photo → send → **visible 🤔 thinking
bubbles** while the agent works → hypotheses → discriminating question →
answer it → diagnosis + guidance. Also re-check the 2.9/2.10 runbook items
(photo thumbnail → bubble; voice → transcript echo → edit → send) in the same
session — one field run covers all three features.
To fall back mid-field-test: `AGENT_BACKEND=scripted` in the shell env
overrides `.env`.
