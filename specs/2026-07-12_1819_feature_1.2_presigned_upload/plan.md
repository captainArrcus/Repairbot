# Feature 1.2 — Plan

1. `app/services/storage.py` — module-level boto3 client (s3v4 + path-style for MinIO),
   `generate_presigned_put(media_key, content_type)`, 900 s expiry.
2. `app/api/media.py` — Pydantic request (content_type allowlist) / response models,
   `create_presigned_upload()`; mount router in `app/main.py`.
3. `tests/test_media.py` — response shape, 422 on bad content_type (always run: presigning
   is local crypto), PUT round-trip + signature-mismatch refusal (skip without MinIO).
4. Verify roadmap acceptance live (uvicorn + curl + storage GET), fix Roadmap curl (D1),
   mark 1.2 DONE.
