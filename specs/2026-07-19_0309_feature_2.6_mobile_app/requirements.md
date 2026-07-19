# Feature 2.6 — Mobile App V1: Requirements

> **One sentence:** The real technician-facing app — session list, streaming
> diagnostic view (hypotheses, question CTA, guidance, diagnosis), evidence
> capture (camera, voice note with ambient-noise meter, numeric/text input),
> presigned uploads, SSE with replay/reconnect, offline-resilient turn queue —
> as an installable Android app built with React Native + Expo.

---

## Context

Feature 1.4's web prototype proved the full flow on a phone (field-tested
2026-07-19). Feature 2.6 replaces it with the real app: structured evidence
capture is the product (Mission: "the app's structured evidence capture is the
product"). The backend contract (1.2 presign, 1.3 SSE, 2.1 outcome/export,
2.5 tenant header + safety gate) is complete and live-verified — this feature
is frontend-only; **zero backend changes**.

## Scope (from Roadmap Feature 2.6)

- Screens: SessionList/NewSession, SessionScreen (SSE stream view)
- Presigned upload flow, SSE client with Last-Event-ID + replay on reconnect
- Evidence widgets: camera, audio recorder w/ ambient noise indicator, quick
  numeric input
- Offline resilience: cache uploaded media_keys pending network, sync on
  reconnect (full offline-first explicitly NOT required)
- Acceptance: installable APK on rugged Android runs the end-to-end flow

Out of scope: iOS (optional later), auth (tenant stays a header), push
notifications, offline-first, multilingual UI beyond German (Phase 1 = de).

## Decisions

### D1: Framework = React Native + Expo (SDK 57) — Techstack lock closed

Techstack said "choice follows the frontend developer's expertise". The
builder reality: coding agent + this machine — Node 24 present, no
Flutter/Dart, no Android SDK. RN reuses the 1.4 prototype's JS contract
logic 1:1, the Roadmap's file examples were already RN, and **Expo Go** gives
the on-phone dev loop with zero Android SDK (QR scan, same-LAN — exactly the
1.4 field-test pattern). PWA stays ruled out (camera control). APK paths:
EAS cloud build or `expo prebuild` + gradle (BUILD.md). Scaffold:
`create-expo-app` blank-typescript; TypeScript strict (template default —
Roadmap's `.js` file names become `.tsx`).

### D2: No navigation library

Two screens, conditional render in `App.tsx`. react-navigation (4 packages)
buys nothing at n=2. Add when a third screen exists.

### D3: Session restore = SSE full replay; `GET /sessions/{id}` stays unbuilt

The 1.3 stream endpoint replays the whole session on fresh connect (cursor
starts at (-1,-1)) — reopening a session is just "connect and reduce".
The Techstack API contract lists `GET /api/v1/sessions/{id}` (state+history);
it was never implemented and V1 does not need it — annotated in Techstack,
not built (ladder rung 1). User turns are not in the event stream; they
persist phone-local (AsyncStorage) with an interleave sort key
`(lastTurnIndex + 0.5) * 1000` — user text slots before the agent turn that
answers it (turn indexes alternate user/agent).

### D4: SSE client = react-native-sse, reconnect owned by the screen

RN has no native EventSource; `react-native-sse` is a small pure-JS
implementation. Its auto-reconnect is disabled (`pollingInterval: 0`) — the
screen reconnects (3 s) with a **fresh** `Last-Event-ID` from the reducer
state, which the lib cannot know. The reducer's monotonic wire-id filter
(`t.e` tuple compare) makes duplicate replays no-ops, so a reconnect without
resume state is merely wasteful, never wrong. Stream error with HTTP 404 →
session vanished (dev DB reset) → remove locally + back to list.

### D5: Offline resilience = one pending turn, persisted with per-media upload progress

`PendingTurn {idempotencyKey, text, media[{localUri, contentType, mediaKey}]}`
in AsyncStorage. `mediaKey` is written back after each successful presign+PUT —
an uploaded file is never uploaded twice across retries (Roadmap: "cache
uploaded media_keys pending network"). `idempotency_key` is generated once at
queue time → the 1.3 unique index makes retries duplicate-safe. Auto-retry
every 8 s + manual "Erneut senden" + "Verwerfen". Error policy: network error
→ keep + retry; 409 (agent busy) → keep + retry; 422/404 → drop + toast (the
turn is invalid, retrying cannot fix it). One turn at a time — matches the
backend's one-turn-per-session lock (2.5). No NetInfo dependency; the
interval is the reconnect detector.

### D6: Evidence capture = expo-image-picker + expo-audio (metering = noise indicator)

Camera: `launchCameraAsync` (system camera app — rugged devices keep their
tuned camera UI). Audio: `expo-audio` recorder, HIGH_QUALITY preset + 
`isMeteringEnabled` — the live dB meter renders as the Roadmap's "ambient
noise indicator" (red > ~75 %). Output m4a (`audio/m4a` passes the 1.2
`audio/*` allowlist; Whisper/ffmpeg reads m4a). Upload = presign + RN
`fetch(localUri).blob()` + PUT with signed Content-Type. Numeric questions
(`evidence_type: "numeric"`) switch the composer input to decimal keyboard
with `required_format` placeholder. Photo/audio CTAs highlight per
`question.evidence_type`.

### D7: High-safety guidance → explicit confirm CTA

Per 2.5 D5 the backend suppresses follow-ups after `safety_level: "high"`
guidance until the technician's next turn. The app renders high-safety steps
red-flagged and, when the turn ended on one, shows a prominent
"Schritt umgesetzt — weiter" button that sends a plain confirmation turn.
No new API — the confirming user turn IS the unblock signal.

### D8: Outcome UI on `awaiting_verification`

When the agent ends a turn `awaiting_verification`, the app shows the
verification card: send verification photo (normal composer) + close the
session as Behoben/Eskaliert/Nicht behoben → `POST /outcome` (2.1). This
closes the Data-Bridge loop from the phone; without it the field data the
Mission depends on never gets its outcome label.

### D9: API base URL — derived in dev, configured in builds

Dev (Expo Go): API host = Metro host (`Constants.expoConfig.hostUri`) on
:8000 — zero config, same-LAN, the 1.4 pattern. Builds: `extra.apiUrl` in
`app.json` (no Metro host exists in an APK). `extra.tenantId` → `X-Tenant-Id`
header per pilot build (2.5 D6). `usesCleartextTraffic` enabled for LAN
field tests — removed with the HTTPS deploy (3.1).

### D10: Session list is phone-local

`AsyncStorage` list (id, createdAt, label = first symptom text, status).
No backend list endpoint exists and pilots are single-device — the phone
knows its own sessions. Long-press removes locally (server data untouched).
A backend session index is a 3.x concern (multi-device).

---

## Acceptance (Roadmap) — status

- Capture photo → upload → turn → SSE events → answer question → diagnosis →
  verification photo → export shows trace: **flow implemented**; dev-verified
  at the contract level (live smoke: real backend events through the app
  reducer). On-phone run via Expo Go + APK on rugged device = field runbook
  (FINDINGS) — same split as 1.4 (built, then user field test).
- Installable APK: build paths documented (BUILD.md); requires EAS account or
  local Android SDK — neither exists on this machine (user step).

---

*Feature 2.6 · Stand: 19. Juli 2026*
