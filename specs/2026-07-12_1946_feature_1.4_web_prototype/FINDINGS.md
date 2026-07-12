# Feature 1.4 — Dirty web prototype: Findings / Acceptance

**Status: COMPLETE (dev-verified, 2026-07-12). The literal acceptance — phone in
front of a machine — is a user action; everything the phone will do has been
verified end-to-end via a browser-identical curl flow.**

## Acceptance evidence (live uvicorn + MinIO + Postgres, dev stack)

Simulated exactly what `app.js` does, `Origin: http://192.168.0.42:8080` on every call:

| Step (what app.js does) | Result |
|---|---|
| `POST /api/v1/sessions` | `{session_id}`, `access-control-allow-origin: *` |
| `POST /api/v1/media/upload-url` | `{upload_url, media_key}` |
| Browser preflight `OPTIONS` on presigned URL (MinIO) | 204 — MinIO allows all origins by default, no infra change |
| `PUT` photo with signed `Content-Type: image/jpeg` | 200 |
| `POST /turns` ("… AL 309, Rattern … X-Achse", media_key) | `{turn_id}` |
| `curl -N …/stream` with Origin | 9 SSE frames (`thinking, tool_call, tool_result, 4× hypothesis, question, done`), CORS header on the stream response |
| `python -m http.server 8080` serves `index.html` + `app.js` | 200/200 |
| `node --check app.js` | clean |
| `uv run ruff check` + `format --check` | clean |
| `uv run pytest -q` | **12 passed** — also closes the pending re-run flagged in the 1.3 FINDINGS |

## Field-test runbook (user, phone on same LAN)

1. `.env` in `Repair_Logic_Agent/`: `S3_ENDPOINT_URL=http://<laptop-lan-ip>:9000`
   (presigned URLs embed the backend's S3 endpoint — `localhost` is unreachable
   from the phone; spec D5). Restart uvicorn with `--host 0.0.0.0`.
2. `cd RepairRöpiApp/web_prototype && python -m http.server 8080`
3. Phone browser → `http://<laptop-lan-ip>:8080` → "Session starten" → photo of
   the control + symptom text → events render, question card shows CTA.

## Notes for later features

- **Feature 2.3 (vision):** photos land in MinIO under `media_key` and the turn
  carries `media_keys` — the stub ignores them today, vision consumes them.
- **Feature 2.5:** `diagnosis`/`guidance` events render as generic log lines in the
  prototype (D6) — give them real cards in the mobile app (2.6), not here.
- **Feature 2.6 (mobile):** the SSE client pattern (one EventSource per session,
  native Last-Event-ID resume) transfers 1:1; RN needs an SSE polyfill with the
  same semantics.
- CORS is allow-all for the field test — tighten with auth (2.5) / deploy (3.1).

## Deviations from Roadmap (ratified in requirements.md, Roadmap corrected)

- Path is `RepairRöpiApp/web_prototype/` (real repo dir), not `repairropi_app/…` (D1).
- Backend touched once: CORSMiddleware in `app/main.py` — Roadmap 1.4 listed no
  backend change, but cross-origin (page :8080 → API :8000) makes it mandatory (D3).

---

*Feature 1.4 · Stand: 12. Juli 2026*
