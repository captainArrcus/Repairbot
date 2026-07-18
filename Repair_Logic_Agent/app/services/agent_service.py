"""Feature 1.3 — AgentService stub (Wizard-of-Oz backend for the Phase 1 field test).

Scripted diagnostician: exact error-code lookup against the seeded error_codes
table (the fast path of the hybrid knowledge winner), hypotheses from
probable_causes, one discriminating question. Steps become typed events
(app/models/events.py) persisted to diagnostic_turn_events BEFORE anything is
streamed (spec 1.3 D3).

The embedded hermes AIAgent replaces these internals in Feature 2.5; the FastAPI
layer only ever imports this module (Techstack abstraction boundary).
"""

import re

from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import db
from app.models.events import (
    DoneEvent,
    Event,
    HypothesisEvent,
    QuestionEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)

# ponytail: catches the seeded formats ("AL 309", "F07011", bare "10720", bare "309");
# real prefix/whitespace/case normalization is the ErrorCodeLookupTool's job (Feature 2.2)
_CODE_RE = re.compile(r"\b(?:AL[\s-]?\d{3,6}|F\d{4,6}|\d{3,6})\b", re.IGNORECASE)

# ponytail: fabricated confidence ladder for the stub's ranked hypotheses;
# real confidences come from the agent (Feature 2.5)
_CONFIDENCE_LADDER = [0.55, 0.25, 0.12, 0.08]

_EVIDENCE_TYPES = {"photo", "audio", "tactile", "numeric", "text"}


def create_session(
    machine_family: str, controller_family: str | None, metadata: dict | None
) -> str:
    with db.connect() as conn:
        # ponytail: tenant_id 'dev' until auth introduces tenant context (Feature 2.5)
        row = conn.execute(
            """INSERT INTO diagnostic_sessions
               (tenant_id, machine_family, controller_family, metadata)
               VALUES ('dev', %s, %s, %s) RETURNING id""",
            (machine_family, controller_family, Jsonb(metadata) if metadata else None),
        ).fetchone()
        return str(row[0])


def handle_turn(
    session_id: str,
    text: str,
    media_keys: list[str],
    machine_context: dict | None,
    idempotency_key: str | None = None,
) -> str:
    """Persist the user turn, run the scripted diagnostician, persist the agent
    turn + its events. Returns the agent turn id (the replay handle, spec D9).

    Raises KeyError if the session does not exist.
    """
    try:
        return _process_turn(session_id, text, media_keys, machine_context, idempotency_key)
    except errors.UniqueViolation:
        # concurrent duplicate submit: first writer won — return its agent turn
        with db.connect() as conn:
            row = conn.execute(_IDEMPOTENT_REPLAY_SQL, (session_id, idempotency_key)).fetchone()
            return str(row[0])


_IDEMPOTENT_REPLAY_SQL = """
    SELECT a.id FROM diagnostic_turns u
    JOIN diagnostic_turns a
      ON a.session_id = u.session_id AND a.turn_index = u.turn_index + 1
    WHERE u.session_id = %s AND u.idempotency_key = %s
"""


def _process_turn(
    session_id: str,
    text: str,
    media_keys: list[str],
    machine_context: dict | None,
    idempotency_key: str | None,
) -> str:
    with db.connect() as conn:
        cur = conn.cursor(row_factory=dict_row)

        if (
            cur.execute("SELECT 1 FROM diagnostic_sessions WHERE id = %s", (session_id,)).fetchone()
            is None
        ):
            raise KeyError(session_id)

        if idempotency_key:
            row = cur.execute(_IDEMPOTENT_REPLAY_SQL, (session_id, idempotency_key)).fetchone()
            if row:
                return str(row["id"])

        controller = (machine_context or {}).get("controller")
        if controller:
            # progressive machine context (Techstack): first sighting wins
            cur.execute(
                """UPDATE diagnostic_sessions
                   SET controller_family = COALESCE(controller_family, %s) WHERE id = %s""",
                (controller, session_id),
            )

        idx = cur.execute(
            "SELECT COALESCE(MAX(turn_index) + 1, 0) AS idx FROM diagnostic_turns"
            " WHERE session_id = %s",
            (session_id,),
        ).fetchone()["idx"]

        cur.execute(
            """INSERT INTO diagnostic_turns
               (session_id, turn_index, role, content, media_refs, idempotency_key)
               VALUES (%s, %s, 'user', %s, %s, %s)""",
            (session_id, idx, text, media_keys or [], idempotency_key),
        )

        events, tools_called, question = _scripted_diagnosis(cur, text, machine_context, idx + 1)

        agent_turn_id = cur.execute(
            """INSERT INTO diagnostic_turns
               (session_id, turn_index, role, content, tools_called)
               VALUES (%s, %s, 'agent', %s, %s) RETURNING id""",
            (session_id, idx + 1, question, Jsonb(tools_called)),
        ).fetchone()["id"]

        for i, ev in enumerate(events):
            cur.execute(
                """INSERT INTO diagnostic_turn_events (turn_id, event_index, event_type, event_data)
                   VALUES (%s, %s, %s, %s)""",
                (agent_turn_id, i, ev.type, Jsonb(ev.model_dump(exclude_none=True))),
            )

        _persist_hypotheses(
            cur,
            session_id,
            agent_turn_id,
            idx + 1,
            [ev for ev in events if isinstance(ev, HypothesisEvent)],
            evidence_text=text,
            evidence_media_ref=media_keys[0] if media_keys else None,
        )

        return str(agent_turn_id)


def _persist_hypotheses(
    cur,
    session_id: str,
    agent_turn_id,
    agent_turn_index: int,
    hypothesis_events: list[HypothesisEvent],
    evidence_text: str,
    evidence_media_ref: str | None,
) -> None:
    """Feature 2.1 (spec D2): mirror hypothesis events into their first-class tables.

    Upsert by (session_id, description): new description → hypotheses row;
    changed confidence → hypothesis_updates row + confidence update.
    """
    # ponytail: SELECT-then-INSERT — single writer per turn transaction; add a
    # unique index when concurrent writers exist (Feature 2.5)
    for ev in hypothesis_events:
        row = cur.execute(
            "SELECT id, confidence FROM hypotheses WHERE session_id = %s AND description = %s",
            (session_id, ev.description),
        ).fetchone()
        if row is None:
            cur.execute(
                """INSERT INTO hypotheses
                   (session_id, introduced_at_turn, description, confidence)
                   VALUES (%s, %s, %s, %s)""",
                (session_id, ev.introduced_at_turn, ev.description, ev.confidence),
            )
        elif row["confidence"] != ev.confidence:
            cur.execute(
                """INSERT INTO hypothesis_updates
                   (hypothesis_id, turn_id, confidence_before, confidence_after,
                    evidence_text, evidence_media_ref)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    row["id"],
                    agent_turn_id,
                    row["confidence"],
                    ev.confidence,
                    evidence_text,
                    evidence_media_ref,
                ),
            )
            cur.execute(
                "UPDATE hypotheses SET confidence = %s WHERE id = %s", (ev.confidence, row["id"])
            )
        if ev.eliminated and row is not None:
            cur.execute(
                """UPDATE hypotheses SET eliminated_at_turn = COALESCE(eliminated_at_turn, %s)
                   WHERE id = %s""",
                (agent_turn_index, row["id"]),
            )


def _scripted_diagnosis(
    cur, text: str, machine_context: dict | None, agent_turn_index: int
) -> tuple[list[Event], list[dict], str]:
    """Returns (events, tools_called json, primary question text)."""
    candidates = _extract_candidates(text, machine_context)

    if not candidates:
        # no code in the message — a lookup with nothing to look up is just noise
        question = (
            "Ich habe in Ihrer Nachricht keinen Fehlercode erkannt. Nennen Sie bitte den "
            "Fehlercode vom Bedienfeld (z. B. AL 309) oder machen Sie ein Foto der "
            "angezeigten Fehlermeldung."
        )
        events = [
            ThinkingEvent(content="Kein Fehlercode in der Meldung erkannt."),
            QuestionEvent(
                content=question, evidence_type="photo", required_format="image_of_panel"
            ),
            DoneEvent(status="awaiting_user_input"),
        ]
        return events, [], question

    events: list[Event] = [
        ThinkingEvent(content=f"Suche Fehlercode in der Meldung: {', '.join(candidates)} ..."),
        ToolCallEvent(tool="error_code_lookup", args={"candidates": candidates}),
    ]

    alarm = _lookup(cur, candidates)
    if alarm is None:
        summary = "no exact match in error_codes"
        events.append(ToolResultEvent(tool="error_code_lookup", result_summary=summary))
        question = (
            f"Der Fehlercode „{candidates[0]}“ ist noch nicht in unserer Datenbank. "
            "Bitte machen Sie ein Foto des Bedienfelds mit der angezeigten Fehlermeldung, "
            "damit wir den Code prüfen können."
        )
        events.append(
            QuestionEvent(content=question, evidence_type="photo", required_format="image_of_panel")
        )
    else:
        summary = f"exact match: {alarm['code']} ({alarm['controller_family']})"
        events.append(
            ToolResultEvent(tool="error_code_lookup", result_summary=summary, raw_result=alarm)
        )
        causes = alarm["probable_causes"][: len(_CONFIDENCE_LADDER)]
        events.extend(
            HypothesisEvent(
                hypothesis_id=f"h{i + 1}",
                description=cause,
                confidence=_CONFIDENCE_LADDER[i],
                introduced_at_turn=agent_turn_index,
            )
            for i, cause in enumerate(causes)
        )
        question, q_event = _question_from_alarm(alarm)
        events.append(q_event)

    events.append(DoneEvent(status="awaiting_user_input"))
    tools_called = [
        {"tool": "error_code_lookup", "args": {"candidates": candidates}, "result_summary": summary}
    ]
    return events, tools_called, question


def _question_from_alarm(alarm: dict) -> tuple[str, QuestionEvent]:
    dq = (alarm["discriminating_questions"] or [{}])[0]
    question = dq.get("question") or "Beschreiben Sie bitte, wann genau der Fehler auftritt."
    evidence_type = dq.get("evidence_type")
    if evidence_type not in _EVIDENCE_TYPES:
        evidence_type = "text"
    return question, QuestionEvent(
        content=question, evidence_type=evidence_type, required_format=dq.get("expected_format")
    )


def _extract_candidates(text: str, machine_context: dict | None) -> list[str]:
    raw = []
    if machine_context and machine_context.get("error_code"):
        raw.append(machine_context["error_code"])
    raw += _CODE_RE.findall(text or "")
    normalized = []
    for c in raw:
        c = c.strip()
        normalized += [c, c.upper(), re.sub(r"(?i)^al[\s-]*", "AL ", c).upper()]
        if c.isdigit():
            normalized.append(f"AL {c}")  # bare number — seeded AL codes store the prefix
    return list(dict.fromkeys(normalized))


def _lookup(cur, candidates: list[str]) -> dict | None:
    if not candidates:
        return None
    return cur.execute(
        """SELECT code, controller_family, message_de, message_en, probable_causes,
                  discriminating_questions, manual_reference
           FROM error_codes WHERE code = ANY(%s) LIMIT 1""",
        (candidates,),
    ).fetchone()
