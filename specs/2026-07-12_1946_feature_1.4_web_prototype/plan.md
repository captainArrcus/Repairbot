# Feature 1.4 — Plan

## Files

| File | Content |
|---|---|
| `RepairRöpiApp/web_prototype/index.html` | single page: start button, status, hypothesis panel, question card, log, composer (camera + text + send) |
| `RepairRöpiApp/web_prototype/app.js` | session create → EventSource; photo → presigned PUT → media_key; POST turn (idempotency_key = crypto.randomUUID()); per-event-type render (D6) |
| `Repair_Logic_Agent/app/main.py` | + CORSMiddleware allow-all dev (D3) |

## Order

1. Spec (this) → index.html + app.js → main.py CORS
2. Verify: dev stack + uvicorn; curl-simulated JS flow with Origin header
   (CORS headers present on POSTs + SSE); `node --check app.js`
3. FINDINGS.md + mirror into Roadmap.md (mark 1.4 DONE, path
   `RepairRöpiApp/web_prototype/`, CORS + `S3_ENDPOINT_URL` LAN note)

## Field test (user, phone)

`S3_ENDPOINT_URL=http://<lan-ip>:9000` in `.env` → restart uvicorn →
`python -m http.server 8080` in web_prototype → phone: `http://<lan-ip>:8080` →
Start → photo + "AL 309 …" → events render, question asks for evidence.

---

*Feature 1.4 · Stand: 12. Juli 2026*
