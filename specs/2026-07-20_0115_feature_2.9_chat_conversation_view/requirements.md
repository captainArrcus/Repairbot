# Feature 2.9 — Chat conversation view: user turns + inline media: Requirements

> **One sentence:** SessionScreen reads as a conversation — user turns are
> right-aligned chat bubbles with their photo/audio inline, agent output stays
> left/full-width, and the captured photo is visible in the composer BEFORE send.

---

## Context

Feedback round 1 (first app field test 2026-07-19), items (a) and (b): no
visual distinction between user input and agent output, and the captured photo
never shown. Closes both. Transcript echo is Feature 2.10; hermes-in-the-field
is 2.11 (depends on this rendering).

App-only change — user turns are a local echo at submit time (Roadmap 2.9),
the backend contract is untouched.

## Scope (from Roadmap Feature 2.9)

1. USER turns render as visually distinct right-aligned chat bubbles
   (text + media); agent events stay left/full-width.
2. Photo: thumbnail in the composer IMMEDIATELY on capture (local uri from
   expo-image-picker); same image inline in the sent user-turn bubble.
3. Audio: chip in the user bubble showing duration.

Out of scope: transcript display (2.10), showing hermes thinking/tool events
as first-class agent bubbles (2.11), fetching media from S3 for bubbles (local
uri is the echo — server media stays Data-Bridge-only).

## Decisions

### D1: Extend the existing user log, don't invent a message store

Feature 2.6 already persists a per-session `UserLogEntry[]` (AsyncStorage) and
merges it into the reducer's sorted `log`. 2.9 extends that entry with
`photoUri` and `audioDurationMs` — same storage, same sortKey merge, same
replay path. Old stored entries (text-only) keep working; the new fields are
optional.

### D2: One log, two renderings — `kind` on LogEntry

The reducer's `log` stays the single ordered conversation. `LogEntry` gains
`kind: "user" | "agent"` (+ optional media fields); SessionScreen renders
`user` entries as right-aligned bubbles and `agent` entries as the existing
compact status lines. The stateful panels (hypotheses, question card,
diagnosis, guidance) are NOT conversation items and stay as-is — 2.11 will
revisit agent-event rendering.

### D3: Photo bubbles use the local uri; degrade to a chip

expo-image-picker returns a cache-dir uri; the OS may purge it eventually.
The bubble shows the Image from the local uri and falls back to a "📷 Foto"
chip via `onError` if the file is gone. Good enough for a local echo — the
authoritative copy went to S3 with the turn.

### D4: Audio duration captured at stop

`recState.durationMillis` is read when the recording stops and travels with
the Attachment → PendingTurn → UserLogEntry, so the bubble chip shows
"🎤 12s". No playback in v1 (nobody asked for it; the transcript is 2.10).
