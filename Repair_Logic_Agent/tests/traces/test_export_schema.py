"""Feature 2.1: Data Bridge completion & export.

Flow tests need the dev Postgres (migrations + seed) — same skip rule as
tests/test_sessions.py.
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services.traces import SessionExport

client = TestClient(app)


def _db_ready() -> bool:
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT idempotency_key FROM diagnostic_turns LIMIT 1")
            return conn.execute("SELECT count(*) FROM error_codes").fetchone()[0] > 0
    except psycopg.Error:
        return False


needs_db = pytest.mark.skipif(not _db_ready(), reason="dev Postgres not running/migrated/seeded")


def _session_with_turn() -> str:
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={"text": "AL 309 beim Verfahren der X-Achse, deutliches Rattern"},
    )
    assert resp.status_code == 200
    return session_id


@needs_db
def test_full_trace_validates_against_training_schema():
    session_id = _session_with_turn()

    export = SessionExport.model_validate(
        client.get(f"/api/v1/sessions/{session_id}/export").json()
    )
    # mid-session (spec D6): open session exports with null labels
    assert export.outcome is None and export.final_diagnosis is None
    assert export.initial_observation.symptom.startswith("AL 309")
    assert [t.role for t in export.diagnostic_chain] == ["user", "agent"]
    agent_turn = export.diagnostic_chain[1]
    assert "hypothesis" in [e["event_type"] for e in agent_turn.events]

    # hypotheses landed in their first-class table (spec D2)
    with psycopg.connect(config.DATABASE_URL) as conn:
        count = conn.execute(
            "SELECT count(*) FROM hypotheses WHERE session_id = %s", (session_id,)
        ).fetchone()[0]
    assert count > 0

    # close the session with the technician's label (spec D3)
    diagnosis = next(
        e["event_data"]["description"] for e in agent_turn.events if e["event_type"] == "hypothesis"
    )
    resp = client.post(
        f"/api/v1/sessions/{session_id}/outcome",
        json={
            "outcome": "resolved",
            "final_diagnosis": diagnosis,
            "repair_action": "Encoder-Stecker X-Achse gereinigt und neu verriegelt",
            "resolution_time_minutes": 35,
            "technician_confidence": 4,
        },
    )
    assert resp.status_code == 200

    export = SessionExport.model_validate(
        client.get(f"/api/v1/sessions/{session_id}/export").json()
    )
    assert export.outcome.outcome == "resolved"
    assert export.outcome.technician_confidence == 4
    assert export.final_diagnosis.description == diagnosis
    assert export.machine_context["status"] == "resolved"


@needs_db
def test_repeated_turn_does_not_duplicate_hypotheses():
    session_id = _session_with_turn()
    client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "Immer noch AL 309"})
    with psycopg.connect(config.DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT description, count(*) FROM hypotheses WHERE session_id = %s"
            " GROUP BY description HAVING count(*) > 1",
            (session_id,),
        ).fetchall()
    assert rows == []


@needs_db
def test_confidence_change_writes_hypothesis_update():
    session_id = _session_with_turn()
    # nudge one stored confidence, then replay the same code: the stub re-emits
    # the original ladder → delta → hypothesis_updates row (spec D2)
    with psycopg.connect(config.DATABASE_URL) as conn:
        hyp_id = conn.execute(
            "SELECT id FROM hypotheses WHERE session_id = %s LIMIT 1", (session_id,)
        ).fetchone()[0]
        conn.execute("UPDATE hypotheses SET confidence = 0.99 WHERE id = %s", (hyp_id,))
    client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "AL 309 weiterhin da"})
    with psycopg.connect(config.DATABASE_URL) as conn:
        update = conn.execute(
            "SELECT confidence_before, confidence_after, evidence_text"
            " FROM hypothesis_updates WHERE hypothesis_id = %s",
            (hyp_id,),
        ).fetchone()
        restored = conn.execute(
            "SELECT confidence FROM hypotheses WHERE id = %s", (hyp_id,)
        ).fetchone()[0]
    assert update is not None
    assert update[0] == 0.99 and update[1] == restored
    assert "AL 309" in update[2]


@needs_db
def test_unknown_final_diagnosis_becomes_hypothesis():
    session_id = _session_with_turn()
    novel = "Kabelbruch im Schleppkettenkabel der X-Achse"
    client.post(
        f"/api/v1/sessions/{session_id}/outcome",
        json={"outcome": "escalated", "final_diagnosis": novel},
    )
    export = SessionExport.model_validate(
        client.get(f"/api/v1/sessions/{session_id}/export").json()
    )
    assert export.final_diagnosis.description == novel
    assert export.final_diagnosis.confidence == 1.0
    assert export.machine_context["status"] == "escalated"


@needs_db
def test_outcome_correction_upserts():
    session_id = _session_with_turn()
    url = f"/api/v1/sessions/{session_id}/outcome"
    client.post(url, json={"outcome": "escalated", "final_diagnosis": "Encoderfehler"})
    # correction without re-sending the diagnosis must not erase it
    client.post(url, json={"outcome": "resolved", "repair_action": "Encoder getauscht"})
    export = SessionExport.model_validate(
        client.get(f"/api/v1/sessions/{session_id}/export").json()
    )
    assert export.outcome.outcome == "resolved"
    assert export.outcome.repair_action == "Encoder getauscht"
    assert export.final_diagnosis.description == "Encoderfehler"


@needs_db
def test_empty_session_exports_with_nulls():
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    export = SessionExport.model_validate(
        client.get(f"/api/v1/sessions/{session_id}/export").json()
    )
    assert export.initial_observation is None
    assert export.diagnostic_chain == []
    assert export.final_diagnosis is None and export.outcome is None


@needs_db
def test_unknown_session_is_404():
    ghost = uuid.uuid4()
    assert client.get(f"/api/v1/sessions/{ghost}/export").status_code == 404
    assert (
        client.post(f"/api/v1/sessions/{ghost}/outcome", json={"outcome": "resolved"}).status_code
        == 404
    )
