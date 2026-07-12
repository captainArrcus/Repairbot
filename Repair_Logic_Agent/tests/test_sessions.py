"""Feature 1.3: sessions API + SSE stream.

Event-model tests run everywhere. Flow tests need the dev Postgres with
migrations 001+002 and the Feature 1.1 seed applied
(docker compose -f infra/docker-compose.yml up -d); skip otherwise, e.g. in CI.
"""

import json
import uuid

import anyio
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import sessions
from app.main import app
from app.models.events import GuidanceEvent, HypothesisEvent, QuestionEvent

client = TestClient(app)


def _db_ready() -> bool:
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT idempotency_key FROM diagnostic_turns LIMIT 1")
            return conn.execute("SELECT count(*) FROM error_codes").fetchone()[0] > 0
    except psycopg.Error:
        return False


needs_db = pytest.mark.skipif(not _db_ready(), reason="dev Postgres not running/migrated/seeded")


def test_event_schemas_are_canonical():
    h = HypothesisEvent(
        hypothesis_id="h1", description="worn bearing", confidence=0.55, introduced_at_turn=1
    )
    assert set(h.model_dump(exclude_none=True)) == {
        "id",
        "hypothesis_id",
        "description",
        "confidence",
        "introduced_at_turn",
    }
    with pytest.raises(ValueError):
        HypothesisEvent(hypothesis_id="h1", description="x", confidence=1.5, introduced_at_turn=0)
    with pytest.raises(ValueError):
        QuestionEvent(content="?", evidence_type="smell")
    with pytest.raises(ValueError):  # safety_level required — no silent "low" default
        GuidanceEvent(step_index=1, content="open the cabinet")


def _create_session(**body) -> str:
    resp = client.post("/api/v1/sessions", json=body) if body else client.post("/api/v1/sessions")
    assert resp.status_code == 200
    return resp.json()["session_id"]


@needs_db
def test_full_turn_flow_with_error_code():
    session_id = _create_session()
    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "text": "AL 309 beim Verfahren der X-Achse, deutliches Rattern",
        "machine_context": {"controller": "SINUMERIK_840D_sl", "error_code": "AL 309"},
    }
    resp = client.post(f"/api/v1/sessions/{session_id}/turns", json=payload)
    assert resp.status_code == 200
    turn_id = resp.json()["turn_id"]

    events = client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}/events").json()["events"]
    types = [e["event_type"] for e in events]
    assert types[0] == "thinking"
    assert "tool_call" in types and "tool_result" in types
    assert "hypothesis" in types and "question" in types
    assert types[-1] == "done"
    hypothesis = next(e["event_data"] for e in events if e["event_type"] == "hypothesis")
    assert 0 <= hypothesis["confidence"] <= 1
    assert hypothesis["introduced_at_turn"] == 1

    # idempotent retry (flaky WiFi): same turn back, no duplicate processing
    retry = client.post(f"/api/v1/sessions/{session_id}/turns", json=payload)
    assert retry.json()["turn_id"] == turn_id

    # replay cursor: only events after the given event_index
    tail = client.get(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/events",
        params={"after": events[-2]["event_index"]},
    ).json()["events"]
    assert [e["event_type"] for e in tail] == ["done"]


@needs_db
def test_no_error_code_asks_for_photo():
    session_id = _create_session(machine_family="cnc_mill")
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={"text": "Maschine macht komische Geräusche"},
    )
    turn_id = resp.json()["turn_id"]
    events = client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}/events").json()["events"]
    question = next(e["event_data"] for e in events if e["event_type"] == "question")
    assert question["evidence_type"] == "photo"


class _OneShotRequest:
    """Disconnects after the first poll — TestClient can't consume an unbounded
    stream body, so the generator is driven directly; the HTTP layer is covered
    by the curl acceptance run (spec FINDINGS)."""

    def __init__(self) -> None:
        self.polls = 0

    async def is_disconnected(self) -> bool:
        self.polls += 1
        return self.polls > 1


@needs_db
def test_sse_stream_frames_persisted_events():
    session_id = _create_session()
    client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "AL 309 Rattern X-Achse"})

    async def collect() -> list[str]:
        gen = sessions._event_stream(uuid.UUID(session_id), _OneShotRequest(), (-1, -1))
        return [frame async for frame in gen]

    lines = "".join(anyio.run(collect)).splitlines()
    assert any(line == "event: hypothesis" for line in lines)
    assert any(line.startswith("id: 1.") for line in lines)
    data_line = next(line for line in lines if line.startswith("data:"))
    assert "id" in json.loads(data_line.removeprefix("data:"))

    # Last-Event-ID resume: cursor past the question (1.7) leaves only the done event
    async def resume() -> list[str]:
        gen = sessions._event_stream(uuid.UUID(session_id), _OneShotRequest(), (1, 7))
        return [frame async for frame in gen]

    resumed = "".join(anyio.run(resume)).splitlines()
    assert [line for line in resumed if line.startswith("event:")] == ["event: done"]


@needs_db
def test_unknown_session_is_404():
    ghost = uuid.uuid4()
    assert client.post(f"/api/v1/sessions/{ghost}/turns", json={"text": "x"}).status_code == 404
    assert client.get(f"/api/v1/sessions/{ghost}/stream").status_code == 404
    assert client.get(f"/api/v1/sessions/{ghost}/turns/{uuid.uuid4()}/events").status_code == 404
