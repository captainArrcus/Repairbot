# Feature 2.9 — Plan

## Files

| File | Content |
|---|---|
| `RepairRöpiApp/mobile/services/events.ts` | `LogEntry` gains `kind` + `photoUri`/`audioDurationMs` (D2); `UserLogEntry` gains the media fields (D1); `userEntry`/`applyUserEntries` carry them through; agent log lines marked `kind: "agent"` |
| `RepairRöpiApp/mobile/services/store.ts` | `PendingMedia` gains `durationMs` (audio, D4) — storage shape only |
| `RepairRöpiApp/mobile/screens/SessionScreen.tsx` | Composer: Image thumbnail on capture (D3); attempt(): build UserLogEntry with photoUri + audioDurationMs from the pending media; log section → conversation renderer (user bubble right / agent line left); bubble Image with onError fallback |
| `RepairRöpiApp/mobile/services/events.test.ts` | Reducer test: user entry with media survives applyUserEntries and sorts before the answering agent turn |

## Order

1. events.ts + store.ts type/reducer changes
2. SessionScreen composer thumbnail + bubble rendering
3. Tests (`node --test`), `tsc --noEmit`
4. Live acceptance: Expo Go on phone — take photo → thumbnail before send →
   send → user bubble with photo + text, agent output visibly distinct
   (scripted backend suffices, Roadmap 2.9)
5. FINDINGS.md + mark 2.9 DONE in Roadmap.md

## Test flow

```
cd RepairRöpiApp/mobile
npx tsc --noEmit
node --test --experimental-strip-types services/events.test.ts
# field: npx expo start → phone → photo → thumbnail → send → bubble
```

---

*Feature 2.9 · Stand: 2026-07-20*
