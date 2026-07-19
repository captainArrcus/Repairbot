# Feature 2.10 — Voice transcript echo: Plan

## Backend (Repair_Logic_Agent)

1. `app/api/media.py` — add `POST /{media_key:path}/transcribe`
   (tenant guard → 404, `stt.transcribe` → `{transcript, confidence}`,
   ValueError → 422, ClientError → 404, else → 502). No new files.
2. `app/services/agent_service.py` — one-condition change: STT step gated on
   `audio_keys and not text.strip()`.
3. Tests:
   - `tests/test_media.py`: transcribe success shape (stt mocked),
     wrong-tenant 404, not-audio 422 (stt mocked to raise) — run without MinIO.
   - `tests/test_sessions.py`: audio + typed text → no `stt` tool_call
     (mocked stt asserts it is never invoked); existing audio-only test keeps
     covering the fallback path.

## App (RepairRöpiApp/mobile)

4. `services/api.ts` — `transcribeMedia(mediaKey)` → POST transcribe.
5. `screens/SessionScreen.tsx` —
   - `Attachment` gains `mediaKey?: string | null`; `submitTurn` passes it
     through so `attempt()` skips the re-upload.
   - recording stop → `setAudio` + fire-and-forget upload→transcribe;
     transcript appended to composer text; guard ref (current audio uri)
     drops stale results; failure → toast + keep audio (server STT fallback).
   - audio chip shows "transkribiere …" while in flight.

## Spec mirror

6. Roadmap 2.10 → BUILT + as-built notes; Techstack endpoint table gains the
   transcribe route.

## Verify

pytest (media + sessions), `tsc --noEmit`, live dev check if stack available;
on-phone record→echo→edit→send = field runbook (like 2.9).
