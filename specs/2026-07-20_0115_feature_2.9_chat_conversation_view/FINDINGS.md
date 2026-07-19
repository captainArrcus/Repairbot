# Feature 2.9 — Chat conversation view: user turns + inline media: Findings / Acceptance

**Status: BUILT, dev-verified 2026-07-20 — on-phone field check (photo → thumbnail → bubble) is the remaining acceptance step.**

## Acceptance evidence

| Check | Result |
|---|---|
| `npx tsc --noEmit` | No errors |
| `node --test services/events.test.ts` | 6/6 pass (2 new: kind-tagged interleave, media-carrying user entry + pre-2.9 entry restore) |
| `npx expo export --platform android` | Bundle builds (1.5MB hbc) |
| Field: photo → composer thumbnail before send → sent bubble shows photo + text; agent output visually distinct | **OPEN — field runbook** (scripted backend suffices, Roadmap 2.9) |

## What was built

- `LogEntry.kind: "user" | "agent"` — the reducer log IS the conversation
  (D2); user entries render as right-aligned bubbles (`userBubble` style,
  photo inline via `BubblePhoto`, audio as "🎤 Sprachnotiz · Ns" chip), agent
  entries stay compact monospace status lines. "Protokoll" heading → "Verlauf".
- `UserLogEntry` + `PendingMedia` gained `photoUri`/`audioDurationMs` /
  `durationMs` (D1, D4); old AsyncStorage entries without the fields restore
  fine (tested).
- Composer: photo chip replaced by a real Image thumbnail (local uri,
  immediately on capture) with ✕ badge; audio chip shows duration.
- `BubblePhoto` falls back to a "📷 Foto" chip on Image `onError` (D3 —
  cache uri can vanish; S3 copy is the authoritative one).

## Notes for later features

- **Feature 2.10:** the audio bubble deliberately has no transcript — the
  transcribe-echo flow puts the transcript into the TEXT field before send,
  so it arrives as bubble text naturally. No 2.9 rework expected.
- **Feature 2.11:** agent `thinking` is still only the status row, and
  tool_call/tool_result are log lines. 2.11 renders streamed thinking as an
  agent bubble in this same `kind`-dispatched list — extend `kind` or add an
  entry type there, don't fork the list.
- The user-turn text no longer embeds 📷/🎤 emojis (media renders for real);
  the session-list label still uses the emoji shorthand.

## Deviations from Roadmap

- None. App-only local echo, no backend change — exactly as specced.
