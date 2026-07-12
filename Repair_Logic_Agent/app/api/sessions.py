"""Feature 1.3 — sessions API + SSE stream.

SSE framing is manual (event:/id:/data: over StreamingResponse) — no extra
dependency (spec D2). Events are persisted before they are streamed, so the
stream endpoint is a DB replay + polling tail; Last-Event-ID resume comes free
(spec D3/D4).
"""

import json
from collections.abc import AsyncIterator
from uuid import UUID

import anyio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import db
from app.services import agent_service

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])

POLL_S = 0.5  # ponytail: DB-poll tail; in-process push when latency matters (Feature 2.5)
KEEPALIVE_S = 15


class CreateSessionRequest(BaseModel):
    machine_family: str = "cnc"
    controller_family: str | None = None
    metadata: dict | None = None


class CreateSessionResponse(BaseModel):
    session_id: str


class MachineContext(BaseModel):
    controller: str | None = None
    error_code: str | None = None


class TurnRequest(BaseModel):
    idempotency_key: str | None = None
    text: str = ""
    media_keys: list[str] = Field(default_factory=list)
    machine_context: MachineContext | None = None


class TurnResponse(BaseModel):
    turn_id: str


@router.post("")
def create_session(req: CreateSessionRequest | None = None) -> CreateSessionResponse:
    req = req or CreateSessionRequest()
    session_id = agent_service.create_session(
        req.machine_family, req.controller_family, req.metadata
    )
    return CreateSessionResponse(session_id=session_id)


@router.post("/{session_id}/turns")
def submit_turn(session_id: UUID, req: TurnRequest) -> TurnResponse:
    try:
        turn_id = agent_service.handle_turn(
            str(session_id),
            req.text,
            req.media_keys,
            req.machine_context.model_dump() if req.machine_context else None,
            req.idempotency_key,
        )
    except KeyError:
        raise HTTPException(404, "session not found") from None
    return TurnResponse(turn_id=turn_id)


@router.get("/{session_id}/stream")
async def stream(session_id: UUID, request: Request) -> StreamingResponse:
    if await anyio.to_thread.run_sync(_session_exists, session_id) is None:
        raise HTTPException(404, "session not found")
    cursor = _parse_last_event_id(request.headers.get("last-event-id"))
    return StreamingResponse(
        _event_stream(session_id, request, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/{session_id}/turns/{turn_id}/events")
def replay_events(session_id: UUID, turn_id: UUID, after: int = -1) -> dict:
    with db.connect() as conn:
        if (
            conn.execute(
                "SELECT 1 FROM diagnostic_turns WHERE id = %s AND session_id = %s",
                (turn_id, session_id),
            ).fetchone()
            is None
        ):
            raise HTTPException(404, "turn not found")
        rows = conn.execute(
            """SELECT event_index, event_type, event_data FROM diagnostic_turn_events
               WHERE turn_id = %s AND event_index > %s ORDER BY event_index""",
            (turn_id, after),
        ).fetchall()
    return {"events": [{"event_index": i, "event_type": t, "event_data": d} for i, t, d in rows]}


def _session_exists(session_id: UUID):
    with db.connect() as conn:
        return conn.execute(
            "SELECT 1 FROM diagnostic_sessions WHERE id = %s", (session_id,)
        ).fetchone()


def _parse_last_event_id(value: str | None) -> tuple[int, int]:
    # SSE wire id = "<turn_index>.<event_index>" — session-monotonic (spec D4)
    try:
        turn_index, event_index = value.split(".")
        return int(turn_index), int(event_index)
    except (AttributeError, ValueError):
        return -1, -1


def _fetch_after(session_id: UUID, cursor: tuple[int, int]) -> list:
    with db.connect() as conn:
        return conn.execute(
            """SELECT t.turn_index, e.event_index, e.event_type, e.event_data
               FROM diagnostic_turn_events e
               JOIN diagnostic_turns t ON t.id = e.turn_id
               WHERE t.session_id = %s AND (t.turn_index, e.event_index) > (%s, %s)
               ORDER BY t.turn_index, e.event_index""",
            (session_id, *cursor),
        ).fetchall()


async def _event_stream(
    session_id: UUID, request: Request, cursor: tuple[int, int]
) -> AsyncIterator[str]:
    idle = 0.0
    while not await request.is_disconnected():
        rows = await anyio.to_thread.run_sync(_fetch_after, session_id, cursor)
        for turn_index, event_index, event_type, event_data in rows:
            cursor = (turn_index, event_index)
            payload = json.dumps(event_data, ensure_ascii=False)
            yield f"event: {event_type}\nid: {turn_index}.{event_index}\ndata: {payload}\n\n"
        idle = 0.0 if rows else idle + POLL_S
        if idle >= KEEPALIVE_S:
            idle = 0.0
            yield ": keep-alive\n\n"
        await anyio.sleep(POLL_S)
