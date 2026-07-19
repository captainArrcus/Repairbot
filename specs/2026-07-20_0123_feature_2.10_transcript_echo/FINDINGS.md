# Feature 2.10 — Voice transcript echo: FINDINGS

**Status: BUILT 2026-07-20, dev-verified live. On-phone record→echo→edit→send = field runbook.**

## What was built

Backend (Repair_Logic_Agent):
- `app/api/media.py` — `POST /api/v1/media/{media_key:path}/transcribe` →
  `{transcript, confidence}`. Tenant guard (404), not-audio (422), missing
  object (404), pipeline failure (502). Reuses `app/tools/stt.py` unchanged.
- `app/services/agent_service.py` — STT step now gated on
  `audio_keys and not text.strip()` (one condition; 2.4 D7 extended).

App (RepairRöpiApp/mobile):
- `services/api.ts` — `transcribeMedia(mediaKey)`.
- `screens/SessionScreen.tsx` — recording stop uploads immediately, calls
  transcribe, appends the transcript to the composer text (editable);
  Attachment carries the `media_key` so `attempt()` skips the re-upload
  (existing PendingTurn write-back). Chip shows "transkribiere …". Guard ref
  drops a stale transcript if the audio was sent/discarded in flight.
  Failure: toast, audio stays attached → server-side 2.4 STT fallback.

## Verification (2026-07-20)

1. **Live endpoint round-trip** (uvicorn + MinIO + Postgres, whisper base):
   presign → PUT `tests/stt/fixtures/sample_de.mp3` (audio/mpeg) →
   `POST .../transcribe` → `{"transcript": "Die Maschine zeigt Fehler-Code
   AL309 und die X-Axe ratert beim Verfahren.", "confidence": 0.808}` in
   ~4 s inline. Guards live-checked: foreign `X-Tenant-Id` → 404, missing
   key → 404.
2. **Skip-STT**: new `test_audio_with_text_skips_stt` — turn with text +
   audio produces NO stt tool_call (mock fails the test if invoked), typed
   text still drives the fast path. Existing audio-only test keeps covering
   the no-text fallback.
3. **Endpoint unit tests**: success shape, foreign-tenant 404 (guard runs
   before STT), non-audio 422 — run without MinIO.
4. Full backend suite **73 passed** (was 69), ruff clean, `tsc --noEmit` clean.

## Findings

1. **`:path` converter is load-bearing** — media_keys are `<tenant>/<uuid>`
   (2.5 D6); FastAPI's default str param would never match. Any future
   media-scoped route must do the same.
2. **Whisper "base" mishears domain terms** ("X-Axe ratert" instead of
   "X-Achse rattert") — exactly the feedback-item-(c) scenario the echo
   exists for: the user sees and fixes it before it drives the diagnosis.
   Reinforces the 3.1 decision (large-v3 vs. hosted STT) but needs no action
   now.
3. **~4 s inline latency (base, CPU, 5 s clip)** is fine for the echo UX;
   large-v3 in prod will be slower — the 3.1 "background jobs if pilot
   latency demands" decision now also covers this endpoint.
4. Memory note: `Repair_Logic_Agent/.venv` is the working venv for
   pytest/ruff/uvicorn (repo-root `venv/` has no pytest) — earlier note
   ".venv broken" is outdated.

## Field runbook (remaining acceptance)

Phone + laptop on same LAN, stack up, Expo Go: record a voice note → chip
shows "transkribiere …" → transcript lands in the text field → edit one
word → send → agent answers from the edited text; confirm the event stream
shows no stt tool_call for that turn.
