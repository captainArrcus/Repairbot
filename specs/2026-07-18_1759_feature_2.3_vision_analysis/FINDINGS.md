# Feature 2.3 — VisionAnalysisTool: Findings / Acceptance

**Status: COMPLETE (dev-verified, 2026-07-18). `app/tools/vision_analysis.py`
analyzes uploaded photos (OCR-first, LiteLLM-multimodal fallback); the
Wizard-of-Oz agent streams `vision_analysis` tool events and feeds detected
codes into the 2.2 fast path.**

## Acceptance evidence

| Check | Result |
|---|---|
| `uv run pytest -q` | **39 passed** (31 existing + 8 new in tests/vision/) |
| `uv run ruff check` + `format --check` (CI scope) | clean |
| Controller detection on seed set (Roadmap: ≥ 80%) | **6/6 = 100%** (synthetic renders, spec D8; LLM fallback off) |
| Live phone flow (uvicorn + presign PUT of rendered panel → turn) | thinking → `vision_analysis` tool_call/result (`controller: SINUMERIK, codes: 309`) → `error_code_lookup` exact match AL 309 → 4 cause hypotheses → tactile question → done |
| SSE stream | typed frames, monotonic wire ids (`1.0`, `1.1`, …) |
| Annotated image | `{media_key}.annotated.png` in MinIO, image/png, red boxes on code words |
| Live LLM fallback (brandless panel, real Gemini 2.5 Flash call) | answered in ~10 s, conf 0.6 — wiring works end-to-end |

## Findings

- **Tesseract OSD is useless on panel crops** — bails with "Too few
  characters". Word *count* can't pick the right rotation either (sideways
  text OCRs into equally many garbage words). Confidence-filtered word count
  (conf ≥ 60) separates cleanly (3 vs 8 on the rotated seed panel) → coarse
  rotation = best-of-four OCR passes, only paid when the upright pass reads
  < 5 confident words (spec D2 updated).
- **Gemini guesses rather than saying UNKNOWN**: the live fallback on a
  deliberately brandless synthetic panel returned SINUMERIK (plausible from
  German alarm text, not verifiable from the image). conf 0.6 carries the
  uncertainty; the 2.5 agent must treat LLM-classified brands as a hint, not
  a fact.
- **detected_codes contains model-number noise**: bezel text like "iTNC 530"
  yields "530". Harmless today (lookup simply misses; the agent asks on),
  and candidate-relevance judgment is 2.5's job — not filtered in the tool.
- **FANUC-style prefixed codes (SV0401) are not extracted** — 2.2's
  `extract_codes` knows AL/F/bare-digit formats (the seeded SINUMERIK corpus).
  Extend when non-SINUMERIK code DBs are seeded (Feature 4.1 knowledge packs).

## Notes for later features

- **2.4 (STT):** audio media_keys currently produce a failure-summary
  `vision_analysis` tool_result ("not an image"). Route by content type in
  the turn handler when audio lands.
- **2.5 (hermes):** register `analyze(media_key)` as the `vision_analysis`
  hermes tool. The keyword/LLM confidence ladder (0.9/0.6) is stub stand-in.
- **4.2 (guidance overlays):** reuse `_annotate_codes`'s draw→PNG→S3 path;
  swap the box source, keep the shipping.
- **Runbooks:** real field photos from the 1.4 field test should be run
  through `tests/vision/` expectations once they exist (spec D8);
  `tesseract-ocr-deu` install if German panel prose ever matters for OCR.

## Deviations from Roadmap (ratified in requirements.md)

- Preprocessing is Pillow-only; content autocrop + fine-angle deskew deferred
  until real field photos show the need (D2 — no OpenCV dependency).
- OCR keyword heuristic classifies first; the Roadmap's "small LiteLLM
  multimodal call" fires only when OCR sees no brand (D3).
- `detected_controller` is brand-level (SINUMERIK/HEIDENHAIN/FANUC), exactly
  what the Roadmap asks to classify; exact-family mapping remains the open
  family-normalization issue (2.2 D2). Not persisted to the session (D7).
- Seed images are synthetic Pillow renders — no real panel photos exist
  anywhere in the repo (D8).

---

*Feature 2.3 · Stand: 18. Juli 2026*
