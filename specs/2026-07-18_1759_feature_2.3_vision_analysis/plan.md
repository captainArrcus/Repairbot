# Feature 2.3 — Plan

1. `pyproject.toml`: add `pytesseract`; `uv sync`. CI: apt-get tesseract-ocr.
2. `app/config.py`: `GOOGLE_API_KEY`, `VISION_MODEL` (default
   `gemini/gemini-2.5-flash`)
3. `app/services/storage.py`: `get_object(media_key) -> (bytes, content_type)`,
   `put_object(key, data, content_type)`
4. `app/tools/vision_analysis.py`
   - `analyze(media_key) -> dict` (S3 shell) over pure
     `_analyze_bytes(data, content_type)`
   - `_preprocess` (EXIF → grayscale → autocontrast → upscale → OSD rotate),
     `_classify` (keyword heuristic → lazy-litellm fallback),
     `_annotate_codes` (boxes → PNG bytes; Phase 4.2 reuse point)
5. `app/services/agent_service.py`: `_vision_step` per image media_key
   (cap 3), tool events, detected codes → `_candidate_codes`
6. Tests
   - `tests/vision/test_vision_expectations.py`: synthetic seed panels,
     ≥ 80% controller accuracy, code extraction, annotation boxes, non-image
     rejection, LLM-fallback wiring (patched), MinIO round-trip (skip-gated)
   - `tests/test_sessions.py`: photo-turn flow test (DB+MinIO+tesseract gated)
7. Verify: `uv run pytest`, `uv run ruff check/format`, live uvicorn + curl
   (upload rendered panel via presign → turn → SSE shows vision events)
8. FINDINGS.md; Roadmap 2.3 → DONE; Techstack untouched (already lists the
   tool + model plan) unless deviations surface
