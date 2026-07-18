"""Feature 2.1 — Data Bridge: outcome write path + training-ready export.

The export schema (spec D5) is the single source of truth for the "training
schema": FastAPI serializes through it, the acceptance test validates against it.
Shape per Roadmap 2.1; chain entries carry both roles (spec D4).
"""

from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app import db


class ChainTurn(BaseModel):
    turn_index: int
    role: str
    content: str | None
    media_keys: list[str] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)


class InitialObservation(BaseModel):
    media_keys: list[str]
    symptom: str | None


class FinalDiagnosis(BaseModel):
    hypothesis_id: str
    description: str
    confidence: float


class Outcome(BaseModel):
    outcome: str
    repair_action: str | None
    verification_media_ref: str | None
    resolution_time_minutes: int | None
    technician_confidence: int | None


class SessionExport(BaseModel):
    session_id: str
    machine_context: dict
    initial_observation: InitialObservation | None
    diagnostic_chain: list[ChainTurn]
    final_diagnosis: FinalDiagnosis | None
    outcome: Outcome | None


def assemble_export(session_id: str) -> SessionExport:
    """Reconstruct the training example for a session. Raises KeyError if unknown."""
    with db.connect() as conn:
        cur = conn.cursor(row_factory=dict_row)

        session = cur.execute(
            """SELECT machine_family, controller_family, status, metadata
               FROM diagnostic_sessions WHERE id = %s""",
            (session_id,),
        ).fetchone()
        if session is None:
            raise KeyError(session_id)

        turns = cur.execute(
            """SELECT id, turn_index, role, content, media_refs
               FROM diagnostic_turns WHERE session_id = %s ORDER BY turn_index""",
            (session_id,),
        ).fetchall()

        events_by_turn: dict = {}
        for row in cur.execute(
            """SELECT e.turn_id, e.event_index, e.event_type, e.event_data
               FROM diagnostic_turn_events e
               JOIN diagnostic_turns t ON t.id = e.turn_id
               WHERE t.session_id = %s ORDER BY t.turn_index, e.event_index""",
            (session_id,),
        ).fetchall():
            events_by_turn.setdefault(row["turn_id"], []).append(
                {
                    "event_index": row["event_index"],
                    "event_type": row["event_type"],
                    "event_data": row["event_data"],
                }
            )

        final = cur.execute(
            """SELECT id, description, confidence FROM hypotheses
               WHERE session_id = %s AND is_final_diagnosis LIMIT 1""",
            (session_id,),
        ).fetchone()

        outcome = cur.execute(
            """SELECT outcome, repair_action, verification_media_ref,
                      resolution_time_minutes, technician_confidence
               FROM session_outcomes WHERE session_id = %s""",
            (session_id,),
        ).fetchone()

    first_user = next((t for t in turns if t["role"] == "user"), None)
    return SessionExport(
        session_id=str(session_id),
        machine_context={
            "machine_family": session["machine_family"],
            "controller_family": session["controller_family"],
            "status": session["status"],
            "metadata": session["metadata"],
        },
        initial_observation=InitialObservation(
            media_keys=first_user["media_refs"] or [], symptom=first_user["content"]
        )
        if first_user
        else None,
        diagnostic_chain=[
            ChainTurn(
                turn_index=t["turn_index"],
                role=t["role"],
                content=t["content"],
                media_keys=t["media_refs"] or [],
                events=events_by_turn.get(t["id"], []),
            )
            for t in turns
        ],
        final_diagnosis=FinalDiagnosis(
            hypothesis_id=str(final["id"]),
            description=final["description"],
            confidence=final["confidence"],
        )
        if final
        else None,
        outcome=Outcome(**outcome) if outcome else None,
    )


def record_outcome(
    session_id: str,
    outcome: str,
    final_diagnosis: str | None,
    repair_action: str | None,
    verification_media_ref: str | None,
    resolution_time_minutes: int | None,
    technician_confidence: int | None,
) -> None:
    """Write the session's training label (spec D3). Raises KeyError if unknown.

    Upserts session_outcomes (a technician may correct an outcome) and mirrors
    the outcome into diagnostic_sessions.status.
    """
    with db.connect() as conn:
        cur = conn.cursor(row_factory=dict_row)

        if (
            cur.execute("SELECT 1 FROM diagnostic_sessions WHERE id = %s", (session_id,)).fetchone()
            is None
        ):
            raise KeyError(session_id)

        final_id = None
        if final_diagnosis:
            cur.execute(
                "UPDATE hypotheses SET is_final_diagnosis = false WHERE session_id = %s",
                (session_id,),
            )
            row = cur.execute(
                "SELECT id FROM hypotheses WHERE session_id = %s AND description = %s",
                (session_id, final_diagnosis),
            ).fetchone()
            if row:
                final_id = row["id"]
                cur.execute(
                    "UPDATE hypotheses SET is_final_diagnosis = true WHERE id = %s", (final_id,)
                )
            else:
                # technician names a diagnosis the agent never raised — exactly
                # the training signal we want (spec D3)
                final_id = cur.execute(
                    """INSERT INTO hypotheses
                       (session_id, introduced_at_turn, description, confidence,
                        is_final_diagnosis)
                       VALUES (%s,
                               (SELECT COALESCE(MAX(turn_index), 0) FROM diagnostic_turns
                                WHERE session_id = %s),
                               %s, 1.0, true) RETURNING id""",
                    (session_id, session_id, final_diagnosis),
                ).fetchone()["id"]

        cur.execute(
            """INSERT INTO session_outcomes
               (session_id, outcome, final_diagnosis_id, repair_action,
                verification_media_ref, resolution_time_minutes, technician_confidence)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (session_id) DO UPDATE SET
                 outcome = EXCLUDED.outcome,
                 final_diagnosis_id = COALESCE(EXCLUDED.final_diagnosis_id,
                                               session_outcomes.final_diagnosis_id),
                 repair_action = EXCLUDED.repair_action,
                 verification_media_ref = EXCLUDED.verification_media_ref,
                 resolution_time_minutes = EXCLUDED.resolution_time_minutes,
                 technician_confidence = EXCLUDED.technician_confidence""",
            (
                session_id,
                outcome,
                final_id,
                repair_action,
                verification_media_ref,
                resolution_time_minutes,
                technician_confidence,
            ),
        )
        cur.execute(
            "UPDATE diagnostic_sessions SET status = %s WHERE id = %s", (outcome, session_id)
        )
