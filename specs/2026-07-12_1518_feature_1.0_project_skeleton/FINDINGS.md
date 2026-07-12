# Feature 1.0 — Project skeleton & dev infra: Findings / Acceptance

**Status: COMPLETE — all acceptance criteria pass (2026-07-12).**

## Acceptance evidence

| Check | Result |
|---|---|
| `uv sync` | clean install into `Repair_Logic_Agent/.venv` (uv-managed), `uv.lock` committed |
| `uv run pytest` | 1 passed |
| `uv run ruff check app tests` + `ruff format --check` | clean |
| `docker compose -f infra/docker-compose.yml up -d` | all 7 services up; postgres/minio/clickhouse/redis healthy |
| Postgres | databases `repair` + `langfuse` present (initdb script works) |
| MinIO | buckets `repair-media` + `langfuse` created by `minio-init` one-shot |
| Langfuse | `GET :3000/api/public/health` → `{"status":"OK","version":"3.212.0"}` |
| Langfuse init keys | `curl -u pk-lf-dev-repairropi:sk-lf-dev-repairropi :3000/api/public/projects` → project `repair-logic-agent-dev` |
| FastAPI | `uvicorn app.main:app` → `GET /health` → 200 `{"status":"ok"}` |

## Notes for later features

- **Langfuse dev credentials** (all dev-only, in compose): UI login `dev@repairropi.local` /
  `devpassword1`; API keys `pk-lf-dev-repairropi` / `sk-lf-dev-repairropi`; host
  `http://localhost:3000`. Use these in the cross-cutting observability feature.
- **Langfuse web has no compose healthcheck** (image has neither curl nor wget); first boot
  runs ClickHouse migrations, ~60s until healthy. Poll `/api/public/health` if scripting.
- **Venv landscape** now: `Repair_Logic_Agent/.venv` (uv, API layer — the one CI uses),
  repo-root `venv/` (legacy spikes), `.venv-hermes/` (hermes, pinned). Repo-root `.venv/` is
  broken and should be deleted at some point.
- Feature 1.1 (DB migration) runs against the `repair` database:
  `docker compose -f infra/docker-compose.yml exec postgres psql -U postgres -d repair ...`

## Deviations from Roadmap (ratified in requirements.md D1–D6)

- CI workflow at git root (single-repo reality), `working-directory: Repair_Logic_Agent`.
- `hermes-agent` NOT in pyproject (exact-pin conflict → stays in `.venv-hermes`; process
  boundary resolved in Feature 2.5).
- `postgres:16-alpine` instead of `postgres:13` (EOL).
- Langfuse v3 full stack (web/worker/clickhouse/redis) instead of a single container —
  v3 SDK requires v3 server; postgres + minio shared with our stack.
- `pytesseract`/`faiss-cpu` dropped from deps (added by the feature that imports them;
  faiss is dead — hybrid winner uses TF-IDF).

---

*Feature 1.0 · Stand: 12. Juli 2026*
