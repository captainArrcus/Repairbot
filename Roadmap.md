Goal: deliver an MVP that proves the mission thesis (multimodal, iterative diagnostic loop + Data Bridge) for SINUMERIK CNC machines in 12 weeks. This roadmap translates the cofounder's phases into concrete features, with file-level entry points, exact APIs, test commands and acceptance criteria so a coding agent or developer can start implementing immediately.

> **Architecture change (Juli 2026, Techstack v3):** the agent backbone is now an **embedded hermes-agent** (`run_agent.AIAgent` from NousResearch/hermes-agent, pinned commit) instead of smolagents. Consequences for this roadmap: Feature 0.2 becomes the hermes embed spike; Feature 2.5 loses the CodeAgent Docker sandbox (tool-calling only — containment is tool allowlist + egress isolation); new Feature 2.7 adds the Learning Pipeline (trajectories, skills, memory → cloud curation); all sessions become tenant-scoped (central multi-tenant cloud).
>
> **Status:** Features 0.0, 0.1, 0.2, 1.0, 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5 and 2.7 are COMPLETE (1.4 field-tested on phone 2026-07-19 — full flow works). Feature 2.6 (mobile app) is BUILT and dev-verified — React Native + Expo locked; Expo Go phone run + APK build are the remaining field steps (see spec). First app field test (2026-07-19) produced Feedback round 1 → Features 2.9–2.11 (chat view, transcript echo, hermes-in-the-field); 2.9, 2.10 and 2.11 are BUILT and dev-verified (2.10 live-verified against the real STT pipeline; 2.11 live-verified with a 2-turn hermes session through the flipped default). One on-phone field run covers the 2.9/2.10/2.11 runbook items together (see 2.11 spec FINDINGS). Knowledge-layer winner: **hybrid** (exact error-code lookup fast-path + LLM over narrowed candidates) — see `Repair_Logic_Agent/knowledge_spike/FINDINGS.md`. Hermes embed spike: **GO** — all four questions pass; tool allowlist must include hermes' learning tools (`skills_*`, `memory`) — see `specs/2026-07-12_0242_feature_0.2_hermes_embed/FINDINGS.md`. Project skeleton + dev infra (Postgres 16, MinIO, Langfuse v3, CI): see `specs/2026-07-12_1518_feature_1.0_project_skeleton/FINDINGS.md`.

Quick conventions used below

    Repo names (two-repo discipline):
        repair_logic_agent — backend, agent, tools, knowledge
        repairropi_app — frontend prototypes and later mobile app
    Owners: BE (backend engineer), ML (ML/agent engineer), FE (mobile/web engineer), QA, PM
    Estimated effort: rough person-hours per feature
    Each feature lists exact files to create, endpoint/function signatures, commands to run and acceptance tests.

PHASE 0 — Intelligence Spike (Weeks 1–2)
Focus: time-to-first-test. Produce a golden dataset, test three knowledge approaches, and produce a CLI agent that can be used immediately on a laptop.

Feature 0.0 — Golden dataset & fixtures (owner: PM + QA) — 8h

    Objective: collect and encode 20 gold cases and supporting assets.
    Deliverables (repair_logic_agent/knowledge_spike/):
        golden_cases.yaml — format below
        docs/ (20 relevant PDF pages or manual extracts)
        images/ (photos for each case if available)
    golden_cases.yaml (exact format required by scripts)
        id: sin_001
        controller: "SINUMERIK_840D"
        error_code: "AL 309"
        symptom_text: "Rattling sound when jogging X-axis"
        ground_truth_labels: ["ball_screw_bearing", "x_axis"]
        preferred_manual_page: "dmgmori_ch12_p84.jpg" (optional)
    Acceptance: golden_cases.yaml present and validated by QA script (repair_logic_agent/knowledge_spike/validate_fixtures.py).
    Test: python knowledge_spike/validate_fixtures.py --cases knowledge_spike/golden_cases.yaml

Feature 0.1 — Knowledge-layer shootout scripts (owner: ML) — 40h

    Objective: implement three small prototypes: RAG, VLM page-feed, and LLM-wiki; evaluate Top-3 recall on the golden set.
    Repo path: repair_logic_agent/knowledge_spike/
    Files to create:
        rag_spike.py
        vlm_pagefeed_spike.py
        wiki_compile_spike.py
        evaluate_spikes.py (runs each approach over golden_cases.yaml and computes top-k recall)
        requirements.txt (minimal libs: pytesseract, pdf2image, faiss-cpu, sentence-transformers or chosen embedder, litellm client)
    Implementation steps (exact):
        rag_spike.py: implement ingest_pdfs(pdf_dir) → chunk_texts(pdf_page_images), embed_chunks(embed_model), index_faiss(index_dir). Implement query_rag(query, top_k) → return chunk_ids with text.
            function signatures:
                def ingest_pdfs(pdf_dir: str) -> List[PageChunk]
                def build_embeddings(chunks: List[PageChunk], model: str) -> None
                def query_rag(query: str, top_k: int=3) -> List[SearchResult]
        vlm_pagefeed_spike.py: page_image_feed(query): sends page images to LiteLLM multimodal model (or a mocked VLM) and returns ranked page ids.
            def query_vlm_pages(query: str, page_images: List[bytes], top_k: int=3) -> List[SearchResult]
        wiki_compile_spike.py: simple LLM-driven compile: for each manual → ask LLM to produce Markdown article per machine/section. Save compiled_articles/*.md and query via LLM prompt.
            def compile_wiki(docs_dir: str) -> None
            def query_wiki(query: str, top_k:int=3) -> List[ArticleResult]
        evaluate_spikes.py: loads golden_cases.yaml and runs each method; prints top-1/top-3 recall; writes results to knowledge_spike/results.json.
    Acceptance: produce a short report; if Top-3 recall >= 85% for any approach, mark as winner. If none reach 85% choose hybrid: structured error-code DB + page-feed fallback.
    Test:
        python knowledge_spike/evaluate_spikes.py --cases knowledge_spike/golden_cases.yaml --output knowledge_spike/results.json

Feature 0.2 — hermes embed spike + CLI diagnostic agent (owner: ML + BE) — 32h

    Objective: prove the hermes-agent bet end-to-end on a laptop BEFORE any API work. This is the
    make-or-break spike from Techstack v3 — if we fight the framework here, we drop to the escape
    hatch (LiteLLM tool-calling + plain loop) and the rest of the roadmap is unchanged.
    Repo path: repair_logic_agent/agents/
    Files to create:
        hermes_service.py — embeds run_agent.AIAgent (pinned commit), registers exactly one tool:
            knowledge_retrieval(query) mapping to the hybrid winner from Feature 0.1
        run_cli.py — starts the agent in interactive mode
    Requirements:
        AIAgent configured against a LiteLLM proxy endpoint (OpenAI-compatible base_url),
        Gemini 2.5 Flash primary / Claude fallback.
        HERMES_HOME pointed at a dedicated directory (tenant-isolation pattern from day one).
        NO hermes built-in tools registered (no terminal, no browser) — allowlist of one.
    Minimal function signatures:
        class HermesAgentService:
            def start_session(self, session_id: str) -> None
            def handle_user_turn(self, text: str, media_paths: List[str]=None) -> List[StepEvent]
    Spike must answer (write findings to specs/):
        1. Does streaming expose enough structure to map to our typed SSE events (thinking,
           hypothesis, question, tool_call, ...)?
        2. Do skills/memory work when driven purely as a library (no CLI/gateway session store)?
        3. Does per-HERMES_HOME isolation hold (two parallel sessions, zero state bleed)?
        4. Can we export a trajectory of the session in hermes' trajectory format?
    Acceptance:
        Run: python run_cli.py
        Example interaction:
            User types: "Controller: SINUMERIK 840D, AL 309. Rattling when jogging X."
            Agent streams: thinking -> hypothesis (JSON) -> question ("Check axial play, tell me mm") -> etc.
        CLI logs must include typed step JSON per step.
        GO/NO-GO decision on hermes documented in specs/ with the four answers above.

PHASE 1 — API & "Wizard of Oz" UI (Weeks 3–4)
Goal: get a smartphone in front of a machine and run the first field tests. Keep UI dirty — web prototype or Gradio.

Feature 1.0 — Project skeleton & dev infra (owner: BE) — 8h — **[DONE 2026-07-12]**

    Repo: repair_logic_agent
    Files to create:
        pyproject.toml (core dependencies; hermes-agent stays in its dedicated venv — see spec D2)
        infra/docker-compose.yml (postgres:16, MinIO dev, Langfuse v3 stack incl. clickhouse + redis)
        app/main.py (FastAPI app skeleton)
        app/config.py (env loader)
        .github/workflows/ci.yml (ruff + pytest; lives at git root — single-repo layout)
    Acceptance: docker-compose up starts services; FastAPI health check returns 200 at /health
    Spec + acceptance evidence: specs/2026-07-12_1518_feature_1.0_project_skeleton/

Feature 1.1 — DB migration and seeded error-code table (owner: BE) — 12h — **[DONE 2026-07-12]**

    Repo: repair_logic_agent/db/migrations/001_create_schema.sql (exact SQL provided)
    Add seed script: db/seeds/seed_error_codes.sql with 20 SINUMERIK codes and descriptions
        (15 from Research_Data curated alarm DB + 5 golden-case/standard codes; see spec D3)
    Required exact SQL (create, insert) — use the schema from the architecture doc (diagnostic_sessions incl. tenant_id, diagnostic_turns, hypotheses, hypothesis_updates, session_outcomes) + diagnostic_turn_events table:
        ADD table diagnostic_turn_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        turn_id UUID REFERENCES diagnostic_turns(id),
        event_index INT,
        event_type TEXT,
        event_data JSONB,
        created_at TIMESTAMPTZ DEFAULT now()
        );
    error_codes columns (defined in spec D2, DDL in Techstack schema section): controller_family,
        code (stored as printed in manual; normalization = Feature 2.2), category, severity,
        message_de/en, probable_causes/recommended_actions/related_components/
        discriminating_questions/spare_part_refs (JSONB), manual_reference, software_version, source
    Acceptance (commands corrected — service `postgres`, DB `repair`, file streamed; spec D1):
        docker compose -f infra/docker-compose.yml exec -T postgres psql -U postgres -d repair -v ON_ERROR_STOP=1 < db/migrations/001_create_schema.sql
        docker compose -f infra/docker-compose.yml exec -T postgres psql -U postgres -d repair -c "select count(*) from error_codes;" => 20 seeded rows.
    Spec + acceptance evidence: specs/2026-07-12_1805_feature_1.1_db_migration/

Feature 1.2 — Presigned upload endpoint (owner: BE) — 8h — **[DONE 2026-07-12]**

    Endpoint: POST /api/v1/media/upload-url
    Input JSON: { "filename": "panel.jpg", "content_type": "image/jpeg", "purpose": "turn_media" }
        content_type allowlisted to image/* and audio/* (422 otherwise); filename/purpose
        accepted but not persisted yet (spec D2/D3)
    Response JSON: { "upload_url": "...", "media_key": "uuid" }
        object key == media_key (retrieval invariant for vision/STT); since Feature 2.5
        media_key = "<tenant>/<uuid>" (X-Tenant-Id header, spec 2.5 D6)
    Implementation files:
        app/api/media.py → function create_presigned_upload()
        app/services/storage.py → function generate_presigned_put(media_key, content_type)
    Acceptance (curl corrected — Content-Type is signed, header required on PUT; spec D1):
        curl -X POST http://localhost:8000/api/v1/media/upload-url -H 'Content-Type: application/json' -d '{"filename":"a.jpg","content_type":"image/jpeg"}'
        use curl -T panel.jpg -H "Content-Type: image/jpeg" "<upload_url>" and then verify via storage GET exists.
    Spec + acceptance evidence: specs/2026-07-12_1819_feature_1.2_presigned_upload/

Feature 1.3 — FastAPI wrapper + SSE stream (owner: BE + ML) — 24h — **[DONE 2026-07-12]**

    Endpoints to implement:
        POST /api/v1/sessions → create session (returns session_id; optional body machine_family/controller_family/metadata; tenant_id='dev' until Feature 2.5)
        POST /api/v1/sessions/{id}/turns → submit user turn (idempotent via idempotency_key —
            migration 002 unique index; returns the AGENT turn id = replay handle; spec D6/D9)
        GET /api/v1/sessions/{id}/stream → SSE event stream (Last-Event-ID resume; wire id =
            "{turn_index}.{event_index}", session-monotonic; spec D4)
        GET /api/v1/sessions/{id}/turns/{tid}/events?after={event_index} → replay (integer
            per-turn cursor, not event uuid — spec D5)
    Files:
        app/api/sessions.py
        app/models/events.py (Pydantic step schemas — see below; plus ThinkingEvent/DoneEvent
            and GuidanceEvent.safety_level per the canonical SSE section, spec D8)
        app/services/agent_service.py (AgentService stub that converts agent steps to events and persists them)
            Stub = scripted diagnostician over the seeded error_codes table (spec D1); the
            embedded hermes AIAgent replaces the internals in Feature 2.5.
        db/migrations/002_turn_idempotency.sql
    SSE: manual text/event-stream framing over StreamingResponse (EventSourceResponse is
        sse-starlette, not FastAPI — no new dependency, spec D2). Events are persisted to
        diagnostic_turn_events BEFORE streaming; the stream is a DB replay + polling tail
        (spec D3), so reconnect/replay is free.
    Pydantic event schemas to create (exact names and fields):
        HypothesisEvent
            id: str
            hypothesis_id: str
            description: str
            confidence: float (0-1)
            introduced_at_turn: int
            eliminated: bool (optional)
        QuestionEvent
            id: str
            content: str
            evidence_type: str (one of: photo, audio, tactile, numeric, text)
            required_format: Optional[str] (e.g., "mm", "on/off", "image_of_panel")
        ToolCallEvent / ToolResultEvent
            id: str
            tool: str
            args: dict
            result_summary: str
            raw_result: dict (optional)
        DiagnosisEvent
            id: str
            hypothesis_id: str
            confidence: float
            explanation: str
        GuidanceEvent
            id: str
            step_index: int
            content: str
    Acceptance:
        Start server, create session, POST turn -> connect with curl:
            curl -N http://localhost:8000/api/v1/sessions/{id}/stream
        SSE returns events with event: hypothesis \n id: 1.3 \n data: {...}\n\n etc.
    Spec + acceptance evidence: specs/2026-07-12_1835_feature_1.3_sse_api/

Feature 1.4 — Dirty web prototype (owner: FE) — 24h — **[DONE 2026-07-12; field-tested on phone 2026-07-19]**

    Repo: RepairRöpiApp/web_prototype/ (real frontend dir; spec D1)
    Files:
        index.html (single page)
        app.js (JS to capture photo, request presigned URL, upload, POST turn, open SSE)
        + backend: CORSMiddleware allow-all in app/main.py (page :8080 → API :8000 is
          cross-origin; tighten in Feature 2.5/3.1 — spec D3)
    Implementation steps:
        page shows "Start session" button -> creates session via POST /api/v1/sessions
        camera capture input (input type="file" accept="image/*" capture="environment")
        request presigned URL, PUT image, POST turn with media_key, open SSE to stream events
        UI renders events: thinking, hypothesis list, questions with primary CTA (take photo)
    Acceptance (FIRST FIELD TEST):
        Open web link on phone, take photo of control, call flow returns streamed events and asks a question.
    Test: open file via a simple static server: python -m http.server 8080 in RepairRöpiApp/web_prototype and visit via phone on same LAN.
        Field-test env (spec D5): S3_ENDPOINT_URL=http://<laptop-lan-ip>:9000 + uvicorn
        --host 0.0.0.0 — presigned URLs embed the backend's S3 endpoint, localhost is
        unreachable from the phone.
    Spec + acceptance evidence: specs/2026-07-12_1946_feature_1.4_web_prototype/

PHASE 2 — Foundation & App (Weeks 5–8)
Focus: productionize the core pipeline, add audio, structured traces, guardrails (tool allowlist, egress isolation, tenant isolation), learning pipeline, and build native app.

Feature 2.1 — Data Bridge completion & export (owner: BE) — 24h — **[DONE 2026-07-12, dev-verified]**

    Implement full session persistence:
        diagnostic_sessions, diagnostic_turns, hypotheses, hypothesis_updates, diagnostic_turn_events, session_outcomes tables with SQL migrations
        (tables shipped in Feature 1.1 migration 001 — no new migration; spec D1.
        hypotheses/hypothesis_updates written by agent_service at event time; spec D2)
    Outcome write path (added, not in original Roadmap — spec D3, user-ratified):
        POST /api/v1/sessions/{id}/outcome → upserts session_outcomes, sets
        diagnostic_sessions.status, resolves/creates the final-diagnosis hypothesis
    Implement export endpoint:
        GET /api/v1/sessions/{id}/export → returns training-ready JSON:
        {
        session_id,
        machine_context,
        initial_observation: {media_keys, symptom},
        diagnostic_chain: [ {turn_index, events: [...] } ... ],
        final_diagnosis: {...},
        outcome: {...}
        }
    Files:
        app/services/traces.py (assemble export)
        app/api/sessions.py (add export route)
    Acceptance:
        Run session in dev -> GET export → JSON validates against training schema (tests/traces/test_export_schema.py)
    Spec + acceptance evidence: specs/2026-07-12_2212_feature_2.1_data_bridge_export/

Feature 2.2 — ErrorCodeLookupTool + KnowledgeRetrievalTool (owner: ML + BE) — 24h — **[DONE 2026-07-18]**

    ErrorCodeLookupTool:
        Implements exact lookup in SQL table error_codes(controller_family, code) -> returns the
        full error_codes row incl. manual_reference + spare_part_refs, confidence=1.0
        (column is manual_reference, not manual_section_id — 1.1 DDL; spec D2)
        Query-time normalization lives here (Techstack): "al-309"/"AL309"/"309" → "AL 309",
        "f 07011" → "F07011"; controller_family=None searches all families (spec D2)
        File: app/tools/error_code_lookup.py (class ErrorCodeLookup)
        Function signature:
            def lookup(controller_family: str | None, code: str) -> Optional[dict]
    KnowledgeRetrievalTool:
        Interface per KnowledgeLayer Protocol: search_semantic, lookup_error_code, get_page_image, get_compiled_article
        File: app/tools/knowledge_layer.py (class KnowledgeRetrieval)
        search_semantic = Postgres full-text search over error_codes, german+english configs,
        no new dependency (spec D3 — embeddings deferred until the PDF corpus lands);
        get_page_image raises / get_compiled_article returns None until a document corpus /
        wiki pipeline exists (spec D4)
    Acceptance:
        Agent can call both tools and incorporate tool_result events into event stream.
        (verified live: exact-code turn → error_code_lookup events + cause hypotheses;
        symptom-only turn → knowledge_retrieval events + candidate-alarm hypotheses, spec D5)
    Spec + acceptance evidence: specs/2026-07-18_1740_feature_2.2_knowledge_tools/

Feature 2.3 — VisionAnalysisTool (owner: ML) — 40h — **[DONE 2026-07-18, dev-verified]**

    Implement pragmatic pipeline:
        Fetch image from S3 (media_key)
        Preprocess: enhance contrast, coarse rotate (best-of-four OCR passes — tesseract OSD
        bails on panel crops; autocrop/fine deskew deferred until real field photos, spec D2)
        OCR via pytesseract to extract numeric/error-code-like strings (2.2 extract_codes)
        Controller classification: OCR keyword heuristic first; the small LiteLLM multimodal
        call (gemini-2.5-flash) only when OCR sees no brand (spec D3). Brand-level result
        (SINUMERIK / HEIDENHAIN / FANUC) — exact-family mapping stays the open 2.2-D2 issue.
        Return: detected_controller, detected_codes[], annotated_images[] (S3 keys), confidence
    File: app/tools/vision_analysis.py
    Function signature:
        def analyze(media_key: str) -> dict
    Acceptance:
        With test images, detect controller family correctly >= 80% on seed images (measured by
        tests/vision/test_vision_expectations.py — 6/6 on synthetic seed renders; no real panel
        photos exist yet, real-photo validation is a field-test runbook item, spec D8)
    Agent integration: when user uploads a photo, agent calls VisionAnalysisTool and streams a tool_call / tool_result event.
        (verified live: presign-uploaded panel photo → vision_analysis events → detected code
        walks the 2.2 error_code_lookup fast path → AL 309 hypotheses, spec FINDINGS)
    Forward pointer: annotated_images[] is the seed of the visual-grounding track (Phase 4.2/4.3) — keep the annotation output path (draw → S3 key) reusable.
    Spec + acceptance evidence: specs/2026-07-18_1759_feature_2.3_vision_analysis/

Feature 2.4 — STT (Whisper) + audio preprocessing (owner: ML + BE) — 24h — **[DONE 2026-07-18, dev-verified]**

    Audio uploads already flow through POST /api/v1/media/upload-url (1.2); STT runs inline in
        the synchronous turn pipeline like every other tool — background job deferred to the
        2.5 agent restructuring (spec D1)
    File: app/tools/stt.py
    Steps:
        route turn media by stored MIME (audio/* → STT, rest → vision; spec D7), fetch from S3
        noise reduction: noisereduce spectral gating, softened to prop_decrease=0.75 —
        full-strength gating measurably destroys Whisper's noise-robust input (spec D3)
        call whisper — WHISPER_MODEL config, large-v3 default; no-GPU dev boxes run base
        (spec D2) — forced German (STT_LANGUAGE)
        return transcript with word timestamps and confidence (mean word probability)
    Acceptance:
        For sample noisy audio, WER measured and logged (0.38 at 10 dB SNR, base model, committed
        gTTS sample — no field recordings exist yet, spec D5/D6); transcripts appear as user-turn
        text when user uploads audio.
        (verified live: presigned voice note → stt tool_call/tool_result events → transcript
        persisted as user-turn content → spoken "AL309" walks the 2.2 fast path to hypotheses)
    Test:
        tests/stt/test_transcribe_sample.py
    Spec + acceptance evidence: specs/2026-07-18_1825_feature_2.4_stt/

Feature 2.5 — AgentService: embedded hermes AIAgent + guardrails + Pydantic step enforcement (owner: ML + BE) — 40h — **[DONE 2026-07-18, live-verified incl. egress-isolated docker run]**

    Implemented in app/services/agent_service.py (turn shell, both backends) +
    app/services/hermes_backend.py (worker mgmt, RPC, validation) + agents/hermes_worker.py
    (runs in .venv-hermes — the two-venv reality makes the agent a worker PROCESS per
    session, JSONL over stdio; spec 2.5 D1). stream_events stays the SSE DB-tail in the
    API layer (HTTP-lifecycle-bound; spec D10) — agent_service owns production/persistence,
    now committed per event so SSE streams mid-turn.
    Key points (as built):
        Embed run_agent.AIAgent (hermes-agent, pinned commit) — productionized 0.2 spike
        Domain tools execute PARENT-side via stdio RPC (spec D2): the agent process holds
        no DB/S3 credentials; its only egress need is the LLM endpoint (+ models.dev)
        Tool allowlist: 4 domain tools (vision_analysis, error_code_lookup,
        knowledge_retrieval, repair_web_search — renamed, hermes name-gates its own
        "web_search" by config, spec FINDINGS #1) + hermes' 4 learning-loop tools
        (memory, skills_list, skill_view, skill_manage — 0.2 finding, ratified).
        No terminal, no browser, no MCP, no subagents — never registered; the worker
        asserts the exposed set and the parent verifies the handshake (breach → 503).
        Per-tenant HERMES_HOME + tenant CWD (trajectories); Postgres stays source of truth;
        tenant via X-Tenant-Id header (default "dev") until auth; media_key tenant-prefixed
        Parent-side Pydantic validation; invalid output sanitized + Langfuse error
        (app/services/observability.py) — raw output never forwarded
        guidance safety_level=high gates follow-up steps (suppressed + logged) until the
        technician's confirming turn
        Scripted 1.3 diagnostician KEPT as deterministic backend (AGENT_BACKEND=scripted
        default — CI/golden-harness mock, spec D7); dev opts in via AGENT_BACKEND=hermes
        LiteLLM proxy deferred to 3.1 (direct endpoint + env swap, user-ratified spec D11)
    Acceptance (all verified — spec FINDINGS):
        Events persisted to diagnostic_turn_events, SSE streams valid typed events (live
        3-turn AL-309 session: exact-hit → hypotheses → elimination → diagnosis 0.95 →
        high-safety LOTO guidance), cross-tenant parallel zero-bleed test green.
    Safety (as built):
        Egress isolation per hermes docs/security/network-egress-isolation.md:
        infra/docker-compose.agent.yml — worker container on an internal network (no
        default route), squid proxy allowlists ONLY LLM endpoint domains + models.dev
        (S3/Langfuse egress is the parent's, not the agent's — tool RPC, spec D2/D8).
        Verified by tests/agent/test_egress_isolation.py + a live diagnostic turn through
        the isolated container (AGENT_RUNNER=docker).
    Spec + acceptance evidence: specs/2026-07-18_2246_feature_2.5_agent_service/

Feature 2.6 — Mobile App V1 — build the real app (owner: FE + PM) — 80h — **[BUILT 2026-07-19, dev-verified; on-phone Expo Go run + APK on rugged device = field runbook, spec FINDINGS]**

    Framework LOCKED (spec D1, Techstack checklist closed): React Native + Expo (SDK 57),
    TypeScript strict. Rationale: builder = coding agent on a Node-only machine; Expo Go
    delivers the on-phone dev loop with zero Android SDK (the 1.4 field-test pattern).
    Target: Android (ruggeds); iOS optional later.
    Repo path: RepairRöpiApp/mobile/ (real dir)
    Key screens (as built):
        SessionList / NewSession — phone-local list (AsyncStorage; no backend index needed, spec D10)
        SessionScreen (SSE stream view): status/thinking row, hypothesis panel, question card
        (primary CTA highlights the requested evidence type), evidence submission (photo,
        audio, numeric/text), verification + outcome card (POST /outcome — Data-Bridge
        closure from the phone, spec D8), diagnosis card, guidance list with high-safety
        confirm CTA (2.5 safety-gate contract, spec D7)
    Required features (as built):
        Presigned upload flow (presign + blob PUT, signed Content-Type)
        SSE client (react-native-sse) — screen-owned reconnect w/ fresh Last-Event-ID;
        session restore = full replay through a monotonic-id reducer (spec D3/D4 —
        GET /sessions/{id} deliberately NOT built)
        Evidence widgets: system camera (expo-image-picker), audio recorder w/ live
        metering as ambient-noise indicator (expo-audio, m4a), decimal keyboard +
        required_format hint on numeric questions
        Offline resilience: single pending-turn queue in AsyncStorage, per-media
        media_key write-back (uploads survive retries), fixed idempotency_key,
        8s auto-retry; 409 retries, 422/404 drops (spec D5)
    Files / components (as built, .tsx not .js):
        App.tsx (two screens, conditional render — no navigation lib, spec D2)
        screens/SessionListScreen.tsx, screens/SessionScreen.tsx
        components/HypothesisList.tsx, components/theme.ts
        services/api.ts, services/events.ts (+ node --test suite), services/store.ts
        BUILD.md (Expo Go loop; APK via EAS cloud OR expo prebuild + gradle)
    Acceptance:
        Installable APK runs on rugged Android and can run end-to-end test: capture photo, upload, create turn, receive SSE events, respond to question, receive diagnosis, upload verification photo, export session shows trace.
        Status: flow implemented; contract dev-verified (typecheck, 5/5 reducer tests,
        Metro android bundle, live smoke: scripted-backend session replayed through the
        real reducer). APK BUILT 2026-07-19 via EAS cloud (install link in spec
        FINDINGS; repo-root .easignore keeps backend/tenant data out of the upload).
        Remaining: rugged-device end-to-end field test.
    Spec + acceptance evidence: specs/2026-07-19_0309_feature_2.6_mobile_app/

Feature 2.7 — Learning Pipeline v1: field → cloud (owner: ML + BE) — 32h — **[DONE 2026-07-19, live-verified end to end]**

    Objective: implement the Techstack v3 Learning Pipeline — every session's learnings become
    cloud assets, tenant-isolated, with a curation gate before anything is shared.
    Files (as built):
        app/services/learning_pipeline.py (harvest + queue/promote/reject CLI)
        db/migrations/003_learning_tables.sql (skill_curation_queue, trajectory_refs)
    Trigger: POST /api/v1/sessions/{id}/outcome — session closure drops the worker and runs
        the harvest best-effort (a pipeline failure never fails the outcome POST; spec D1).
        Sessions abandoned without an outcome are not harvested in v1.
    Three streams (as built):
        1. Trajectories: per-session by construction — the worker CWD is session-scoped
           (<tenant_home>/trajectories/<session_id>/; hermes appends to CWD, 0.2 finding #5).
           Uploaded as raw gzipped ShareGPT JSONL to
           learning/<tenant>/trajectories/<sid>.jsonl.gz + trajectory_refs row.
           trajectory_compressor deliberately NOT wired (spec D3): it only rewrites
           trajectories above its token budget and needs transformers + an LLM summarizer —
           run it as a batch step when Phase 4 fine-tuning prep sees over-budget trajectories.
        2. Skills: post-session scan of HERMES_HOME/<tenant>/skills/ → content-hash-deduped
           rows in skill_curation_queue (pending_review, content stored in the row).
           Promotion: python -m app.services.learning_pipeline promote <id> → fleet base
           (FLEET_SKILLS_DIR), synced into every tenant home at worker start (own skill wins;
           unmodified fleet copies are not re-queued).
        3. Memory: memories/ → learning/<tenant>/memory.tar.gz (latest snapshot). Never shared.
    Guardrail (non-negotiable):
        Nothing crosses a tenant boundary without curation. Automated tenant-string scrub
        blocks promotion + human runs the CLI (NER/PII scrub deferred until volume demands).
        Cross-tenant test green: tests/agent/test_learning_pipeline.py.
    Acceptance (all verified — spec FINDINGS):
        Live hermes session → trajectory in MinIO + ref row; synthetic skill queued on outcome;
        promotion → fleet base → tenant-B session has it in its skills prompt index.
    Spec + acceptance evidence: specs/2026-07-19_2229_feature_2.7_learning_pipeline/

Feature 2.8 — Controller-family normalization (owner: BE) — 4h — **[DONE 2026-07-19]**

    Closes the 2.2-D2 gap that bit twice (2.3: brand-level vision result; 2.5 finding #2:
    exact lookup missed because the model says "SINUMERIK" while seeds store
    "SINUMERIK_840D_sl" — the family=None retry masks it, doesn't solve it).
    Canonical family-alias map (data, not code): brand + variant strings → seeded
    controller_family values, owned by app/tools/error_code_lookup.py alongside the
    existing code normalization.
    As built: FAMILY_ALIASES + _canonical_family() applied inside lookup() — one guard,
        every caller (scripted agent_service, hermes dispatcher, KnowledgeRetrieval
        delegate) covered. Unmapped families pass through unchanged (no silent widening).
        Extend the map with each new seed batch.
    Small and independent — does NOT gate 2.6 or 2.7.
    Acceptance (verified — spec FINDINGS):
        lookup("SINUMERIK", "AL 309") exact-hits without the family=None retry (DB test
        green against the real seed); the 2.5 dispatcher retry removed from
        hermes_backend.py; full suite 69 passed.
    Spec + acceptance evidence: specs/2026-07-19_2253_feature_2.8_family_normalization/

Feedback round 1 — first app field test (2026-07-19)
User feedback: (a) no visual distinction between what the user sent and what the agent answered; (b) captured photo not shown — neither immediately on capture nor in the conversation; (c) voice recording works but the transcript is invisible before send, so the user cannot verify what was understood; (d) the stream "just matches input text" — root cause: the field test ran the DEFAULT scripted backend (AGENT_BACKEND=scripted, 2.5 D7); the interactive hermes agent (thinking/planning) is opt-in and never reached the phone. Features 2.9–2.11 close this, ordered so each is field-testable on its own; 2.11 depends on 2.9 (rendering).

Feature 2.9 — Chat conversation view: user turns + inline media (owner: FE) — 16h — **[BUILT 2026-07-20, dev-verified; on-phone photo→thumbnail→bubble check = field runbook]**

    Objective: SessionScreen reads as a conversation — who said what, media inline.
    Repo path: RepairRöpiApp/mobile/ (screens/SessionScreen.tsx, services/events.ts reducer)
    As built: LogEntry.kind ("user"/"agent") — the reducer log is the conversation;
        user log entries carry photoUri/audioDurationMs (old stored entries restore fine);
        BubblePhoto degrades to a chip if the cache uri is gone (S3 copy is authoritative).
        2.11 extends this same kind-dispatched list for thinking/tool bubbles.
    Changes:
        Render USER turns as visually distinct chat bubbles (right-aligned: text + media);
        agent events stay left/full-width. User turns are a local echo at submit time —
        no backend change needed.
        Photo: thumbnail in the composer IMMEDIATELY on capture (local uri from
        expo-image-picker) so the user sees what will be sent; same image rendered inline
        in the sent user-turn bubble.
        Audio: chip in the user bubble (duration); transcript display = Feature 2.10.
    Acceptance (field-testable alone, scripted backend suffices):
        Take photo → thumbnail visible before send; send turn → photo + text appear as a
        user bubble; agent output clearly distinguishable from user input.

Feature 2.10 — Voice transcript echo before send (owner: BE + FE) — 12h — **[BUILT 2026-07-20, dev-verified live; on-phone record→echo→edit→send check = field runbook]**

    Objective: user must SEE (and can correct) what STT understood BEFORE it drives the diagnosis.
    Backend: POST /api/v1/media/{media_key}/transcribe → runs the 2.4 STT pipeline
        (app/tools/stt.py) standalone, returns { transcript, confidence }. Reuses the tool as-is.
        As built: {media_key:path} route (keys contain the tenant slash, spec D1); tenant
        guard mirrors 2.5 D6 (foreign tenant / missing object → 404, non-audio → 422,
        pipeline failure → 502 so the app can degrade; spec D2/D3). Synchronous like every
        tool since 2.4 D1.
    App: after audio upload, call transcribe and put the transcript into the text field
        (editable); user corrects, then sends TEXT (audio media_key stays attached for the
        Data Bridge).
        As built: upload happens at recording STOP (was send time); Attachment carries the
        media_key so the send queue skips the re-upload (2.6 D5 write-back). Chip shows
        "transkribiere …"; stale echo dropped if the audio was sent/discarded in flight;
        failure → toast + audio stays attached, server-side 2.4 STT covers it (spec D5).
    Turn pipeline: skip STT when the turn already carries user text (text-presence check in
        the agent_service media routing, extends 2.4 D7) — no double transcription.
    Acceptance:
        Record voice note → transcript appears in the text field → edit one word → send →
        agent works with the edited text; event stream shows no second stt tool_call.
        Status: dev-verified — live endpoint round-trip (presign → PUT sample_de.mp3 →
        transcribe → correct German transcript, conf 0.81, ~4 s inline, whisper base);
        skip-STT + tenant-guard tests green (full suite 73 passed); tsc clean. On-phone
        echo-and-edit run = field runbook item.
    Spec + acceptance evidence: specs/2026-07-20_0123_feature_2.10_transcript_echo/

Feature 2.11 — Hermes agent in the field (owner: ML + FE) — 16h — depends on 2.9 — **[BUILT 2026-07-20, dev-verified live; on-phone hermes run = field runbook, spec FINDINGS]**

    Objective: the interactive thinking/planning agent built in 2.5 actually reaches the phone —
    every field test so far exercised the scripted mock.
    Steps (as built):
        Dev/field environment defaults to AGENT_BACKEND=hermes via .env (code default stays
        scripted = CI/golden, 2.5 D7); NEW tests/conftest.py pins the pytest suite to
        scripted regardless of .env (spec D2 — load_dotenv would otherwise flip local
        tests silently). Switch + fallback documented in the field runbook (spec FINDINGS).
        thinking / tool_call / tool_result render in the 2.9 conversation view:
        LogEntry.kind gained "thinking" — non-empty thinking events become left-aligned
        agent bubbles in the log (wire-id keyed, replay-idempotent) while still driving
        the transient status row; tool calls stay the compact 🔧/✅ rows (spec D3/D4).
        On-phone field run: panel photo → visible thinking → hypotheses → discriminating
        question → answer → diagnosis. (Remaining acceptance step.)
    Acceptance:
        On-phone session against AGENT_BACKEND=hermes shows visible thinking/planning and at
        least one discriminating question; feedback item (d) "where is the agent?" closed.
        Status: dev-verified — live 2-turn AL-309 session through the flipped default
        (lookup exact hit → thinking → 3 hypotheses → axial-play question → answer →
        elimination → diagnosis 0.95 → guidance), real SSE replay fed through the real
        app reducer shows thinking bubbles + tool rows; app tests 7/7, tsc clean,
        backend suite 73 passed with .env flipped. Known: agent answers in English to
        German input (2.5 finding #5, gated by the 3.2 harness — not a 2.11 change).
    Spec + acceptance evidence: specs/2026-07-20_0147_feature_2.11_hermes_in_field/

PHASE 3 — Field Deployment (Weeks 9–12)
Goal: cloud deploy, pilots, metric capture.

Feature 3.1 — Cloud deployment + Docker Compose (owner: BE + infra) — 16h

    Deploy stack (single VPS or managed container host) via Docker Compose:
        Services: repair_logic_agent app, DB (managed or self-hosted Postgres), S3 (Hetzner/AWS), Langfuse
    Deliverables:
        infra/prod-docker-compose.yml
        deploy README with env var values to set (DB_URL, S3 creds, LITELLM_API_KEY, LANGFUSE_KEY)
    Decisions forced here (2.4/2.5 findings):
        STT deployment: Whisper large-v3 needs a GPU — decide GPU host vs. WHISPER_MODEL=base/small
        vs. hosted STT API BEFORE sizing the VPS (currently an unpriced contradiction with
        "single VPS").
        Inline tool latency: STT/vision run inline in the synchronous turn (2.4 D1) — move to
        background jobs only if pilot latency demands it.
        Also lands here (2.5 open items): LiteLLM proxy service (env swap by design),
        CORS tightening to real origins.
    Acceptance:
        Prod endpoint reachable; a smoke test script verify_connectivity.sh hits /health and performs a small simulated session.

Feature 3.2 — Golden test harness & CI gating (owner: QA + ML) — 16h

    First task (0.1 finding): align the golden-case label taxonomy with the alarm-DB
        related_components field (or enrich alarm records with symptom/positional tags) —
        top-3 recall is a metric artifact until this is done.
    Implement tests/golden/ harness (pytest) that:
        executes the agent pipeline in CI using a deterministic model mock or small local model and the seeded docs
        asserts top-1 accuracy (primary metric per 0.1 finding; top-3 recall only after
        taxonomy alignment) and that agent asks at least one clarifying question for each case
        checks prompt-language discipline (German user text → German agent output; 2.5
        finding #5 — CONFIRMED LIVE in 2.11: gemini answered a German AL-309 report with
        English thinking/hypotheses/question; fix belongs in the worker prompt, this
        check gates it)
    Also here (2.11 finding #3): resolve the ruff format drift — local ruff flags
        app/api/media.py + app/tools/error_code_lookup.py (committed in 2.10/2.8) that CI
        passed; pin the ruff version in pyproject so local and CI agree, then format.
    Hook into GitHub Actions to run on PRs, fail on regressions
    Acceptance: CI passes on baseline; PRs must run harness

Feature 3.3 — Pilot onboarding & monitoring (owner: PM + QA) — 40h

    Pilot pack:
        runbook: how-to install app, consent form, sample photos to capture, support contact
        monitoring: Langfuse traces per session, dashboard of metrics (diagnostic time, turns/session, top-1 accuracy sample)
    Data gate (1.1 finding): verify the 5 non-SIOS-verified seed error codes
        (source column marks them: 3000, 10720, 25050, 300500, 600607) against SIOS
        BEFORE any pilot relies on them.
    Acceptance:
        2–3 technicians run 10 sessions each; PM collects usage and feedback; QA calculates diagnostic time delta vs baseline.

PHASE 4 — Visual Grounding & Generalization (post-MVP, NOT scheduled)
Strategic directions ratified 2026-07-18. Nothing here starts before Phase 3 acceptance; listed so Phases 1–3 don't paint us into a corner.
Prototype provenance: https://github.com/edavidk7/zurich_physical_hack ("DocOps", IBM Docling Challenge) — Docling-parsed datasheets/SOPs → Gemini agents (DocumentSearcher + TaskPlanner) → camera-calibrated SO-ARM100 arm with multimeter probe physically probing an Arduino board. Transferable assets: Docling schematic/figure parsing, keypoint detection on the physical object (find_board_keypoints.py), camera calibration + pose estimation mapping documentation coordinates onto the real world. The robot arm is replaced by the technician's smartphone camera.

Feature 4.1 — Machine knowledge packs: generalize beyond CNC (owner: BE + ML)

    Extract everything CNC-specific (error_codes seed data, fault taxonomy, prompt context, golden cases, doc corpus refs) into a versioned knowledge-pack format; a second machine family proves the interface.
    Schema already keys by machine_family/controller_family — no migration expected; this is packaging discipline, not re-architecture.
    Acceptance: a non-CNC pilot machine family runs an end-to-end diagnosis with zero core-code change — only a new pack.

Feature 4.2 — Image annotation v1: augment the user's photos (owner: ML)

    Extend VisionAnalysisTool annotated_images[] (Feature 2.3) from OCR boxes to guidance overlays: arrows, circles, part outlines drawn on the user's own photo, driven by agent output ("mark the coolant valve").
    Implementation: Pillow/OpenCV drawing server-side, result to S3, guidance event gains optional annotated_media_key.
    Acceptance: agent answers "where is X?" with the user's own photo, X highlighted; technician-rated usefulness in pilot.

Feature 4.3 — Schematic-to-photo grounding: point to the problem (owner: ML)

    Parse schematics/exploded views (docling — already in the stack), match diagram to user photo via keypoint detection + pose estimation (port the prototype's find_board_keypoints/pose_estimation approach, minus calibration targets — single-photo homography, degrade gracefully to "no grounding, text only"), project the fault/part location from diagram onto photo.
    Acceptance: golden set of (diagram, photo, target part) triples; projected marker lands on the correct part ≥80%.

Feature 4.4 — Knowledge crawler: manuals + CNC forum corpus (owner: ML + BE)

    Closes the document-corpus gap (0.1/2.2 findings: search_semantic is FTS over 20 error-code
    rows, get_page_image is honestly empty, docling still unused) — deliberately OUT of Phase 2/3
    scope (ratified 2026-07-19).
    A crawler that inhales not just the machine manuals but also CNC online-forum threads
    (symptom language, workarounds, tribal knowledge) into the knowledge layer.
    Unblocks the deferred 2.2-D3 upgrade (indexed/embedding-backed search_semantic, real
    page-image store) and the RAG-vs-VLM question deferred since the 0.1 spike.
    Acceptance: defined when scheduled.

Cross-cutting features (must be done early)

    Langfuse integration (owner: ML + BE) — integrate LLM call and tool call tracing at each invocation. Files: app/services/observability.py
    Logging & metrics: add structured logs with session_id and turn_id
    Consent flag for training usage (append to sessions table and UI)
    Security/guardrails: agent container has resource limits and egress-proxy allowlist (no default route); hermes tool allowlist enforced in one place (hermes_backend.ALLOWED_TOOLS, checked against the worker handshake at every session start — Feature 2.5); per-tenant HERMES_HOME — cross-tenant leak test in CI (tests/agent/)

Exact SSE event schema (canonical — must be implemented verbatim)

    Each SSE message uses the event name header equal to step type, e.g., event: hypothesis
    Each event payload is JSON (data: {...})
    Event types and required fields:

    thinking

    { "id": "<event_uuid>", "content": "" }

    hypothesis

    { "id": "<event_uuid>", "hypothesis_id": "<h_uuid>", "description": "", "confidence": 0.0-1.0, "introduced_at_turn": int, "eliminated": bool (optional) }

    question

    { "id": "<event_uuid>", "content": "", "evidence_type": "photo|audio|tactile|numeric|text", "required_format": "" }

    tool_call

    { "id": "<event_uuid>", "tool": "<tool_name>", "args": {...} }

    tool_result

    { "id": "<event_uuid>", "tool": "<tool_name>", "result_summary": "", "raw_result": {...} }

    diagnosis

    { "id": "<event_uuid>", "hypothesis_id": "<h_uuid>", "confidence": 0.0-1.0, "explanation": "" }

    guidance

    { "id": "<event_uuid>", "step_index": int, "content": "", "safety_level": "low|medium|high" }

    done

    { "id": "<event_uuid>", "status": "awaiting_user_input|awaiting_verification|complete" }

Acceptance criteria for moving from phase to phase

    End of Phase 0 (Week 2)
        [DONE 2026-07-10] Knowledge spike result and decision documented — winner: hybrid
        CLI agent (hermes embed) that makes at least one discriminating question in toy session
        + GO/NO-GO on hermes documented (Feature 0.2 spike questions)
    End of Phase 1 (Week 4)
        [DONE 2026-07-19] SSE API accepts media, streams typed events, and dirty web prototype runs on phone for a first field test — user-verified on phone, full flow works
    End of Phase 2 (Week 8)
        Full Data Bridge persistence working, Vision + STT integrated, guardrails verified (tool allowlist, egress isolation, cross-tenant leak test), learning pipeline v1 delivering trajectories + skills to cloud, and mobile v1 can run an end-to-end diagnostic flow
    End of Phase 3 (Week 12)
        Pilot customers onboarded; basic metrics collected and initial diagnostic time delta measured

