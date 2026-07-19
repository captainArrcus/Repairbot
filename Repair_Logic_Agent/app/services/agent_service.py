"""AgentService — turn pipeline shell + two interchangeable diagnosis backends.

Feature 2.5: the embedded hermes AIAgent (worker process, app/services/
hermes_backend.py + agents/hermes_worker.py) is the real agent; the Feature
1.3 scripted diagnostician stays as the deterministic backend for CI and the
golden harness (spec 2.5 D7, AGENT_BACKEND config). Both backends produce the
same typed events through ONE persistence loop, which now commits per event so
the SSE DB-tail streams mid-turn (spec 2.5 D4), and which enforces the
physical-safety approval gate (spec 2.5 D5).

Feature 2.4: audio media is transcribed inline BEFORE the user turn is
persisted — STT is an input adapter, not an agent tool. Vision is inline for
the scripted backend, agent-called for hermes (spec 2.5 D2).
"""

from itertools import chain

from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import config, db
from app.models.events import (
    DiagnosisEvent,
    DoneEvent,
    Event,
    GuidanceEvent,
    HypothesisEvent,
    QuestionEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.services import hermes_backend, observability, storage
from app.tools import stt, vision_analysis
from app.tools.error_code_lookup import ErrorCodeLookup
from app.tools.knowledge_layer import KnowledgeRetrieval

# ponytail: fabricated confidence ladder for the scripted backend's ranked
# hypotheses; hermes provides real confidences
_CONFIDENCE_LADDER = [0.55, 0.25, 0.12, 0.08]

# ponytail: stand-in for the LLM judging candidate relevance (scripted backend
# only) — drops FTS noise matches (real hits score ~1.0, noise ~0.04)
_MIN_SEARCH_SCORE = 0.1

_EVIDENCE_TYPES = {"photo", "audio", "tactile", "numeric", "text"}

# ponytail: bounded S3/OCR work per turn; the web prototype sends one photo
_MAX_VISION_IMAGES = 3
# ponytail: bounded ffmpeg/Whisper work per turn; one voice note is the real case
_MAX_STT_CLIPS = 3
# ponytail: degraded respawn context — last turns as plain text, not hermes state (spec D1)
_MAX_CONTEXT_TURNS = 12


def create_session(
    machine_family: str,
    controller_family: str | None,
    metadata: dict | None,
    tenant_id: str = "dev",
) -> str:
    with db.connect() as conn:
        row = conn.execute(
            """INSERT INTO diagnostic_sessions
               (tenant_id, machine_family, controller_family, metadata)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (tenant_id, machine_family, controller_family, Jsonb(metadata) if metadata else None),
        ).fetchone()
        return str(row[0])


def handle_turn(
    session_id: str,
    text: str,
    media_keys: list[str],
    machine_context: dict | None,
    idempotency_key: str | None = None,
) -> str:
    """Persist the user turn, run the diagnosis backend, persist the agent turn
    + its events (committed per event — the SSE tail streams them live).
    Returns the agent turn id (the replay handle, spec 1.3 D9).

    Raises KeyError (unknown session), ValueError (media key outside the
    session's tenant), hermes_backend.AgentBusyError (turn in flight).
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

        session = cur.execute(
            "SELECT tenant_id FROM diagnostic_sessions WHERE id = %s", (session_id,)
        ).fetchone()
        if session is None:
            raise KeyError(session_id)
        _check_media_tenant(session["tenant_id"], media_keys or [])

        if idempotency_key:
            row = cur.execute(_IDEMPOTENT_REPLAY_SQL, (session_id, idempotency_key)).fetchone()
            if row:
                return str(row["id"])

        worker = None
        if config.AGENT_BACKEND == "hermes":
            # busy check BEFORE any write — a 409 must leave no orphan user turn
            worker = hermes_backend.acquire_worker(session_id, session["tenant_id"])
        try:
            return _run_turn(
                conn, cur, worker, session_id, text, media_keys, machine_context, idempotency_key
            )
        finally:
            if worker is not None:
                worker.lock.release()


def _run_turn(
    conn, cur, worker, session_id, text, media_keys, machine_context, idempotency_key
) -> str:
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

    # Feature 2.4: transcribe voice notes BEFORE persisting the user turn —
    # the transcript IS user-turn text (Roadmap acceptance)
    audio_keys, visual_media = _split_media(media_keys or [])
    stt_events: list[Event] = []
    tools_called: list[dict] = []
    transcripts: list[str] = []
    if audio_keys:
        stt_events.append(ThinkingEvent(content="Transkribiere die Sprachnachricht ..."))
        for media_key in audio_keys[:_MAX_STT_CLIPS]:
            if transcript := _stt_step(media_key, stt_events, tools_called):
                transcripts.append(transcript)
    text = "\n".join(part for part in (text, *transcripts) if part.strip())

    cur.execute(
        """INSERT INTO diagnostic_turns
           (session_id, turn_index, role, content, media_refs, idempotency_key)
           VALUES (%s, %s, 'user', %s, %s, %s)""",
        (session_id, idx, text, media_keys or [], idempotency_key),
    )
    # agent turn row exists BEFORE events stream (they reference it);
    # content/tools_called are finalized after the backend finishes (spec D4)
    agent_turn_id = cur.execute(
        """INSERT INTO diagnostic_turns (session_id, turn_index, role)
           VALUES (%s, %s, 'agent') RETURNING id""",
        (session_id, idx + 1),
    ).fetchone()["id"]
    conn.commit()

    if worker is None:
        backend_events = _scripted_events(
            cur, text, visual_media, machine_context, idx + 1, tools_called
        )
    else:
        backend_events = _hermes_events(
            cur, worker, session_id, text, visual_media, machine_context, idx, tools_called
        )

    persisted = _persist_event_stream(
        conn, cur, session_id, agent_turn_id, chain(stt_events, backend_events)
    )

    cur.execute(
        "UPDATE diagnostic_turns SET content = %s, tools_called = %s WHERE id = %s",
        (_primary_content(persisted), Jsonb(tools_called), agent_turn_id),
    )
    _persist_hypotheses(
        cur,
        session_id,
        agent_turn_id,
        idx + 1,
        [ev for ev in persisted if isinstance(ev, HypothesisEvent)],
        evidence_text=text,
        evidence_media_ref=media_keys[0] if media_keys else None,
    )
    conn.commit()
    return str(agent_turn_id)


def _persist_event_stream(conn, cur, session_id, agent_turn_id, events) -> list[Event]:
    """ONE persistence loop for both backends: commit per event (live SSE tail),
    safety gate (spec D5), guaranteed trailing done — agent failure never 500s."""
    persisted: list[Event] = []
    gated = False
    done_seen = False

    def _persist(ev: Event) -> None:
        cur.execute(
            """INSERT INTO diagnostic_turn_events (turn_id, event_index, event_type, event_data)
               VALUES (%s, %s, %s, %s)""",
            (agent_turn_id, len(persisted), ev.type, Jsonb(ev.model_dump(exclude_none=True))),
        )
        conn.commit()
        persisted.append(ev)

    try:
        for ev in events:
            if done_seen:
                break
            if gated and not isinstance(ev, DoneEvent):
                # physical-safety approval gate: no follow-up steps stream until
                # the technician confirms (their next turn)
                observability.log_agent_error(
                    session_id, "suppressed_event", f"{ev.type} after high-safety guidance"
                )
                continue
            if isinstance(ev, DoneEvent):
                done_seen = True
                if gated:
                    ev = DoneEvent(status="awaiting_user_input")
            elif isinstance(ev, GuidanceEvent) and ev.safety_level == "high":
                gated = True
            _persist(ev)
    except Exception as exc:  # backend/DB failure mid-stream: close the turn cleanly
        observability.log_agent_error(session_id, "worker_error", f"event stream failed: {exc}")
        _persist(
            ThinkingEvent(content="Interner Fehler im Diagnose-Agenten — bitte erneut senden.")
        )
    if not done_seen:
        _persist(DoneEvent(status="awaiting_user_input"))
    return persisted


def _primary_content(events: list[Event]) -> str | None:
    """The agent turn's utterance: the question the technician must answer,
    else actionable guidance, else the diagnosis explanation."""
    for kind in (QuestionEvent, GuidanceEvent, DiagnosisEvent):
        for ev in reversed(events):
            if isinstance(ev, kind):
                return ev.content if hasattr(ev, "content") else ev.explanation
    return None


def _check_media_tenant(tenant_id: str, media_keys: list[str]) -> None:
    """Trust boundary (spec D6): turn media must carry the session's tenant
    prefix. Bare pre-2.5 keys stay valid for the dev tenant."""
    for key in media_keys:
        if "/" in key:
            if not key.startswith(f"{tenant_id}/"):
                raise ValueError(f"media_key {key!r} does not belong to tenant {tenant_id!r}")
        elif tenant_id != "dev":
            raise ValueError("bare media keys are only valid for the dev tenant")


# --- hermes backend (Feature 2.5) ---


def _hermes_events(
    cur, worker, session_id, text, visual_media, machine_context, user_turn_index, tools_called
):
    if machine_context:
        parts = [f"{k}={v}" for k, v in machine_context.items() if v]
        if parts:
            text = f"{text}\n\n[Maschinenkontext] {', '.join(parts)}"
    turn_op = {
        "op": "turn",
        "text": text,
        "media": visual_media,
        "context": _respawn_context(cur, session_id)
        if worker.turns_seen == 0 and user_turn_index > 0
        else None,
    }
    worker.turns_seen += 1
    session_media = _session_media(cur, session_id)
    return hermes_backend.iter_turn_events(
        cur, worker, turn_op, session_media, user_turn_index + 1, tools_called
    )


def _respawn_context(cur, session_id) -> str:
    rows = cur.execute(
        """SELECT role, content FROM diagnostic_turns
           WHERE session_id = %s AND content IS NOT NULL
           ORDER BY turn_index DESC LIMIT %s""",
        (session_id, _MAX_CONTEXT_TURNS),
    ).fetchall()
    lines = "\n".join(f"{r['role']}: {r['content']}" for r in reversed(rows))
    return f"[Bisheriger Diagnose-Verlauf — Sitzung wird fortgesetzt]\n{lines}"


def _session_media(cur, session_id) -> set[str]:
    rows = cur.execute(
        "SELECT media_refs FROM diagnostic_turns WHERE session_id = %s", (session_id,)
    ).fetchall()
    return {key for r in rows for key in (r["media_refs"] or [])}


# --- scripted backend (Feature 1.3 stub, kept as deterministic mock — spec 2.5 D7) ---


def _scripted_events(cur, text, visual_media, machine_context, agent_turn_index, tools_called):
    events, tools, _question = _scripted_diagnosis(
        cur, text, [m["key"] for m in visual_media], machine_context, agent_turn_index
    )
    tools_called.extend(tools)
    yield from events


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
    # ponytail: SELECT-then-INSERT — writes stay single-flight per session (the
    # 2.5 worker lock serializes hermes turns; scripted is per-request)
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
        # family filter deliberately None: broadest exact-code search; variant
        # strings are canonicalized inside the tool anyway (2.8 alias map)
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
    """Hybrid slow path (spec 2.2 D5): no exact code hit -> full-text candidate
    search; hits become candidate-alarm hypotheses, zero hits fall back to the
    photo ask."""
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


def _split_media(media_keys: list[str]) -> tuple[list[str], list[dict]]:
    """Route by stored MIME (trustworthy — the presign signs it, 1.2). Keys
    whose type can't be read go to the visual path, whose failure handling
    already reports them as failure-summary tool_results."""
    audio: list[str] = []
    visual: list[dict] = []
    for key in media_keys:
        try:
            kind = storage.head_content_type(key)
        except Exception:
            kind = ""
        if kind.startswith("audio/"):
            audio.append(key)
        else:
            visual.append({"key": key, "content_type": kind or "unknown"})
    return audio, visual


def _stt_step(media_key: str, events: list[Event], tools_called: list[dict]) -> str:
    """Feature 2.4: voice note in the turn → STT tool, streamed as tool events.
    Failures (bad recording, ffmpeg, S3 down) become a failure-summary
    tool_result — broken audio must never 500 the turn."""
    args = {"media_key": media_key}
    events.append(ToolCallEvent(tool="stt", args=args))
    try:
        result = stt.transcribe(media_key)
        summary = f"transcript (confidence {result['confidence']}): {result['transcript']}"
        events.append(ToolResultEvent(tool="stt", result_summary=summary, raw_result=result))
        transcript = result["transcript"]
    except Exception as exc:
        summary = f"transcription failed: {exc}"
        events.append(ToolResultEvent(tool="stt", result_summary=summary))
        transcript = ""
    tools_called.append({"tool": "stt", "args": args, "result_summary": summary})
    return transcript


def _vision_step(media_key: str, events: list[Event], tools_called: list[dict]) -> list[str]:
    """Feature 2.3 (scripted backend): photo in the turn → vision tool, streamed
    as tool events. The hermes backend calls vision itself via RPC (2.5 D2).
    Failures become a failure-summary tool_result — a bad photo must never 500
    the turn."""
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
    # family, and first-sighting-wins would lock it in (spec 2.3 D7)
    return result["detected_codes"] if result else []


def _candidate_codes(text: str, machine_context: dict | None, vision_codes: list[str]) -> list[str]:
    codes = []
    if machine_context and machine_context.get("error_code"):
        codes.append(machine_context["error_code"].strip())
    codes += ErrorCodeLookup.extract_codes(text)
    codes += vision_codes
    return list(dict.fromkeys(codes))
