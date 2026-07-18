# Feature 2.1 — Plan

## Files

| File | Content |
|---|---|
| `Repair_Logic_Agent/app/services/agent_service.py` | persist hypotheses + hypothesis_updates inside `_process_turn` (D2) |
| `Repair_Logic_Agent/app/services/traces.py` | Pydantic export schema + `assemble_export(session_id)` (D4, D5) |
| `Repair_Logic_Agent/app/api/sessions.py` | `GET /{id}/export`, `POST /{id}/outcome` (D3, D6) |
| `Repair_Logic_Agent/tests/traces/test_export_schema.py` | full flow: turns → outcome → export validates; mid-session export; 404 |

## Order

1. Spec (this) → agent_service hypothesis persistence → traces.py → routes
2. Tests, `uv run ruff check` + `format --check`, `uv run pytest -q`
3. Live acceptance: dev stack up, curl session → turn → outcome → export,
   verify JSON shape + hypotheses/outcome rows in Postgres
4. FINDINGS.md + mirror into Roadmap.md (mark 2.1 DONE, note D3 outcome endpoint)

## Test flow

`docker compose -f infra/docker-compose.yml up -d` (Postgres migrated + seeded) →
`uv run pytest -q tests/traces/` — creates a session via TestClient, posts a turn
("AL 309 …"), posts an outcome, GETs export, validates against the Pydantic
schema; asserts hypotheses rows exist, final_diagnosis marked, outcome mapped to
session status. Mid-session export returns nulls (D6); ghost session → 404.

---

*Feature 2.1 · Stand: 12. Juli 2026*
