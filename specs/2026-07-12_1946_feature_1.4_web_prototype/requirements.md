# Feature 1.4 — Dirty web prototype: Requirements

> **One sentence:** Single-page phone web UI (photo → presigned PUT → turn → SSE render)
> against the Feature 1.3 API — the "Wizard of Oz" front end for the FIRST FIELD TEST.

---

## Context

Phase 1 goal: smartphone in front of a machine. UI stays dirty (Roadmap: single
`index.html` + `app.js`, static server, no framework, no build). The real app is
Feature 2.6; this prototype only has to prove the loop end-to-end on a phone.

## Scope (from Roadmap Feature 1.4)

1. `RepairRöpiApp/web_prototype/index.html` — single page
2. `RepairRöpiApp/web_prototype/app.js` — session create, camera capture, presigned
   upload, POST turn, EventSource, event rendering
3. Backend: CORS middleware (the one backend change this feature forces — see D3)

Out of scope: audio capture (→ 2.4/2.6), auth/tenancy (→ 2.5), offline caching
(→ 2.6), any styling beyond phone-usable.

## Decisions

### D1: Location `RepairRöpiApp/web_prototype/`

Roadmap writes `repairropi_app/web_prototype/`; the actual frontend directory is
`RepairRöpiApp/` (Mission two-repo table). Same repo discipline, real name.

### D2: Vanilla JS, no framework, no build step

`fetch` + `EventSource` cover the whole contract. EventSource auto-reconnects and
re-sends `Last-Event-ID` natively — the 1.3 resume design (persist-then-stream,
wire id `turn_index.event_index`) makes reconnect free on the client.
One stream per session, opened once (1.3 FINDINGS note).

### D3: Backend gets CORSMiddleware, allow-all (dev)

Page is served from `:8080` (python -m http.server), API on `:8000` → every fetch
and the EventSource are cross-origin. FastAPI ships CORSMiddleware; allow-all
origins/methods/headers, no credentials. Tighten when auth lands (Feature 2.5) /
prod deploy (3.1). MinIO's S3 API allows all origins by default, so the presigned
PUT from the browser needs no infra change.

### D4: API base = `http://${location.hostname}:8000`

Phone loads the page from the laptop's LAN IP, so the same hostname reaches the
API. No config file, no hardcoded IP.

### D5: Field-test env: `S3_ENDPOINT_URL` must be the LAN IP

The presigned URL embeds the S3 endpoint the *backend* was configured with;
default `http://localhost:9000` is unreachable from the phone. Before a field
test: `S3_ENDPOINT_URL=http://<laptop-lan-ip>:9000` in `.env`, restart uvicorn.
(Config already env-driven — no code change.)

### D6: Event rendering (stub emits: thinking, tool_call, tool_result, hypothesis, question, done)

- `thinking` → status line
- `hypothesis` → panel upserted by `hypothesis_id`: description + confidence bar,
  `eliminated` → struck through
- `question` → question card; primary CTA by `evidence_type`: `photo` → camera
  button highlighted, else text input focused; `required_format` shown as hint
- `tool_call` / `tool_result` → one log line each
- `done` → composer re-enabled, status from `status` field
- anything else (`diagnosis`, `guidance` — Feature 2.5) → generic log line, no
  special rendering until a feature needs it

### D7: German UI labels

Stub speaks German, field test is German technicians (Mission persona).

### D8: Plain HTTP is fine on the phone

`<input type="file" capture>` is not getUserMedia — no secure context required.
No HTTPS/cert dance for the field test.

---

## Acceptance (Roadmap — FIRST FIELD TEST)

- `python -m http.server 8080` in `RepairRöpiApp/web_prototype/`, open on phone
  (same LAN), start session, take photo of control, send → streamed events render
  (thinking, hypotheses, question with CTA).
- Dev verification without a phone: curl-simulated JS flow (session → upload-url →
  PUT → turn → stream) with an `Origin` header proving CORS, `node --check app.js`.

---

*Feature 1.4 · Stand: 12. Juli 2026*
