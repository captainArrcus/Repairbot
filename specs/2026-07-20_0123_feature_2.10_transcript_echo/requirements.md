# Feature 2.10 — Voice transcript echo before send: Requirements

> **One sentence:** the user SEES (and can correct) what STT understood BEFORE
> it drives the diagnosis — record → transcript appears in the text field →
> edit → send TEXT, audio media_key stays attached for the Data Bridge.

---

## Context

Feedback round 1 (first app field test 2026-07-19), item (c): voice recording
works but the transcript is invisible before send, so the user cannot verify
what was understood. Roadmap Feature 2.10 closes it. Depends on nothing;
2.9 (chat view) is already built.

## Scope (from Roadmap Feature 2.10)

1. Backend: `POST /api/v1/media/{media_key}/transcribe` → runs the 2.4 STT
   pipeline (`app/tools/stt.py`) standalone, returns `{ transcript, confidence }`.
   Reuses the tool as-is.
2. App: after audio upload, call transcribe and put the transcript into the
   text field (editable); user corrects, then sends TEXT (audio media_key
   stays attached).
3. Turn pipeline: skip STT when the turn already carries user text
   (text-presence check in the agent_service media routing, extends 2.4 D7) —
   no double transcription.

Out of scope: word-level confidence display, transcript editing UI beyond the
plain text field, audio playback, hosted-STT latency work (3.1 decision).

## Decisions

### D1: Path-param media_key needs the `:path` converter

media_keys are tenant-prefixed (`<tenant>/<uuid>`, 2.5 D6) — they contain a
slash. The route is `/api/v1/media/{media_key:path}/transcribe`; FastAPI's
default `str` converter would 404 every real key.

### D2: Tenant guard mirrors the turn pipeline's trust boundary

The endpoint accepts `X-Tenant-Id` (default `dev`, same pre-auth pattern as
everywhere) and 404s unless `media_key` starts with `<tenant>/`. Same rule as
`agent_service._check_media_tenant` (2.5 D6): 404, not 403 — existence of
another tenant's key is not revealed.

### D3: Error mapping — 404 missing, 422 not-audio, no 500 for bad audio

`stt.transcribe` raises `ValueError` for non-audio objects → 422 with the
message. Missing S3 object (boto3 `ClientError`) → 404. Anything else (ffmpeg
choke, model failure) → 502 "Transkription fehlgeschlagen" — the app degrades
(D5), it must be able to tell "my recording is bad" from "server hiccup".

### D4: Skip-STT = text presence, exactly as the Roadmap says

`_process_turn` runs the STT step only when the turn has audio AND no user
text (`text.strip()` empty). Ratified consequence (Roadmap wording): a turn
with typed text + attached audio never transcribes server-side — the echoed
transcript (or the user's deliberate replacement) IS the text. Offline
fallback stays: app couldn't transcribe → sends audio without text → the 2.4
inline STT path runs unchanged.

### D5: App flow — upload at recording stop, degrade to the 2.4 path

On recording stop the app uploads the audio immediately (was: at send time)
and calls transcribe; the transcript is appended into the composer text field.
The Attachment carries the returned `media_key`, so the send-time queue skips
the re-upload (PendingTurn media write-back already supports pre-set keys,
2.6 D5). Upload/transcribe failure (offline, server down): toast, audio stays
attached without text — server-side STT covers it (D4). A guard ref drops the
transcript if the audio was sent/discarded while transcription was in flight
(stale echo must not land in an empty composer).

### D6: Synchronous endpoint, no job queue

Whisper runs inline in the request like every other tool since 2.4 D1
(background jobs deferred to 3.1 if pilot latency demands). The app shows a
"transkribiere …" state on the audio chip while waiting.

## Acceptance (Roadmap, verbatim)

Record voice note → transcript appears in the text field → edit one word →
send → agent works with the edited text; event stream shows no second stt
tool_call.
