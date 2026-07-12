# Feature 1.0 — Project skeleton & dev infra: Plan

> **Goal:** installable package + running dev stack + green CI. No product logic.

---

## Task Group 1: Python project

1.1. `Repair_Logic_Agent/pyproject.toml` — project metadata, deps (requirements D5),
`[tool.ruff]` (line-length 100, py312, `E F I N W UP` — verbatim from Techstack §Code Style),
`[tool.pytest.ini_options]` (`testpaths=["tests"]`, `pythonpath=["."]`).

1.2. `uv lock && uv sync` → `Repair_Logic_Agent/.venv` (uv-managed; distinct from the
repo-root spike venvs).

**Output:** importable project, committed `uv.lock`.

## Task Group 2: App skeleton

2.1. `app/__init__.py`, `app/main.py` (FastAPI, `GET /health` → `{"status": "ok"}`).

2.2. `app/config.py` — `load_dotenv()` + module-level constants
(`DATABASE_URL`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`,
`LANGFUSE_HOST`); defaults match the compose stack, overridable via `.env`/env.

2.3. `tests/test_health.py` — TestClient asserts 200 + body.

**Output:** `uvicorn app.main:app` serves `/health`; pytest green.

## Task Group 3: Dev infra (compose)

3.1. `infra/docker-compose.yml`:

| Service | Image | Ports | Notes |
|---|---|---|---|
| postgres | postgres:16-alpine | 5432 | DBs: `repair` (app), `langfuse` (via initdb script) |
| minio | minio/minio | 9000/9001 | dev S3 |
| minio-init | minio/mc | — | one-shot: creates `repair-media` + `langfuse` buckets |
| clickhouse | clickhouse/clickhouse-server:24.8-alpine | internal | Langfuse event store |
| redis | redis:7-alpine | internal | Langfuse queue |
| langfuse-web | langfuse/langfuse:3 | 3000 | `LANGFUSE_INIT_*` provisions org/project/keys |
| langfuse-worker | langfuse/langfuse-worker:3 | internal | shares env anchor with web |

3.2. `infra/initdb/create-langfuse-db.sql` — `CREATE DATABASE langfuse;`

**Output:** `docker compose up -d` → healthy stack.

## Task Group 4: CI

4.1. `repair_bot/.github/workflows/ci.yml` (git root, D1): checkout → setup-uv →
`uv sync` → `ruff check app tests` → `ruff format --check app tests` → `pytest`,
all with `working-directory: Repair_Logic_Agent`.

**Output:** CI runs on push/PR to main.

## Task Group 5: Acceptance + mirror

5.1. Run acceptance commands (requirements §Acceptance), capture output → `FINDINGS.md`.

5.2. Mirror into `Roadmap.md` (status line, Feature 1.0 deviations D2–D4) and
`Techstack.md` (pre-lock checklist: Langfuse deployed; hermes venv note).

---

## File Map

```
repair_bot/
├── .github/workflows/ci.yml                  # TG4
└── Repair_Logic_Agent/
    ├── pyproject.toml                        # TG1
    ├── uv.lock                               # TG1
    ├── app/{__init__,main,config}.py         # TG2
    ├── tests/test_health.py                  # TG2
    └── infra/
        ├── docker-compose.yml                # TG3
        └── initdb/create-langfuse-db.sql     # TG3
```

## Estimated Effort

~4h (Roadmap estimate: 8h).

---

*Feature 1.0 · Stand: 12. Juli 2026*
