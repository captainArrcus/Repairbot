"""Feature 1.3 — AgentService stub (Wizard-of-Oz backend for the Phase 1 field test).

Scripted diagnostician: exact error-code lookup against the seeded error_codes
table (the fast path of the hybrid knowledge winner), hypotheses from
probable_causes, one discriminating question. Steps become typed events
(app/models/events.py) persisted to diagnostic_turn_events BEFORE anything is
streamed (spec 1.3 D3).

Feature 2.2: the inline lookup moved into the real tool modules (app/tools/);
this stub now walks both paths of the hybrid knowledge winner — exact
error-code lookup fast path, full-text candidate search slow path — and streams
tool_call/tool_result events for each.

Feature 2.3: turns carrying photos run VisionAnalysisTool first; detected codes
join the candidate codes ahead of the lookup, so a photo of a panel showing
AL 309 walks the same fast path as typed "AL 309".

The embedded hermes AIAgent replaces these internals in Feature 2.5; the FastAPI
layer only ever imports this module (Techstack abstraction boundary).
"""

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
from app.tools import vision_analysis
from app.tools.error_code_lookup import ErrorCodeLookup
from app.tools.knowledge_layer import KnowledgeRetrieval

# ponytail: fabricated confidence ladder for the stub's ranked hypotheses;
# real confidences come from the agent (Feature 2.5)
_CONFIDENCE_LADDER = [0.55, 0.25, 0.12, 0.08]

# ponytail: stand-in for the LLM judging candidate relevance (Feature 2.5) —
# drops FTS noise matches (real hits score ~1.0, noise ~0.04 on the seed corpus)
_MIN_SEARCH_SCORE = 0.1

_EVIDENCE_TYPES = {"photo", "audio", "tactile", "numeric", "text"}

# ponytail: bounded S3/OCR work per turn; the web prototype sends one photo
_MAX_VISION_IMAGES = 3


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

        events, tools_called, question = _scripted_diagnosis(
            cur, text, media_keys or [], machine_context, idx + 1
        )

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
    cur, text: str, media_keys: list[str], machine_context: dict | None, agent_turn_index: int
) -> tuple[list[Event], list[dict], str]:
    """Returns (events, tools_called json, primary question text)."""
    events: list[Event] = []
    tools_called: list[dict] = []

    vision_codes: list[str] = []
    if media_keys:
        events.append(ThinkingEvent(content="Analysiere das hochgeladene Foto ..."))
        for media_key in media_keys[:_MAX_VISION_IMAGES]:
            vision_codes += _vision_step(media_key, events, tools_called)

    codes = _candidate_codes(text, machine_context, vision_codes)

    alarm = None
    if codes:
        events.append(
            ThinkingEvent(content=f"Suche Fehlercode in der Meldung: {', '.join(codes)} ...")
        )
        events.append(ToolCallEvent(tool="error_code_lookup", args={"codes": codes}))
        tool = ErrorCodeLookup(cur.connection)
        # family filter deliberately None: family-string variants would false-negative (spec D2)
        alarm = next((a for c in codes if (a := tool.lookup(None, c))), None)
        if alarm:
            summary = f"exact match: {alarm['code']} ({alarm['controller_family']})"
            events.append(
                ToolResultEvent(tool="error_code_lookup", result_summary=summary, raw_result=alarm)
            )
        else:
            summary = "no exact match in error_codes"
            events.append(ToolResultEvent(tool="error_code_lookup", result_summary=summary))
        tools_called.append(
            {"tool": "error_code_lookup", "args": {"codes": codes}, "result_summary": summary}
        )
    else:
        events.append(
            ThinkingEvent(
                content="Kein Fehlercode in der Meldung erkannt — suche in der Wissensbasis "
                "nach der Symptombeschreibung."
            )
        )

    if alarm:
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
    else:
        question = _semantic_fallback(cur, text, codes, events, tools_called, agent_turn_index)

    events.append(DoneEvent(status="awaiting_user_input"))
    return events, tools_called, question


def _semantic_fallback(
    cur,
    text: str,
    codes: list[str],
    events: list[Event],
    tools_called: list[dict],
    agent_turn_index: int,
) -> str:
    """Hybrid slow path (spec D5): no exact code hit -> full-text candidate search;
    hits become candidate-alarm hypotheses, zero hits fall back to the photo ask."""
    results = []
    if text and text.strip():
        args = {"query": text, "top_k": len(_CONFIDENCE_LADDER)}
        events.append(ToolCallEvent(tool="knowledge_retrieval", args=args))
        results = KnowledgeRetrieval(cur.connection).search_semantic(text, top_k=args["top_k"])
        results = [r for r in results if r["score"] >= _MIN_SEARCH_SCORE]
        found = ", ".join(r["code"] for r in results) or "none"
        summary = f"{len(results)} confident candidate alarms via full-text search: {found}"
        events.append(
            ToolResultEvent(
                tool="knowledge_retrieval",
                result_summary=summary,
                raw_result={"results": results},
            )
        )
        tools_called.append(
            {"tool": "knowledge_retrieval", "args": args, "result_summary": summary}
        )

    if results:
        events.extend(
            HypothesisEvent(
                hypothesis_id=f"h{i + 1}",
                description=f"{r['code']}: {r['message_de'] or r['message_en'] or ''}",
                confidence=_CONFIDENCE_LADDER[i],
                introduced_at_turn=agent_turn_index,
            )
            for i, r in enumerate(results)
        )
        question, q_event = _question_from_alarm(results[0])
        events.append(q_event)
        return question

    if codes:
        question = (
            f"Der Fehlercode „{codes[0]}“ ist noch nicht in unserer Datenbank. "
            "Bitte machen Sie ein Foto des Bedienfelds mit der angezeigten Fehlermeldung, "
            "damit wir den Code prüfen können."
        )
    else:
        question = (
            "Ich habe in Ihrer Nachricht keinen Fehlercode erkannt. Nennen Sie bitte den "
            "Fehlercode vom Bedienfeld (z. B. AL 309) oder machen Sie ein Foto der "
            "angezeigten Fehlermeldung."
        )
    events.append(
        QuestionEvent(content=question, evidence_type="photo", required_format="image_of_panel")
    )
    return question


def _question_from_alarm(alarm: dict) -> tuple[str, QuestionEvent]:
    dq = (alarm["discriminating_questions"] or [{}])[0]
    question = dq.get("question") or "Beschreiben Sie bitte, wann genau der Fehler auftritt."
    evidence_type = dq.get("evidence_type")
    if evidence_type not in _EVIDENCE_TYPES:
        evidence_type = "text"
    return question, QuestionEvent(
        content=question, evidence_type=evidence_type, required_format=dq.get("expected_format")
    )


def _vision_step(media_key: str, events: list[Event], tools_called: list[dict]) -> list[str]:
    """Feature 2.3: photo in the turn → vision tool, streamed as tool events.
    Failures (missing object, audio key, S3 down) become a failure-summary
    tool_result — a bad photo must never 500 the turn."""
    args = {"media_key": media_key}
    events.append(ToolCallEvent(tool="vision_analysis", args=args))
    try:
        result = vision_analysis.analyze(media_key)
        summary = (
            f"controller: {result['detected_controller'] or 'unbekannt'}, "
            f"codes: {', '.join(result['detected_codes']) or 'keine'}"
        )
        events.append(
            ToolResultEvent(tool="vision_analysis", result_summary=summary, raw_result=result)
        )
    except Exception as exc:
        result = None
        summary = f"vision analysis failed: {exc}"
        events.append(ToolResultEvent(tool="vision_analysis", result_summary=summary))
    tools_called.append({"tool": "vision_analysis", "args": args, "result_summary": summary})
    # vision brand is NOT persisted to the session: coarser than a user-provided
    # family, and first-sighting-wins would lock it in (spec D7) — 2.5 decides
    return result["detected_codes"] if result else []


def _candidate_codes(text: str, machine_context: dict | None, vision_codes: list[str]) -> list[str]:
    codes = []
    if machine_context and machine_context.get("error_code"):
        codes.append(machine_context["error_code"].strip())
    codes += ErrorCodeLookup.extract_codes(text)
    codes += vision_codes
    return list(dict.fromkeys(codes))
