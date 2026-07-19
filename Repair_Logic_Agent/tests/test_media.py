"""Feature 1.2: presigned upload endpoint.

Endpoint tests run everywhere (presigning is pure local crypto).
The round-trip test needs dev MinIO (docker compose -f infra/docker-compose.yml up -d);
skips otherwise, e.g. in CI.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _request_upload_url(content_type: str = "image/jpeg") -> dict:
    resp = client.post(
        "/api/v1/media/upload-url",
        json={"filename": "panel.jpg", "content_type": content_type},
    )
    assert resp.status_code == 200
    return resp.json()


def test_upload_url_shape():
    body = _request_upload_url()
    assert set(body) == {"upload_url", "media_key"}
    assert body["media_key"] in body["upload_url"]


def test_rejects_non_media_content_type():
    resp = client.post(
        "/api/v1/media/upload-url",
        json={"filename": "x.sh", "content_type": "application/x-sh"},
    )
    assert resp.status_code == 422


# Feature 2.10 — standalone transcribe endpoint (STT itself mocked; the real
# pipeline is covered by tests/stt/).


def test_transcribe_returns_transcript_and_confidence(monkeypatch):
    from app.api import media

    result = {"transcript": "AL 309 Rattern", "language": "de", "words": [], "confidence": 0.9}
    monkeypatch.setattr(media.stt, "transcribe", lambda key: result)
    resp = client.post("/api/v1/media/dev/some-uuid/transcribe")
    assert resp.status_code == 200
    assert resp.json() == {"transcript": "AL 309 Rattern", "confidence": 0.9}


def test_transcribe_foreign_tenant_is_404(monkeypatch):
    from app.api import media

    monkeypatch.setattr(
        media.stt, "transcribe", lambda key: pytest.fail("tenant guard must run before STT")
    )
    resp = client.post("/api/v1/media/other-tenant/some-uuid/transcribe")
    assert resp.status_code == 404


def test_transcribe_non_audio_is_422(monkeypatch):
    from app.api import media

    def not_audio(key):
        raise ValueError(f"{key} is not audio (image/jpeg)")

    monkeypatch.setattr(media.stt, "transcribe", not_audio)
    resp = client.post("/api/v1/media/dev/photo-key/transcribe")
    assert resp.status_code == 422


def test_put_roundtrip():
    body = _request_upload_url()
    payload = b"\xff\xd8fake-jpeg-bytes"
    try:
        put = httpx.put(
            body["upload_url"],
            content=payload,
            headers={"Content-Type": "image/jpeg"},
            timeout=2,
        )
    except httpx.TransportError:
        pytest.skip("dev MinIO not running")
    assert put.status_code == 200

    # signature covers Content-Type: a mismatching PUT must be refused
    bad = httpx.put(body["upload_url"], content=payload, timeout=2)
    assert bad.status_code in (400, 403)  # MinIO: 400, AWS: 403
