# Feature 2.6 — FINDINGS

## Verified (2026-07-19, this machine)

- `npm run typecheck` — clean (TS strict).
- `npm test` — 5/5 reducer tests (upsert/elimination, monotonic filter,
  question→diagnosis→done flow, guidance ordering, user-turn interleave +
  restore idempotence).
- `npx expo export --platform android` — Metro bundles 615 modules → Hermes
  bytecode, no errors (compile-level proof without an Android SDK).
- **Live contract smoke** (scratchpad `smoke.mjs`, scripted backend):
  created session, posted AL-309 turn, fresh-connect stream replayed
  `thinking→tool_call→tool_result→4×hypothesis→question→done@1.8`; fed
  through the real `events.ts` reducer → 4 hypotheses, question set,
  `awaiting_user_input`, busy cleared. Reconnect with `Last-Event-ID: 1.8`
  replayed nothing; re-reducing the full replay was a no-op. D3/D4 hold
  against the real wire format.

## Findings

1. **Fresh SSE connect replays the entire session** (server cursor (-1,-1)) —
   this made `GET /sessions/{id}` unnecessary for the app and turned "session
   restore" into "connect + reduce". The Techstack endpoint list was ahead of
   the implementation; annotated instead of built.
2. **SDK 57 scaffold ships an AGENTS.md pointing at versioned docs** — the
   expo-audio recording API (useAudioRecorder/useAudioRecorderState/
   AudioModule permissions) and image-picker/constants were verified against
   `docs.expo.dev/versions/v57.0.0` before finalizing. expo-av is gone; 
   expo-audio metering delivers the ambient-noise indicator directly.
3. **`expo install` auto-registered its config plugins** in app.json
   (expo-audio, expo-build-properties) — only image-picker + permission
   strings needed manual entry.
4. **Node ≥23 type stripping** runs the TS reducer tests with zero test
   framework (`node --test services/events.test.ts`). The test file is
   excluded in tsconfig (node types vs RN types collide); tsc still covers
   every shipped file.
5. **EAS archives from the git root, not the app dir** — the first build
   swept the whole monorepo and died with EACCES on docker-created root-owned
   dirs (`Repair_Logic_Agent/agents/.hermes_home/…/audio_cache`); it would
   also have uploaded backend + tenant data to Expo's build servers.
   Root-level `.easignore` (allowlist: only `RepairRöpiApp/mobile`, minus
   node_modules/.expo) fixes crash, size and data-hygiene in one.
6. **expo/fetch (global default since SDK 56) is broken on-device for this
   app** — first APK run failed every request with `NativeRequest.start …
   cannot be cast to NativeRequestInit` despite a valid RequestInit (verified
   against the installed Kotlin record: all-string headers, valid enums).
   Same failure class as expo#39896/#45909. Fix: official opt-out
   `EXPO_PUBLIC_USE_RN_FETCH=1` in `mobile/.env` (tracked → ships in the EAS
   archive; Metro inlines it in dev and cloud builds — verified in export
   log). RN's XHR-based fetch is the same stack the 1.4 prototype field-
   proved. Revisit when upstream fixes expo/fetch.
7. **react-native-sse events carry `lastEventId`** per message; lib
   auto-reconnect is disabled in favor of screen-owned reconnect with the
   reducer's `lastEventId` (D4) — the lib would reconnect without resume
   state, which the monotonic filter tolerates but the fresh header avoids.

## Open items (field runbook — user steps)

1. **Expo Go run on the phone** (same LAN): `npx expo start` + backend with
   `S3_ENDPOINT_URL=http://<lan-ip>:9000`, uvicorn on 0.0.0.0 (BUILD.md).
   Expected to mirror the 1.4 field test; audio turn additionally exercises
   STT end-to-end from the app.
2. **APK build — DONE 2026-07-19 (EAS cloud, preview profile).** projectId
   `07eafe19-…` + `extra.apiUrl` (laptop LAN IP; hostUri still wins in Expo
   Go) baked into app.json, `eas.json` created, keystore on Expo servers.
   Install link/QR (build 2 — with the RN-fetch fix, finding #6):
   https://expo.dev/accounts/arrcuss-team/projects/repairropi/builds/0fff0953-178d-40e2-8a23-f5423b673d67
   Rebuild: `npx eas-cli build -p android --profile preview` (BUILD.md).
   Remaining acceptance step: install on the rugged device, run the
   end-to-end diagnostic flow against the LAN backend.
3. **High-safety confirm CTA live** — implemented against the 2.5 contract
   (scripted backend's stream has no high-safety guidance); verify once a
   hermes session emits one (AGENT_BACKEND=hermes dev run).
4. `usesCleartextTraffic` removal + real `extra.apiUrl` → Feature 3.1 deploy.

## Delta vs. Roadmap text

- Files are `.tsx`/`.ts` (TS strict), not the `.js` names the Roadmap
  sketched; paths as named otherwise (`screens/SessionScreen.tsx`,
  `components/HypothesisList.tsx`, `services/api.ts`).
- Added beyond the sketch: outcome UI (D8 — Data-Bridge closure from the
  phone), high-safety confirm CTA (D7 — 2.5 contract surface), phone-local
  session list (D10).
