# Feature 2.5 — Plan

1. `app/config.py`: `AGENT_BACKEND` (scripted default), `AGENT_WORKER_CMD`,
   `AGENT_RUNNER` (subprocess|docker) + docker image/network/proxy vars,
   `AGENT_TURN_TIMEOUT_S`, `HERMES_HOME_ROOT`, `REPAIR_LLM_*`,
   `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`; fix 2.3 proxy comment (D11)
2. `pyproject.toml`: add `ddgs`; `app/tools/web_search.py` (D9)
3. `app/services/observability.py`: `log_agent_error(session_id, kind,
   detail)` — Langfuse event if keys configured, stdlib logging always
4. `agents/hermes_worker.py` (runs in `.venv-hermes`): register 4 RPC-proxied
   domain tools + skills/memory toolsets, allowlist assert, `ready` handshake,
   turn loop (`run_conversation` + history), post-turn NDJSON protocol parse →
   event ops, tool RPC over stdio (D1–D3); diagnostic protocol prompt updated
   for 4 tools + high-safety stop rule
5. `app/services/hermes_backend.py`: `ALLOWED_TOOLS`, `Worker` (spawn
   subprocess|docker, handshake check, per-session registry + lock, kill),
   `iter_turn_events(...)` generator: RPC dispatch (session-scoped media
   guard) → synthesized tool events, event op → Pydantic validation →
   sanitize + Langfuse (D4)
6. `app/services/agent_service.py`: tenant param on `create_session`; shell
   refactor — STT inline, user+agent turn rows committed first, ONE
   persistence loop consuming backend generator (scripted wrapped as
   generator), commit per event, safety gate (D5), finalize turn
   content/tools_called + hypotheses; agent failure → error event, never 500
7. API tenant plumbing (D6): `X-Tenant-Id` header on sessions + media
   endpoints, tenant-prefixed media_key, turn media-key prefix check (422),
   409 on concurrent turn
8. Egress infra (D8): `infra/Dockerfile.agent`,
   `infra/docker-compose.agent.yml` (internal network + squid),
   `infra/egress/squid.conf` (allowlist: LLM domains + models.dev)
9. Tests: `tests/agent/stub_worker.py` (deterministic worker, knobs via env);
   `tests/agent/test_agent_service.py` — hermes flow w/ real lookup RPC,
   sanitization, safety gate, handshake mismatch, cross-tenant parallel
   zero-bleed, busy 409, timeout kill; validation unit tests (no DB);
   `tests/agent/test_egress_isolation.py` (docker-gated);
   media prefix + guard tests
10. Verify: `uv run pytest`, ruff; docker image build + egress test; live
    acceptance `AGENT_BACKEND=hermes` (real Gemini key): AL-309 session end
    to end, events in DB + SSE, tenant home populated
11. FINDINGS.md; Roadmap 2.5 → DONE (+ D2/D8/D10 amendments); Techstack:
    worker-RPC architecture note, WebSearch row (D9), proxy timing (D11),
    egress allowlist correction (LLM-only for the agent process)
