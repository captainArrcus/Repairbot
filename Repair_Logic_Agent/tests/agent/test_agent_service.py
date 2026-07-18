"""Feature 2.5: hermes backend pipeline — RPC dispatch, validation, safety
gate, tenant isolation. Uses the deterministic stub worker (stub_worker.py) so
no hermes venv or LLM is needed; the real worker is covered by the live
acceptance run (spec FINDINGS). Flow tests need the dev Postgres (seeded);
unit tests run everywhere.
"""

import json
import sys
import threading
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models.events import HypothesisEvent, ThinkingEvent
from app.services import agent_service, hermes_backend, observability

client = TestClient(app)
STUB_CMD = f"{sys.executable} {Path(__file__).parent / 'stub_worker.py'}"


def _db_ready() -> bool:
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT idempotency_key FROM diagnostic_turns LIMIT 1")
            return conn.execute("SELECT count(*) FROM error_codes").fetchone()[0] > 0
    except psycopg.Error:
        return False


needs_db = pytest.mark.skipif(not _db_ready(), reason="dev Postgres not running/migrated/seeded")


@pytest.fixture
def hermes(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AGENT_BACKEND", "hermes")
    monkeypatch.setattr(config, "AGENT_RUNNER", "subprocess")
    monkeypatch.setattr(config, "AGENT_WORKER_CMD", STUB_CMD)
    monkeypatch.setattr(config, "HERMES_HOME_ROOT", str(tmp_path))
    monkeypatch.setattr(config, "AGENT_TURN_TIMEOUT_S", 20.0)
    yield tmp_path
    for sid in list(hermes_backend._workers):
        hermes_backend.drop_worker(sid)


@pytest.fixture
def agent_errors(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        observability, "log_agent_error", lambda sid, kind, detail: calls.append((kind, detail))
    )
    return calls


def _create_session(tenant: str = "dev") -> str:
    resp = client.post("/api/v1/sessions", headers={"X-Tenant-Id": tenant})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def _events(session_id: str, turn_id: str) -> list[dict]:
    return client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}/events").json()["events"]


# --- unit (no DB) ---


def test_allowlist_is_the_ratified_eight():
    assert hermes_backend.ALLOWED_TOOLS == {
        "vision_analysis",
        "error_code_lookup",
        "knowledge_retrieval",
        "repair_web_search",
        "memory",
        "skills_list",
        "skill_view",
        "skill_manage",
    }


def test_build_event_validates_and_sanitizes(agent_errors):
    ev = hermes_backend.build_event(
        "s1", "hypothesis", {"hypothesis_id": "h1", "description": "x", "confidence": 0.4}, 3
    )
    assert isinstance(ev, HypothesisEvent) and ev.introduced_at_turn == 3

    bad = hermes_backend.build_event("s1", "hypothesis", {"description": "no confidence"}, 3)
    assert isinstance(bad, ThinkingEvent)
    unknown = hermes_backend.build_event("s1", "frobnicate", {"content": "?"}, 3)
    assert isinstance(unknown, ThinkingEvent)
    raw = hermes_backend.build_event("s1", "raw", {"content": "prose"}, 3)
    assert isinstance(raw, ThinkingEvent) and raw.content == "prose"
    # raw is sanitized silently; the two real violations are logged
    assert [k for k, _ in agent_errors] == ["invalid_event", "invalid_event"]


def test_media_tenant_guard():
    agent_service._check_media_tenant("acme", ["acme/abc"])
    agent_service._check_media_tenant("dev", ["bare-legacy-key", "dev/abc"])
    with pytest.raises(ValueError):
        agent_service._check_media_tenant("acme", ["other/abc"])
    with pytest.raises(ValueError):
        agent_service._check_media_tenant("acme", ["bare-key"])


def test_media_key_carries_tenant_prefix():
    resp = client.post(
        "/api/v1/media/upload-url",
        json={"filename": "a.jpg", "content_type": "image/jpeg"},
        headers={"X-Tenant-Id": "acme"},
    )
    assert resp.json()["media_key"].startswith("acme/")


# --- flow (stub worker + dev Postgres) ---


@needs_db
def test_hermes_turn_streams_validated_events(hermes):
    session_id = _create_session()
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={"text": "AL 309 beim Verfahren der X-Achse"},
    )
    assert resp.status_code == 200
    events = _events(session_id, resp.json()["turn_id"])
    types = [e["event_type"] for e in events]
    # RPC surfaced live: the stub's error_code_lookup ran against the REAL seed DB
    assert "tool_call" in types and "tool_result" in types
    result = next(e["event_data"] for e in events if e["event_type"] == "tool_result")
    assert result["result_summary"].startswith("exact match: AL 309")
    assert "hypothesis" in types and "question" in types and types[-1] == "done"

    with psycopg.connect(config.DATABASE_URL) as conn:
        content, tools_called = conn.execute(
            "SELECT content, tools_called FROM diagnostic_turns"
            " WHERE session_id = %s AND role = 'agent'",
            (session_id,),
        ).fetchone()
        assert content == "Wie viel Axialspiel in mm?"
        assert tools_called[0]["tool"] == "error_code_lookup"
        assert (
            conn.execute(
                "SELECT count(*) FROM hypotheses WHERE session_id = %s", (session_id,)
            ).fetchone()[0]
            == 1
        )


@needs_db
def test_vision_rpc_is_session_scoped(hermes, monkeypatch):
    monkeypatch.setattr(agent_service.storage, "head_content_type", lambda key: "image/jpeg")
    monkeypatch.setattr(
        hermes_backend.vision_analysis,
        "analyze",
        lambda key: {
            "detected_controller": "SINUMERIK",
            "detected_codes": ["AL 309"],
            "annotated_images": [],
            "confidence": 0.9,
        },
    )
    monkeypatch.setenv("STUB_EXTRA_VISION_KEY", "foreign-session-key")
    session_id = _create_session()
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        json={"text": "Foto vom Panel", "media_keys": ["panel-key"]},
    )
    events = _events(session_id, resp.json()["turn_id"])
    vision_results = [
        e["event_data"]["result_summary"]
        for e in events
        if e["event_type"] == "tool_result" and e["event_data"]["tool"] == "vision_analysis"
    ]
    assert vision_results[0].startswith("controller: SINUMERIK")  # session media: allowed
    assert "does not belong" in vision_results[1]  # foreign key: refused (trust boundary)


@needs_db
def test_invalid_output_sanitized_and_logged(hermes, agent_errors, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "invalid")
    session_id = _create_session()
    resp = client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "kaputt"})
    events = _events(session_id, resp.json()["turn_id"])
    types = [e["event_type"] for e in events]
    assert types == ["thinking", "thinking", "thinking", "done"]  # nothing raw forwarded
    assert types.count("hypothesis") == 0
    assert {k for k, _ in agent_errors} == {"invalid_event"}


@needs_db
def test_high_safety_guidance_gates_followup(hermes, agent_errors, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "safety")
    session_id = _create_session()
    resp = client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "Kurzschluss?"})
    events = _events(session_id, resp.json()["turn_id"])
    types = [e["event_type"] for e in events]
    assert types == ["guidance", "done"]  # low guidance + question suppressed
    assert events[0]["event_data"]["safety_level"] == "high"
    assert events[-1]["event_data"]["status"] == "awaiting_user_input"  # NOT "complete"
    assert [k for k, _ in agent_errors].count("suppressed_event") == 2


@needs_db
def test_allowlist_breach_fails_safe(hermes, agent_errors, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "badtools")
    session_id = _create_session()
    resp = client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "AL 309"})
    assert resp.status_code == 503
    assert [k for k, _ in agent_errors] == ["allowlist_breach"]
    with psycopg.connect(config.DATABASE_URL) as conn:  # fail safe: nothing persisted
        assert (
            conn.execute(
                "SELECT count(*) FROM diagnostic_turns WHERE session_id = %s", (session_id,)
            ).fetchone()[0]
            == 0
        )


@needs_db
def test_cross_tenant_parallel_zero_bleed(hermes, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "marker")
    secrets = {"tenant-a": "SECRET-ALPHA-9317", "tenant-b": "SECRET-BRAVO-4242"}
    session_ids = {t: _create_session(tenant=t) for t in secrets}

    def _turn(tenant: str) -> None:
        resp = client.post(
            f"/api/v1/sessions/{session_ids[tenant]}/turns", json={"text": secrets[tenant]}
        )
        assert resp.status_code == 200

    threads = [threading.Thread(target=_turn, args=(t,)) for t in secrets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for tenant, secret in secrets.items():
        home = hermes.joinpath(tenant)
        assert secret in (home / "marker.txt").read_text()
        other = next(s for t, s in secrets.items() if t != tenant)
        leaked = [
            p for p in home.rglob("*") if p.is_file() and other in p.read_text(errors="ignore")
        ]
        assert leaked == [], f"tenant bleed: {other} found in {leaked}"


@needs_db
def test_concurrent_turn_is_409(hermes):
    session_id = _create_session()
    worker = hermes_backend.acquire_worker(session_id, "dev")  # holds the turn lock
    try:
        resp = client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "AL 309"})
        assert resp.status_code == 409
    finally:
        worker.lock.release()


@needs_db
def test_turn_timeout_kills_worker(hermes, agent_errors, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "sleep")
    monkeypatch.setattr(config, "AGENT_TURN_TIMEOUT_S", 1.5)
    session_id = _create_session()
    resp = client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "AL 309"})
    assert resp.status_code == 200  # agent failure never 500s the turn
    events = _events(session_id, resp.json()["turn_id"])
    assert [e["event_type"] for e in events] == ["thinking", "done"]
    assert "worker_error" in [k for k, _ in agent_errors]
    assert not hermes_backend._workers[session_id].alive


@needs_db
def test_respawned_worker_gets_history_context(hermes):
    session_id = _create_session()
    client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "AL 309 Rattern X-Achse"})
    hermes_backend.drop_worker(session_id)  # simulate worker death between turns

    resp = client.post(f"/api/v1/sessions/{session_id}/turns", json={"text": "0.5mm Spiel"})
    events = _events(session_id, resp.json()["turn_id"])
    context_thinking = events[0]["event_data"]["content"]
    assert context_thinking.startswith("context:")
    assert "AL 309 Rattern X-Achse" in json.dumps([e["event_data"] for e in events])
