# Feature 1.1 — DB migration & seeded error-code table: Requirements

> **One sentence:** Create the Data Bridge schema (Techstack v3 Session Trace Schema +
> `diagnostic_turn_events`) and an `error_codes` table in the dev Postgres, seeded with
> 20 SINUMERIK codes, applied via plain SQL (no ORM, no migration runner).

---

## Context

Feature 1.0 delivered the dev stack (Postgres 16 `repair` database). Feature 1.3 (SSE API)
needs the trace tables to persist events; Feature 2.2 (ErrorCodeLookupTool) needs the
`error_codes` table. The hybrid knowledge winner (Feature 0.1) made exact error-code lookup
the fast path — this table is its future backend.

## Scope (from Roadmap Feature 1.1)

1. `Repair_Logic_Agent/db/migrations/001_create_schema.sql` — Techstack schema verbatim
   (`diagnostic_sessions` incl. `tenant_id`, `diagnostic_turns`, `hypotheses`,
   `hypothesis_updates`, `session_outcomes`) + `diagnostic_turn_events` (Roadmap exact SQL)
   + `error_codes`.
2. `Repair_Logic_Agent/db/seeds/seed_error_codes.sql` — 20 SINUMERIK codes with descriptions.
3. Smoke test `tests/test_schema.py` (skips when dev Postgres is down — CI has no DB service).

Out of scope: migration runner/alembic (plain psql per Techstack "no ORM"), learning tables
(Feature 2.7), any API code.

## Decisions

### D1: Acceptance command corrected to the real compose stack

Roadmap says `docker-compose exec db psql -U postgres -f db/migrations/...`. Reality
(Feature 1.0): service is `postgres`, database is `repair`, and `db/` is not mounted into
the container. Working command (mirrored into the Roadmap):

    docker compose -f infra/docker-compose.yml exec -T postgres \
      psql -U postgres -d repair -v ON_ERROR_STOP=1 < db/migrations/001_create_schema.sql

### D2: `error_codes` column shape = curated YAML fields + Feature 2.2 lookup contract

Roadmap gives no columns for `error_codes`. Shape mirrors
`Research_Data/01_error_code_databases/*.yaml` (category, severity, message_de/en,
probable_causes, recommended_actions, related_components, discriminating_questions,
manual_reference) plus `spare_part_refs` (Feature 2.2 return field) and provenance
(`software_version`, `source` — alarm meanings are firmware-version-specific).
List/object fields are JSONB (Techstack: "JSONB for flexible evolution").
Feature 2.2 mapping: `meaning` ← `message_en`, `manual_section_id` ← `manual_reference`;
`confidence` is constant 1.0 in the tool, not stored.
Codes are stored as printed in the manual ("AL 309", "F07011"); query-time normalization
("700042" → "AL 700042") is the lookup tool's job (Feature 2.2), not the schema's.

### D3: Seed = 15 curated + 5 golden-case/standard codes, generated, idempotent

The curated SINUMERIK alarm DB has 15 entries; Roadmap wants 20. The 5 additions are the
4 SINUMERIK golden-case codes missing from the curated DB (`3000`, `10720`, `300500`,
`600607` — so the exact-lookup fast path can serve the golden harness) + `25050` (contour
monitoring, standard high-frequency alarm). Their wording follows the standard 840D
diagnostics manual but is **not yet verified against SIOS** — recorded in the `source`
column per row. Seed SQL is generated from the YAML (one-off script), committed as plain
SQL, idempotent via `ON CONFLICT (controller_family, code) DO NOTHING`.

### D4: No migration runner; smoke test skips without DB

One migration file doesn't justify a runner — single transaction, rerun fails atomically.
`tests/test_schema.py` connects with a 2s timeout and `pytest.skip`s when Postgres is down,
so CI (no DB service) stays green while local runs verify schema + seed.

---

## Acceptance (from Roadmap, command per D1)

- Migration applies cleanly; `\dt` shows all 7 tables.
- Seed applies; `select count(*) from error_codes;` → 20.
- `uv run pytest` green (schema tests pass with stack up, skip without), ruff clean.

---

*Feature 1.1 · Stand: 12. Juli 2026*
