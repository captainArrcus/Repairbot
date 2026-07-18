"""Feature 2.3: VisionAnalysisTool.

Seed images are synthetic control-panel renders (spec D8 — no real field
photos exist yet): deterministic, offline, no binaries in git. OCR needs the
tesseract binary (CI installs it); tests skip cleanly without it. The MinIO
round-trip additionally needs the dev stack (docker compose up -d).
"""

import io
import shutil
import uuid

import psycopg
import pytest
from PIL import Image, ImageDraw, ImageFont

from app import config
from app.services import storage
from app.tools import vision_analysis

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    # offline determinism: the LLM fallback never fires in unit tests (spec D8)
    monkeypatch.setattr(vision_analysis, "_classify_with_llm", lambda *a: None)


# (expected_brand, bezel/header text, alarm line) — the labeled seed set
SEED_PANELS = [
    ("SINUMERIK", "SIEMENS SINUMERIK 840D sl", "ALARM: 309 Achse X1 Not-Halt"),
    ("SINUMERIK", "SINUMERIK OPERATE", "10720 Kanal 1 Software-Endschalter"),
    ("HEIDENHAIN", "HEIDENHAIN iTNC 530", "FEHLER: EXT. NOT-AUS"),
    ("HEIDENHAIN", "HEIDENHAIN TNC 640", "Fehler 25050 Positionierfehler"),
    ("FANUC", "FANUC Series 30i-B", "ALARM SV0401 V-READY OFF"),
    ("FANUC", "FANUC Series 0i-MF", "ALARM 414 SERVO ALARM X AXIS"),
]


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _render_panel(header: str, alarm_line: str, rotate: int = 0) -> bytes:
    """A control-panel-ish render: dark bezel with brand header, light screen
    area with the alarm line. OCR-friendly by design — synthetic seed, spec D8."""
    img = Image.new("RGB", (1000, 640), (40, 40, 45))
    draw = ImageDraw.Draw(img)
    draw.text((60, 40), header, font=_font(48), fill=(235, 235, 235))
    draw.rectangle((50, 140, 950, 560), fill=(200, 210, 200))
    draw.text((80, 180), alarm_line, font=_font(40), fill=(20, 20, 20))
    if rotate:
        img = img.rotate(rotate, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_controller_detection_meets_roadmap_bar():
    # Roadmap acceptance: >= 80% correct controller family on the seed images
    hits = 0
    for expected, header, alarm_line in SEED_PANELS:
        result, _ = vision_analysis._analyze_bytes(_render_panel(header, alarm_line), "image/png")
        hits += result["detected_controller"] == expected
    assert hits / len(SEED_PANELS) >= 0.8


def test_codes_and_annotation_from_panel():
    result, annotated = vision_analysis._analyze_bytes(
        _render_panel(*SEED_PANELS[0][1:]), "image/png"
    )
    assert "309" in result["detected_codes"]  # lookup normalizes 309 -> AL 309 (2.2)
    assert result["confidence"] == vision_analysis._CONF_KEYWORD
    assert annotated is not None
    assert Image.open(io.BytesIO(annotated)).format == "PNG"


def test_rotated_panel_still_classified():
    # coarse 90°-step rotation via best-of-four OCR passes (spec D2)
    result, _ = vision_analysis._analyze_bytes(
        _render_panel(*SEED_PANELS[0][1:], rotate=90), "image/png"
    )
    assert result["detected_controller"] == "SINUMERIK"


def test_blank_panel_yields_nothing():
    result, annotated = vision_analysis._analyze_bytes(
        _render_panel("", "kein Text mit Marke"), "image/png"
    )
    assert result["detected_controller"] is None
    assert result["confidence"] == 0.0
    assert result["detected_codes"] == []
    assert annotated is None


def test_llm_fallback_wiring(monkeypatch):
    # no brand in OCR text -> the multimodal fallback decides (patched, spec D3)
    monkeypatch.setattr(vision_analysis, "_classify_with_llm", lambda *a: "HEIDENHAIN")
    controller, confidence = vision_analysis._classify("no brand here", b"", "image/png")
    assert (controller, confidence) == ("HEIDENHAIN", vision_analysis._CONF_LLM)


def test_non_image_object_rejected(monkeypatch):
    monkeypatch.setattr(vision_analysis.storage, "get_object", lambda k: (b"x", "audio/webm"))
    with pytest.raises(ValueError, match="not an image"):
        vision_analysis.analyze("some-key")


def _minio_ready() -> bool:
    try:
        storage.put_object("vision-selftest", b"ok", "text/plain")
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _minio_ready(), reason="dev MinIO not running")
def test_analyze_round_trip_uploads_annotation():
    media_key = str(uuid.uuid4())
    storage.put_object(media_key, _render_panel(*SEED_PANELS[4][1:]), "image/png")

    result = vision_analysis.analyze(media_key)

    assert result["detected_controller"] == "FANUC"
    assert result["annotated_images"] == [f"{media_key}.annotated.png"]
    data, content_type = storage.get_object(f"{media_key}.annotated.png")
    assert content_type == "image/png" and data


def _db_ready() -> bool:
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM error_codes").fetchone()[0] > 0
    except psycopg.Error:
        return False


@pytest.mark.skipif(not (_db_ready() and _minio_ready()), reason="dev Postgres/MinIO not running")
def test_photo_turn_streams_vision_events_and_walks_fast_path():
    """Roadmap acceptance: photo upload → vision tool_call/tool_result streamed;
    a panel showing 309 yields the same hypotheses as typing 'AL 309'."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    media_key = str(uuid.uuid4())
    storage.put_object(media_key, _render_panel(*SEED_PANELS[0][1:]), "image/png")

    session_id = client.post("/api/v1/sessions").json()["session_id"]
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={"text": "Was bedeutet die Anzeige?", "media_keys": [media_key]},
    )
    assert resp.status_code == 200
    turn_id = resp.json()["turn_id"]

    events = client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}/events").json()["events"]
    calls = [e["event_data"] for e in events if e["event_type"] == "tool_call"]
    assert [c["tool"] for c in calls] == ["vision_analysis", "error_code_lookup"]
    vision_result = next(
        e["event_data"]
        for e in events
        if e["event_type"] == "tool_result" and e["event_data"]["tool"] == "vision_analysis"
    )
    raw = vision_result["raw_result"]
    assert raw["detected_controller"] == "SINUMERIK"
    assert raw["annotated_images"] == [f"{media_key}.annotated.png"]
    assert "hypothesis" in [e["event_type"] for e in events]  # 309 → seeded AL 309
