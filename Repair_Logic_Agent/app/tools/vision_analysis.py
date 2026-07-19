"""Feature 2.3 — VisionAnalysisTool.

Roadmap pipeline: fetch image from S3 → preprocess (Pillow) → pytesseract OCR
→ extract error-code-like strings → classify the control panel (OCR keyword
heuristic; LiteLLM multimodal fallback) → red boxes around detected codes,
annotation uploaded to S3 (seed of the Phase 4.2 visual-grounding track).

detected_controller is brand-level (SINUMERIK / HEIDENHAIN / FANUC) — the
error_code_lookup FAMILY_ALIASES map (2.8) canonicalizes it to seeded families.
"""

import base64
import io
import re

import pytesseract
from PIL import Image, ImageDraw, ImageOps

from app import config
from app.services import storage
from app.tools.error_code_lookup import ErrorCodeLookup

# brand markings printed on the bezel/screen of each controller family
_BRANDS = [
    ("SINUMERIK", re.compile(r"sinumerik|siemens", re.I)),
    ("HEIDENHAIN", re.compile(r"heidenhain|\bi?tnc\b", re.I)),
    ("FANUC", re.compile(r"fanuc", re.I)),
]

# ponytail: fabricated confidence ladder (keyword > LLM > nothing);
# real confidences come from the agent (Feature 2.5)
_CONF_KEYWORD = 0.9
_CONF_LLM = 0.6

# word-level box filter for annotation: bare or prefixed alarm numbers
_CODEISH_RE = re.compile(r"^(?:AL|F|SV|PS|EX)?-?\d{3,6}[.,:;]?$", re.I)

_LLM_PROMPT = (
    "This is a photo of a CNC machine control panel. Which controller brand "
    "is it: SINUMERIK (Siemens), HEIDENHAIN, or FANUC? "
    "Answer with exactly one word: SINUMERIK, HEIDENHAIN, FANUC, or UNKNOWN."
)


def analyze(media_key: str) -> dict:
    """Fetch + analyze an uploaded photo; upload the annotated image if any
    code-like text was found. Raises ValueError for non-image objects."""
    data, content_type = storage.get_object(media_key)
    if not content_type.startswith("image/"):
        raise ValueError(f"{media_key} is not an image ({content_type or 'unknown type'})")
    result, annotated_png = _analyze_bytes(data, content_type)
    if annotated_png is not None:
        key = f"{media_key}.annotated.png"
        storage.put_object(key, annotated_png, "image/png")
        result["annotated_images"] = [key]
    return result


def _analyze_bytes(data: bytes, content_type: str) -> tuple[dict, bytes | None]:
    """Pure pipeline (no S3): returns (result dict, annotated PNG or None)."""
    img = _preprocess(Image.open(io.BytesIO(data)))
    img, ocr = _ocr_best_rotation(img)
    text = " ".join(word for word in ocr["text"] if word.strip())
    controller, confidence = _classify(text, data, content_type)
    result = {
        "detected_controller": controller,
        "detected_codes": ErrorCodeLookup.extract_codes(text),
        "annotated_images": [],
        "confidence": confidence,
        "ocr_text": text,
    }
    return result, _annotate_codes(img, ocr)


def _preprocess(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)  # phone photos carry orientation in EXIF
    img = ImageOps.autocontrast(img.convert("L"))
    if max(img.size) < 1200:  # small crops: tesseract wants ~30px glyphs
        img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    # ponytail: no content autocrop / fine-angle deskew — Pillow-only until real
    # field photos show OCR failures this chain can't handle (would need OpenCV)
    return img


_MIN_WORDS_UPRIGHT = 5
_MIN_WORD_CONF = 60  # sideways text yields equally MANY words, but garbage — conf discriminates


def _confident_words(ocr: dict) -> int:
    return sum(
        1 for word, conf in zip(ocr["text"], ocr["conf"]) if word.strip() and conf >= _MIN_WORD_CONF
    )


def _ocr_best_rotation(img: Image.Image) -> tuple[Image.Image, dict]:
    """OCR upright; if that reads almost nothing trustworthy, try the three 90°
    rotations and keep the best. ponytail: brute force instead of tesseract OSD
    — OSD bails on panel crops ("Too few characters"); 3 extra passes, worst case."""
    ocr = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    score = _confident_words(ocr)
    if score >= _MIN_WORDS_UPRIGHT:
        return img, ocr
    for angle in (90, 180, 270):
        candidate = img.rotate(angle, expand=True)
        cand_ocr = pytesseract.image_to_data(candidate, output_type=pytesseract.Output.DICT)
        cand_score = _confident_words(cand_ocr)
        if cand_score > score:
            img, ocr, score = candidate, cand_ocr, cand_score
    return img, ocr


def _classify(ocr_text: str, image_bytes: bytes, content_type: str) -> tuple[str | None, float]:
    for brand, pattern in _BRANDS:
        if pattern.search(ocr_text):
            return brand, _CONF_KEYWORD
    brand = _classify_with_llm(image_bytes, content_type)
    return (brand, _CONF_LLM) if brand else (None, 0.0)


def _classify_with_llm(image_bytes: bytes, content_type: str) -> str | None:
    """Multimodal fallback when OCR sees no brand (glare, odd angle, logo-only).
    Degrades to None on any failure — vision must never kill the turn."""
    if not config.GOOGLE_API_KEY:
        return None
    import litellm  # ponytail: lazy — importing litellm costs seconds, only this path pays

    image_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"
    try:
        resp = litellm.completion(
            model=config.VISION_MODEL,
            api_key=config.GOOGLE_API_KEY,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _LLM_PROMPT},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        )
        answer = (resp.choices[0].message.content or "").upper()
    except Exception:
        return None
    return next((brand for brand, _ in _BRANDS if brand in answer), None)


def _annotate_codes(img: Image.Image, ocr: dict) -> bytes | None:
    """Red boxes around code-like OCR words → PNG bytes; the caller ships them
    to S3. Phase 4.2 swaps the box source (guidance overlays), not this path."""
    boxes = [
        (
            ocr["left"][i],
            ocr["top"][i],
            ocr["left"][i] + ocr["width"][i],
            ocr["top"][i] + ocr["height"][i],
        )
        for i, word in enumerate(ocr["text"])
        if _CODEISH_RE.match(word.strip())
    ]
    if not boxes:
        return None
    out = img.convert("RGB")
    draw = ImageDraw.Draw(out)
    for box in boxes:
        draw.rectangle(box, outline=(220, 30, 30), width=3)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
