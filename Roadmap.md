Goal: deliver an MVP that proves the mission thesis (multimodal, iterative diagnostic loop + Data Bridge) for SINUMERIK CNC machines in 12 weeks. This roadmap translates the cofounder's phases into concrete features, with file-level entry points, exact APIs, test commands and acceptance criteria so a coding agent or developer can start implementing immediately.

> **Architecture change (Juli 2026, Techstack v3):** the agent backbone is now an **embedded hermes-agent** (`run_agent.AIAgent` from NousResearch/hermes-agent, pinned commit) instead of smolagents. Consequences for this roadmap: Feature 0.2 becomes the hermes embed spike; Feature 2.5 loses the CodeAgent Docker sandbox (tool-calling only — containment is tool allowlist + egress isolation); new Feature 2.7 adds the Learning Pipeline (trajectories, skills, memory → cloud curation); all sessions become tenant-scoped (central multi-tenant cloud).
>
> **Status:** Features 0.0 and 0.1 are COMPLETE. Knowledge-layer winner: **hybrid** (exact error-code lookup fast-path + LLM over narrowed candidates) — see `Repair_Logic_Agent/knowledge_spike/FINDINGS.md`.

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

Feature 1.0 — Project skeleton & dev infra (owner: BE) — 8h

    Repo: repair_logic_agent
    Files to create:
        pyproject.toml (core dependencies)
        infra/docker-compose.yml (postgres, MinIO dev, langfuse)
        app/main.py (FastAPI app skeleton)
        app/config.py (env loader)
        .github/workflows/ci.yml (ruff + pytest stub)
    Acceptance: docker-compose up starts services; FastAPI health check returns 200 at /health

Feature 1.1 — DB migration and seeded error-code table (owner: BE) — 12h

    Repo: repair_logic_agent/db/migrations/001_create_schema.sql (exact SQL provided)
    Add seed script: db/seeds/seed_error_codes.sql with 20 SINUMERIK codes and descriptions
    Required exact SQL (create, insert) — use the schema from the architecture doc (diagnostic_sessions incl. tenant_id, diagnostic_turns, hypotheses, hypothesis_updates, session_outcomes) + diagnostic_turn_events table:
        ADD table diagnostic_turn_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        turn_id UUID REFERENCES diagnostic_turns(id),
        event_index INT,
        event_type TEXT,
        event_data JSONB,
        created_at TIMESTAMPTZ DEFAULT now()
        );
    Acceptance:
        Run: docker-compose exec db psql -U postgres -f db/migrations/001_create_schema.sql
        docker-compose exec db psql -U postgres -c "select count(*) from error_codes;" => shows seeded rows.

Feature 1.2 — Presigned upload endpoint (owner: BE) — 8h

    Endpoint: POST /api/v1/media/upload-url
    Input JSON: { "filename": "panel.jpg", "content_type": "image/jpeg", "purpose": "turn_media" }
    Response JSON: { "upload_url": "...", "media_key": "uuid" }
    Implementation files:
        app/api/media.py → function create_presigned_upload()
        app/services/storage.py → function generate_presigned_put(media_key, content_type)
    Acceptance:
        curl -X POST http://localhost:8000/api/v1/media/upload-url -d '{"filename":"a.jpg","content_type":"image/jpeg"}'
        use curl -T panel.jpg "<upload_url>" and then verify via storage GET exists.

Feature 1.3 — FastAPI wrapper + SSE stream (owner: BE + ML) — 24h

    Endpoints to implement:
        POST /api/v1/sessions → create session (returns session_id)
        POST /api/v1/sessions/{id}/turns → submit user turn
        GET /api/v1/sessions/{id}/stream → SSE event stream
        GET /api/v1/sessions/{id}/turns/{tid}/events?after={event_id} → replay
    Files:
        app/api/sessions.py
        app/models/events.py (Pydantic step schemas — see below)
        app/services/agent_service.py (AgentService stub that converts agent steps to events and persists them)
    SSE: use fastapi.responses.EventSourceResponse (or manually stream text/event-stream)
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
        SSE returns events with event: hypothesis \n data: {...}\n\n etc.

Feature 1.4 — Dirty web prototype (owner: FE) — 24h

    Repo: repairropi_app/web_prototype/
    Files:
        index.html (single page)
        app.js (JS to capture photo, request presigned URL, upload, POST turn, open SSE)
    Implementation steps:
        page shows "Start session" button -> creates session via POST /api/v1/sessions
        camera capture input (input type="file" accept="image/*" capture="environment")
        request presigned URL, PUT image, POST turn with media_key, open SSE to stream events
        UI renders events: thinking, hypothesis list, questions with primary CTA (take photo)
    Acceptance (FIRST FIELD TEST):
        Open web link on phone, take photo of control, call flow returns streamed events and asks a question.
    Test: open file via a simple static server: python -m http.server 8080 in repairropi_app/web_prototype and visit via phone on same LAN.

PHASE 2 — Foundation & App (Weeks 5–8)
Focus: productionize the core pipeline, add audio, structured traces, guardrails (tool allowlist, egress isolation, tenant isolation), learning pipeline, and build native app.

Feature 2.1 — Data Bridge completion & export (owner: BE) — 24h

    Implement full session persistence:
        diagnostic_sessions, diagnostic_turns, hypotheses, hypothesis_updates, diagnostic_turn_events, session_outcomes tables with SQL migrations
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

Feature 2.2 — ErrorCodeLookupTool + KnowledgeRetrievalTool (owner: ML + BE) — 24h

    ErrorCodeLookupTool:
        Implements exact lookup in SQL table error_codes(controller_family, code) -> returns structured fields: code, meaning, manual_section_id, spare_part_refs, confidence=1.0
        File: app/tools/error_code_lookup.py (class ErrorCodeLookup)
        Function signature:
            def lookup(controller_family: str, code: str) -> Optional[dict]
    KnowledgeRetrievalTool:
        Interface per KnowledgeLayer Protocol: search_semantic, lookup_error_code, get_page_image, get_compiled_article
        File: app/tools/knowledge_layer.py
    Acceptance:
        Agent can call both tools and incorporate tool_result events into event stream.

Feature 2.3 — VisionAnalysisTool (owner: ML) — 40h

    Implement pragmatic pipeline:
        Fetch image from S3 (media_key)
        Preprocess: autocrop, enhance contrast, rotate deskew
        OCR via pytesseract (or cloud OCR if needed) to extract numeric/error-code-like strings
        A small LiteLLM multimodal call to classify control panel (Siemens / Heidenhain / Fanuc) on the image
        Return: detected_controller, detected_codes[], annotated_images[] (S3 keys or base64), confidence
    File: app/tools/vision_analysis.py
    Function signature:
        def analyze(media_key: str) -> dict
    Acceptance:
        With test images, detect controller family correctly >= 80% on seed images (measured by tests/vision/test_vision_expectations.py)
    Agent integration: when user uploads a photo, agent calls VisionAnalysisTool and streams a tool_call / tool_result event.

Feature 2.4 — STT (Whisper) + audio preprocessing (owner: ML + BE) — 24h

    Add audio upload handling route (POST /api/v1/media/upload-url already handles uploads; STT runs via background job)
    File: app/tools/stt.py
    Steps:
        fetch audio from S3, run noise reduction (noisereduce or RNNoise wrapper)
        call whisper (large-v3) to transcribe to German
        return transcript with word timestamps and confidence
    Acceptance:
        For sample noisy audio, WER measured and logged; transcripts appear as user-turn text when user uploads audio.
    Test:
        tests/stt/test_transcribe_sample.py

Feature 2.5 — AgentService: embedded hermes AIAgent + guardrails + Pydantic step enforcement (owner: ML + BE) — 40h

    Implement or refine app/services/agent_service.py with:
        AgentService.start_session(session_id, tenant_id)
        AgentService.push_turn(session_id, turn_payload)
        AgentService.stream_events(session_id) → generator used by SSE endpoint
    Key points:
        Embed run_agent.AIAgent (hermes-agent, pinned commit) — productionize the Feature 0.2 spike
        Tool allowlist: exactly the 4 domain tools (vision, error-code lookup, knowledge retrieval,
        web search). No terminal, no browser, no MCP, no subagents — never registered.
        Per-tenant HERMES_HOME (memory/skills/session cache); Postgres stays source of truth
        Event mapper converts the hermes stream to our Pydantic events
        Validate each event against app/models/events.py; if invalid, agent_service synthesizes a
        sanitized event and logs a Langfuse error — raw output is never forwarded
        guidance events with safety_level=high require explicit user confirmation before the
        agent streams follow-up steps (physical-safety approval gate)
    Acceptance:
        Events are persisted to diagnostic_turn_events, SSE streams valid typed events,
        cross-tenant test: two parallel sessions with different tenant_ids show zero state bleed.
    Safety:
        Egress isolation per hermes docs/security/network-egress-isolation.md: agent container on
        an internal Docker network with no default route; egress proxy allowlists only LLM
        endpoints, S3 and Langfuse. Verified by a test that curls a non-allowlisted host from
        inside the container and fails.

Feature 2.6 — Mobile App V1 (RN or Flutter) — build the real app (owner: FE + PM) — 80h

    Target: Android (ruggeds); iOS optional later.
    Repo path: repairropi_app/mobile/
    Key screens:
        SessionList / NewSession
        SessionScreen (SSE stream view): top area shows "agent thinking", hypothesis panel, question card (primary CTA), evidence submission (photo, audio, text), verification upload, final diagnosis card
    Required features:
        Presigned upload flow (from web prototype)
        SSE client with Last-Event-ID & replay on reconnect
        Evidence capture widgets: camera, audio recorder (with ambient noise indicator), quick numeric input (e.g., "enter mm")
        Offline resilience: cache uploaded media_keys pending network; sync on reconnect (but offline-first full not required)
    Files / components (React Native):
        screens/SessionScreen.js
        components/HypothesisList.js
        services/api.js (presigned upload + turns + SSE helper)
    Acceptance:
        Installable APK runs on rugged Android and can run end-to-end test: capture photo, upload, create turn, receive SSE events, respond to question, receive diagnosis, upload verification photo, export session shows trace.

Feature 2.7 — Learning Pipeline v1: field → cloud (owner: ML + BE) — 32h

    Objective: implement the Techstack v3 Learning Pipeline — every session's learnings become
    cloud assets, tenant-isolated, with a curation gate before anything is shared.
    Files:
        app/services/learning_pipeline.py
        db/migrations/00X_learning_tables.sql (skill_curation_queue, trajectory_refs)
    Three streams:
        1. Trajectories: after each session, export the hermes trajectory (compressed via
           trajectory_compressor), upload to S3 under tenant prefix, insert Postgres ref row.
        2. Skills: watch per-tenant HERMES_HOME/skills/; new/changed skills are copied into
           skill_curation_queue (status: pending_review). Promotion to the fleet skill base is a
           manual review action in Phase 2 (simple CLI/SQL is fine — no admin UI yet).
        3. Memory: per-tenant hermes memory is backed up to S3 (tenant prefix). Never shared.
    Guardrail (non-negotiable):
        Nothing crosses a tenant boundary without curation. Automated scrub of tenant-identifying
        strings + human approval. Test: a skill created in tenant A is not loadable by tenant B
        unless promoted.
    Acceptance:
        Run a dev session -> trajectory appears in S3 + ref row in Postgres; a synthetic skill
        lands in the curation queue; promotion copies it to the fleet skill base and a tenant-B
        session can then use it.

PHASE 3 — Field Deployment (Weeks 9–12)
Goal: cloud deploy, pilots, metric capture.

Feature 3.1 — Cloud deployment + Docker Compose (owner: BE + infra) — 16h

    Deploy stack (single VPS or managed container host) via Docker Compose:
        Services: repair_logic_agent app, DB (managed or self-hosted Postgres), S3 (Hetzner/AWS), Langfuse
    Deliverables:
        infra/prod-docker-compose.yml
        deploy README with env var values to set (DB_URL, S3 creds, LITELLM_API_KEY, LANGFUSE_KEY)
    Acceptance:
        Prod endpoint reachable; a smoke test script verify_connectivity.sh hits /health and performs a small simulated session.

Feature 3.2 — Golden test harness & CI gating (owner: QA + ML) — 16h

    Implement tests/golden/ harness (pytest) that:
        executes the agent pipeline in CI using a deterministic model mock or small local model and the seeded docs
        asserts top-1/top-3 recall and that agent asks at least one clarifying question for each case
    Hook into GitHub Actions to run on PRs, fail on regressions
    Acceptance: CI passes on baseline; PRs must run harness

Feature 3.3 — Pilot onboarding & monitoring (owner: PM + QA) — 40h

    Pilot pack:
        runbook: how-to install app, consent form, sample photos to capture, support contact
        monitoring: Langfuse traces per session, dashboard of metrics (diagnostic time, turns/session, top3 accuracy sample)
    Acceptance:
        2–3 technicians run 10 sessions each; PM collects usage and feedback; QA calculates diagnostic time delta vs baseline.

Cross-cutting features (must be done early)

    Langfuse integration (owner: ML + BE) — integrate LLM call and tool call tracing at each invocation. Files: app/services/observability.py
    Logging & metrics: add structured logs with session_id and turn_id
    Consent flag for training usage (append to sessions table and UI)
    Security/guardrails: agent container has resource limits and egress-proxy allowlist (no default route); hermes tool allowlist enforced in one place (AgentService constructor); per-tenant HERMES_HOME — cross-tenant leak test in CI

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

Entry points for the coding agent — prioritized actionable tasks
These are the exact first tasks you should send to the coding agent in order. Each entry says file(s) to create, CLI command to run, and acceptance test.

    Create repos & project skeleton (repair_logic_agent)

    Files to create:
        repair_logic_agent/pyproject.toml (dependencies: fastapi, uvicorn, pydantic>=2, httpx, hermes-agent @ pinned git commit, litellm, psycopg[binary], boto3, langfuse, pytest, ruff, pytesseract, faiss-cpu or simple in-memory index)
        repair_logic_agent/app/main.py (FastAPI app with /health)
        repair_logic_agent/infra/docker-compose.yml (postgres:13, minio, optional langfuse)
    Command:
        git init repair_logic_agent && cd repair_logic_agent
        python -m venv .venv && .venv/bin/pip install -r requirements.txt
        docker-compose up -d
    Acceptance:
        curl http://localhost:8000/health → returns {"status":"ok"}

    Add DB migration (repair_logic_agent/db/migrations/001_create_schema.sql)

    Copy the SQL schema from the architecture doc, plus diagnostic_turn_events table and error_codes table.
    Command:
        docker-compose exec db psql -U postgres -f db/migrations/001_create_schema.sql
    Acceptance:
        docker-compose exec db psql -U postgres -c '\dt' shows tables

    Add golden fixtures (repair_logic_agent/knowledge_spike/golden_cases.yaml + docs/)

    Place PDFs and images in that folder.
    Acceptance:
        python knowledge_spike/validate_fixtures.py --cases knowledge_spike/golden_cases.yaml returns OK

    Implement minimal RAG prototype (repair_logic_agent/knowledge_spike/rag_spike.py)

    Implement ingest → embed → search flow (use a small embedder to avoid external API).
    Acceptance:
        python knowledge_spike/rag_spike.py --query "AL 309 rattling x axis" returns top-3 pages and prints whether ground_truth found.

    Implement CLI agent harness (repair_logic_agent/agents/run_cli.py)

    Embed hermes run_agent.AIAgent (or fallback to litellm sequential calls if the embed spike fails); ensure the CLI can call knowledge_retrieval(query) tool and answer the four spike questions from Feature 0.2
    Acceptance:
        python agents/run_cli.py
        Provide input "AL 309" -> agent prints JSON hypothesis and question

    Wrap CLI in FastAPI with SSE (repair_logic_agent/app/api/sessions.py)

    Implement endpoints and SSE streaming using EventSourceResponse
    Acceptance:
        Start server: uvicorn app.main:app --reload
        Create session: curl -X POST http://localhost:8000/api/v1/sessions -> session_id
        POST turn and open SSE: curl -N http://localhost:8000/api/v1/sessions/{id}/stream -> see events

    Dirty web prototype (repairropi_app/web_prototype/)

    Create index.html and app.js to call presigned URL endpoint + SSE
    Acceptance:
        Python static server + phone browser -> can take photo, upload, and receive events from SSE

    Add VisionAnalysisTool stub (repair_logic_agent/app/tools/vision_analysis.py)

    Implement analyze(media_key) that fetches image and runs pytesseract; return controller guess via simple heuristics (e.g., regex matching for Fanuc/Siemens patterns)
    Acceptance:
        Run a script that loads sample image and prints detected codes and controller.

    Add presigned upload endpoint (repair_logic_agent/app/api/media.py)

    Implement using boto3 and test via curl PUT
    Acceptance:
        POST -> get upload_url, curl -T -> GET object via boto3 list_objects

    Integrate Langfuse minimal tracing for LLM calls (repair_logic_agent/app/services/observability.py)

    Add a wrapper to call LiteLLM with Langfuse callback tags (session_id)
    Acceptance:
        Running a small demo generates a trace in Langfuse dev instance

Acceptance criteria for moving from phase to phase

    End of Phase 0 (Week 2)
        [DONE 2026-07-10] Knowledge spike result and decision documented — winner: hybrid
        CLI agent (hermes embed) that makes at least one discriminating question in toy session
        + GO/NO-GO on hermes documented (Feature 0.2 spike questions)
    End of Phase 1 (Week 4)
        SSE API accepts media, streams typed events, and dirty web prototype runs on phone for a first field test
    End of Phase 2 (Week 8)
        Full Data Bridge persistence working, Vision + STT integrated, guardrails verified (tool allowlist, egress isolation, cross-tenant leak test), learning pipeline v1 delivering trajectories + skills to cloud, and mobile v1 can run an end-to-end diagnostic flow
    End of Phase 3 (Week 12)
        Pilot customers onboarded; basic metrics collected and initial diagnostic time delta measured

Small checklist you can hand to the coding agent now (top 10 atomic issues)

    (BE) Create repo repair_logic_agent and add pyproject.toml + app/main.py health endpoint.
    (BE) Add docker-compose with Postgres + MinIO dev, and start services.
    (PM) Add golden_cases.yaml and upload 20 manual pages to repair_logic_agent/knowledge_spike/docs/.
    (ML) Implement rag_spike.py that can return top-3 pages for a query and a simple evaluator.
    (ML) Implement run_cli.py embedding hermes AIAgent (or fallback to litellm) that calls knowledge_retrieval tool.
    (BE) Implement DB migration 001_create_schema.sql and run it against dev Postgres.
    (BE) Implement POST /api/v1/media/upload-url and test presigned PUT.
    (BE+ML) Implement basic AgentService that can accept a turn, call knowledge tool, produce a hypothesis event, and stream via SSE.
    (FE) Create repairropi_app/web_prototype/index.html that can capture a photo and call the presigned flow and SSE.
    (QA) Create tests/golden/test_rag_recall.py that validates top-3 recall for the RAG prototype.
