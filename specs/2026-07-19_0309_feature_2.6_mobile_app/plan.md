# Feature 2.6 — Plan

1. Scaffold: `create-expo-app` blank-typescript at `RepairRöpiApp/mobile/`
   (SDK 57); deps via `expo install`: image-picker, audio, crypto, constants,
   build-properties, async-storage; `react-native-sse` via npm (D1)
2. `services/events.ts` — pure reducer over the canonical SSE events:
   monotonic wire-id filter (D4), hypothesis/guidance upserts, question/
   diagnosis/done transitions, user-log interleave keys (D3)
   + `services/events.test.ts` (`node --test`, type stripping — no jest)
3. `services/api.ts` — base-URL resolution (D9), createSession/sendTurn/
   recordOutcome/uploadMedia (presign + blob PUT), `openStream` wrapping
   react-native-sse with reconnect disabled (D4)
4. `services/store.ts` — AsyncStorage: session list (D10), per-session user
   log, pending turn with per-media mediaKey write-back (D5)
5. Screens: `SessionListScreen` (list + new + long-press remove),
   `SessionScreen` (stream lifecycle w/ 3s reconnect + 404 handling, attempt/
   retry loop, camera/recorder/composer, hypothesis panel, guidance +
   high-safety confirm (D7), verification/outcome card (D8));
   `components/HypothesisList.tsx`, `components/theme.ts`; `App.tsx`
   conditional render (D2)
6. `app.json`: name/slug/package, dark UI, permission strings (de),
   cleartext build property, `extra.apiUrl`/`extra.tenantId` (D9)
7. Verify: `npm run typecheck`, `npm test`, `expo export --platform android`
   (Metro compile), live contract smoke — real scripted-backend session's SSE
   replay fed through the real reducer (scratchpad script)
8. `BUILD.md` (Expo Go loop, both APK paths); FINDINGS.md; Roadmap 2.6
   as-built + status; Techstack: frontend lock (D1), checklist tick,
   `GET /sessions/{id}` annotation (D3)
