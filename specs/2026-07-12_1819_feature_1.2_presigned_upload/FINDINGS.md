# Feature 1.2 — Presigned upload endpoint: Findings / Acceptance

**Status: COMPLETE — all acceptance criteria pass (2026-07-12).**

## Acceptance evidence

| Check | Result |
|---|---|
| `POST /api/v1/media/upload-url` (curl, live uvicorn) | `{upload_url, media_key}`, key `be05a521-…` |
| `curl -T panel.jpg -H "Content-Type: image/jpeg" "<upload_url>"` | HTTP 200 |
| Storage GET (`get_object` on media_key) | 9 bytes, `ContentType: image/jpeg` |
| PUT without matching Content-Type header | refused (MinIO 400; AWS would be 403) |
| `uv run pytest` | 7 passed (health + 3 schema + 3 media) |
| `uv run ruff check app tests` + `ruff format --check` | clean |

## Notes for later features

- **Feature 1.4 (web prototype):** presigned URL host comes from `S3_ENDPOINT_URL`
  (dev: `http://localhost:9000`). Phone on LAN → set `S3_ENDPOINT_URL` to the dev
  machine's LAN IP before generating URLs. Client PUT **must** send
  `Content-Type` equal to the one requested (it's signed — D1).
- **Features 2.3/2.4 (vision/STT):** fetch by `media_key` verbatim — object key ==
  media_key (D2). Stored MIME is trustworthy (signed).
- **Feature 2.5 (tenancy):** tenant prefix goes *into* the media_key at mint time;
  no other change needed.
- `filename`/`purpose` are accepted but not persisted (no media table yet — D2).

## Deviations from Roadmap (ratified in requirements.md D1)

- Acceptance `curl -T` gained `-H "Content-Type: image/jpeg"` — the header is part of
  the presigned signature. Roadmap command corrected.

---

*Feature 1.2 · Stand: 12. Juli 2026*
