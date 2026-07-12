# Feature 1.0 — Project skeleton & dev infra: Requirements

> **One sentence:** Give `Repair_Logic_Agent` a real Python project (pyproject + uv), a dev
> infra stack (Postgres, MinIO, Langfuse) via Docker Compose, a FastAPI skeleton with
> `/health`, and CI (ruff + pytest) — the foundation every Phase-1 feature builds on.

---

## Context

Phase 0 is complete (knowledge winner: hybrid; hermes embed: GO). Phase 1 starts here.
Everything so far is spike code in ad-hoc venvs; there is no installable package, no server,
no database, no CI.

## Scope

### In Scope (from Roadmap Feature 1.0)

1. `Repair_Logic_Agent/pyproject.toml` — core dependencies, ruff + pytest config, uv-managed.
2. `Repair_Logic_Agent/infra/docker-compose.yml` — postgres, MinIO (dev S3), Langfuse.
3. `Repair_Logic_Agent/app/main.py` — FastAPI skeleton with `GET /health`.
4. `Repair_Logic_Agent/app/config.py` — env loader (defaults match the compose stack).
5. `.github/workflows/ci.yml` — ruff + pytest on push/PR (at git root, see D1).
6. `Repair_Logic_Agent/tests/test_health.py` — the pytest stub is a real test.

### Out of Scope

| Item | Why Not Now |
|---|---|
| DB schema / migrations | Feature 1.1 |
| Presigned uploads, sessions API, SSE | Features 1.2 / 1.3 |
| Hermes / AgentService integration | Feature 2.5 (see D2) |
| Langfuse SDK wiring in app code | Cross-cutting feature (`app/services/observability.py`) |
| Production compose | Feature 3.1 |

---

## Key Decisions

### D1: Single repo, CI at git root

Roadmap assumes a standalone `repair_logic_agent` repo. Reality (since Feature 0.0): one repo
`repair_bot` with `Repair_Logic_Agent/` and `RepairRöpiApp/` subdirectories. GitHub Actions
only reads workflows from the git root, so `ci.yml` lives at `repair_bot/.github/workflows/`
and runs with `working-directory: Repair_Logic_Agent`. The two-repo split can happen later
without touching anything but that one line.

### D2: hermes-agent is NOT in pyproject.toml

Roadmap's entry-point checklist lists `hermes-agent @ pinned` as a pyproject dependency.
Feature 0.2 (D1) proved this wrong in practice: hermes exact-pins its deps (`openai==2.24.0`
etc.) and must live in its dedicated venv (`.venv-hermes`,
`agents/requirements_agents.txt`). The pyproject venv is the **API-layer** environment.
Consequence: FastAPI app and embedded hermes cannot share a process today; Feature 1.3's
AgentService stub is hermes-free, and the process/dependency boundary is resolved in
Feature 2.5 (options: reconcile pins at the then-current hermes commit, or run the agent as
a subprocess per session). Recorded here so nobody "fixes" the missing dependency.

### D3: postgres:16-alpine (not postgres:13)

Roadmap says `postgres:13` — EOL since November 2025. Schema needs nothing newer than
`gen_random_uuid()` (built-in since 13), so 16 changes nothing except being supported.

### D4: Langfuse v3 stack (web + worker + ClickHouse + Redis), sharing dev Postgres and MinIO

The Langfuse v3 Python SDK requires a v3 server; starting on v2 in mid-2026 means a forced
ClickHouse data migration later. Cost: four extra dev-only services in compose — but Postgres
(separate `langfuse` database) and MinIO (separate `langfuse` bucket) are shared with our own
stack, and the config is copied from Langfuse's own self-host compose. All secrets in the
compose file are dev-only values. `LANGFUSE_INIT_*` provisions a deterministic org/project/
API-key pair so the app and LiteLLM can be pointed at it without ClickOps.
This also checks the Techstack pre-lock item "Langfuse deployed before first agent
integration test".

### D5: Dependencies = what Phase 1 features import, nothing speculative

`fastapi, uvicorn, pydantic>=2, httpx, litellm~=1.77, psycopg[binary], boto3, langfuse,
python-dotenv, pyyaml, pillow` + dev group `ruff, pytest`. From the Roadmap suggestion list,
`pytesseract` (Feature 2.3) and `faiss-cpu` (dead — hybrid won, TF-IDF suffices) are dropped;
they get added by the feature that imports them.

### D6: ruff scope = `app/` + `tests/`

Phase-0 spike code (`knowledge_spike/`, `agents/`, `data_crawling_pipe/`, …) predates the
lint rules and stays untouched until a feature touches it. CI runs
`ruff check app tests` + `ruff format --check app tests`.

---

## Acceptance (from Roadmap)

- `docker compose -f infra/docker-compose.yml up -d` → all services healthy
  (Postgres accepts connections, MinIO live, Langfuse `/api/public/health` OK).
- `uvicorn app.main:app` → `curl http://localhost:8000/health` returns 200 `{"status":"ok"}`.
- `uv run pytest` green, `uv run ruff check app tests` clean.

---

*Feature 1.0 · Stand: 12. Juli 2026*
