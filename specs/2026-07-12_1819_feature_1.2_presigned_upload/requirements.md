# Feature 1.2 — Presigned upload endpoint: Requirements

> **One sentence:** `POST /api/v1/media/upload-url` returns a presigned S3 PUT URL +
> `media_key` so clients upload media directly to object storage — the only media path
> (Techstack: no base64 in request bodies).

---

## Context

Feature 1.4 (web prototype) and 2.6 (mobile app) upload photos/audio before posting a turn
that references `media_key`. Feature 2.3 (vision) and 2.4 (STT) later fetch by `media_key`.
Dev S3 is the Feature 1.0 MinIO; prod is cloud S3 (same boto3 code path).

## Scope (from Roadmap Feature 1.2)

1. `app/services/storage.py` — `generate_presigned_put(media_key, content_type)`
2. `app/api/media.py` — `create_presigned_upload()`, router mounted in `app/main.py`
3. `tests/test_media.py`

Out of scope: media metadata table (nothing needs it yet), tenant prefixes (no tenant
context in the API until Feature 2.5), download URLs (tools read S3 server-side).

## Decisions

### D1: Content-Type is part of the signature — acceptance curl needs the header

`ContentType` is included in the presign params, so the stored object's MIME is
trustworthy for the later vision/STT/multimodal calls. Consequence: the client PUT must
send the same `Content-Type` header, else S3 refuses (MinIO 400 / AWS 403). Roadmap
acceptance command corrected (mirrored):

    curl -T panel.jpg -H "Content-Type: image/jpeg" "<upload_url>"

### D2: object key == media_key == bare uuid4

Retrieval invariant for Features 2.3/2.4: fetch by `media_key` verbatim, no mapping table.
Tenant prefix moves *into* the media_key when auth introduces tenant context (Feature 2.5)
— the invariant survives. `filename`/`purpose` are accepted per the API contract but not
persisted; revisit when a media table exists.

### D3: content_type allowlisted to `image/*` and `audio/*`

Trust boundary: Pydantic pattern `^(image|audio)/[\w.+-]+$`, 422 otherwise. Matches the
only media types the product ingests (photos, voice).

### D4: presigned URL host = `S3_ENDPOINT_URL`

Dev URLs point at `http://localhost:9000` — fine for laptop curl. **Feature 1.4 (phone on
LAN) must set `S3_ENDPOINT_URL` to the LAN IP of the dev machine**, else the phone can't
reach MinIO. No second "public endpoint" config until that day comes.

---

## Acceptance (Roadmap, curl corrected per D1)

- `curl -X POST http://localhost:8000/api/v1/media/upload-url -H 'Content-Type: application/json' -d '{"filename":"a.jpg","content_type":"image/jpeg"}'` → `{upload_url, media_key}`
- `curl -T panel.jpg -H "Content-Type: image/jpeg" "<upload_url>"` → 200, object GET-able in storage
- `uv run pytest` green (round-trip test skips without MinIO), ruff clean

---

*Feature 1.2 · Stand: 12. Juli 2026*
