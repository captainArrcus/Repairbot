# Feature 2.3 — VisionAnalysisTool: Requirements

> **One sentence:** `app/tools/vision_analysis.py` turns an uploaded photo
> (media_key) into `detected_controller` + `detected_codes[]` + an annotated
> image in S3 — OCR-first, LiteLLM-multimodal fallback — and the Wizard-of-Oz
> agent streams `tool_call`/`tool_result` events whenever a turn carries media.

---

## Context

The pipeline is the Roadmap one: fetch from S3 → preprocess → pytesseract OCR
→ extract error-code-like strings → classify the control panel (Siemens /
Heidenhain / Fanuc) → return annotated images. Detected codes feed straight
into the Feature 2.2 fast path (`ErrorCodeLookup` normalizes OCR-ish variants
— 2.2 FINDINGS forward pointer). `annotated_images[]` is the seed of the
Phase 4.2/4.3 visual-grounding track, so the draw→S3 path stays a separate,
reusable function.

## Scope (from Roadmap Feature 2.3)

1. `app/tools/vision_analysis.py` — `def analyze(media_key: str) -> dict`
2. `app/services/storage.py` — gains `get_object` / `put_object`
3. `app/services/agent_service.py` — photo in turn → vision tool call,
   `tool_call`/`tool_result` streamed, detected codes join the lookup path
4. `tests/vision/test_vision_expectations.py` (+ flow test in
   `tests/test_sessions.py`); CI installs the tesseract binary

Out of scope: guidance overlays on request ("mark the coolant valve" → 4.2),
schematic grounding (4.3), audio (2.4), hermes registration of the tool (2.5).

## Decisions

### D1: OCR = pytesseract + system tesseract; eng traineddata suffices for now

Tesseract 5 is on the dev box; CI gets `apt-get install tesseract-ocr` (one
line). Error codes and brand names are digits/Latin — the seeded panels OCR
fine with `eng`. German panel prose (umlauts) degrades gracefully; installing
`tesseract-ocr-deu` is a runbook note, not a dependency. Tests skip when the
binary is missing (same pattern as `needs_db`). No cloud OCR — the Roadmap
allows it "if needed"; it is not needed yet.

### D2: Preprocessing is Pillow-only; autocrop + fine-angle deskew deferred

EXIF transpose (phone photos carry orientation), grayscale, autocontrast,
2× upscale below 1200 px, coarse 90°-step rotation. Rotation is brute force —
OCR upright, and only if fewer than 5 *confident* words (conf ≥ 60) come back,
try the three 90° rotations and keep the best. Tesseract OSD was tried first
and bails on panel crops ("Too few characters"); word *count* alone can't
discriminate either, because sideways text yields equally many garbage words
— confidence separates cleanly (3 vs 8 on the rotated seed panel). Roadmap
names "autocrop" and "deskew": content-aware autocrop and sub-degree deskew
need OpenCV and real field photos to tune against; neither exists yet.
Deferred with a `ponytail:` ceiling comment — revisit when field photos from
the 1.4 runbook show OCR failures the current chain can't handle.

### D3: Controller classification = OCR keyword heuristic first, LLM fallback

Brand keywords in the OCR text decide first (SINUMERIK/SIEMENS → `SINUMERIK`,
HEIDENHAIN/TNC → `HEIDENHAIN`, FANUC → `FANUC`) — free, deterministic, and on
panel photos the brand is printed on the bezel. Only when OCR sees no brand
does the Roadmap's "small LiteLLM multimodal call" fire: `gemini/gemini-2.5-flash`
(Techstack model plan) via direct `litellm.completion` (same invocation as the
knowledge spikes — no proxy server in dev; the proxy endpoint arrives with 2.5),
one-word forced answer, temperature 0. No `GOOGLE_API_KEY` or LLM error →
vision degrades to OCR-only, never raises. `litellm` is imported lazily —
importing it costs seconds and only the fallback path pays.

`detected_controller` is **brand-level** (`SINUMERIK`/`HEIDENHAIN`/`FANUC`/
`None`) — exactly what the Roadmap asks to classify. Mapping to exact families
(`SINUMERIK_840D_sl`) is the still-open family-normalization issue (2.2 D2).

Confidence ladder (fabricated, dies with the stub in 2.5): keyword hit 0.9,
LLM answer 0.6, neither 0.0. The returned top-level `confidence` is the
controller-classification confidence.

### D4: Code extraction reuses `ErrorCodeLookup.extract_codes`

Run over the OCR text. Downstream lookup already normalizes OCR-ish variants
(`AL309`, `f07011`) — no second regex, no new normalization.

### D5: Annotation = red boxes on code-like OCR words → PNG → S3

Word boxes from `image_to_data` matching a code-ish pattern get red
rectangles; the drawn PNG goes to S3 as `{media_key}.annotated.png`
(content-type image/png, same bucket — an agent-generated asset, not an
upload, so the presign/media_key invariant is untouched). No code-like words →
no upload, `annotated_images: []`. Drawing lives in its own function
(`boxes → PNG bytes`) so Phase 4.2 swaps the box source, not the path.

### D6: Return shape

```python
{
  "detected_controller": "SINUMERIK" | "HEIDENHAIN" | "FANUC" | None,
  "detected_codes": [str, ...],      # as extracted; lookup normalizes
  "annotated_images": [str, ...],    # S3 keys, [] if nothing annotated
  "confidence": float,               # controller-classification confidence
  "ocr_text": str,                   # full OCR text — the 2.5 agent will want it
}
```

`analyze(media_key)` raises `ValueError` for non-image content types (stored
MIME is trustworthy — presign signs it, 1.2). Internals split as pure
`_analyze_bytes(data, content_type)` + S3 shell, so tests run without MinIO.

### D7: Stub integration — events yes, session controller write no

`_scripted_diagnosis` gains the media step: each image-typed media_key
(capped at 3/turn) produces one `tool_call`/`tool_result` pair
(`tool: "vision_analysis"`); failures (missing object, audio key, S3 down)
become a failure-summary `tool_result`, never a 500. Detected codes are
appended to the candidate codes ahead of `error_code_lookup` — a photo of a
panel showing AL 309 walks the same fast path as typed "AL 309".

The vision brand is **not** written to `diagnostic_sessions.controller_family`:
it is coarser than a user-provided family and first-sighting-wins (COALESCE)
would lock the coarse value in. The 2.5 agent decides what to do with it.

### D8: Seed images are synthetic renders; ≥ 80% measured over that set

No field photos exist anywhere in the repo (checked — Feature 0.0's images/
folder never materialized). Seed images = Pillow-rendered control panels
(brand header + alarm line, 6 labeled cases incl. a rotated one) generated at
test time: deterministic, offline, no binaries in git.
`tests/vision/test_vision_expectations.py` asserts controller detection
≥ 80% over the set (Roadmap acceptance). The LLM fallback is monkeypatched
off in unit tests (offline determinism); real-photo validation is a runbook
item once the 1.4 field test produces photos.

---

## Acceptance (Roadmap)

- Controller family detected correctly on ≥ 80% of seed images, measured by
  `tests/vision/test_vision_expectations.py`.
- Photo turn → agent streams `vision_analysis` `tool_call`/`tool_result`; a
  panel photo showing a seeded code yields the same hypotheses as typing it.
- Annotated image lands in S3 under `{media_key}.annotated.png`.

---

*Feature 2.3 · Stand: 18. Juli 2026*
