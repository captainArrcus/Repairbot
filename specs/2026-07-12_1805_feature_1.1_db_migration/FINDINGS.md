# Feature 1.1 — DB migration & seeded error codes: Findings / Acceptance

**Status: COMPLETE — all acceptance criteria pass (2026-07-12).**

## Acceptance evidence

| Check | Result |
|---|---|
| Migration via `exec -T postgres psql ... -d repair < db/migrations/001_create_schema.sql` | `BEGIN` + 7× `CREATE TABLE` + `COMMIT` |
| `\dt` on `repair` | 7 tables: diagnostic_sessions, diagnostic_turns, diagnostic_turn_events, hypotheses, hypothesis_updates, session_outcomes, error_codes |
| Seed via same path | `INSERT 0 20` |
| `select count(*) from error_codes;` | 20 |
| Seed rerun (idempotency) | `INSERT 0 0`, count stays 20 |
| `uv run pytest` | 4 passed (health + 3 schema tests) |
| `uv run ruff check app tests` + `ruff format --check` | clean |

## Notes for later features

- **Feature 1.3 / 2.1:** trace tables exist now; `diagnostic_turn_events` has no index on
  `turn_id` yet — add one when the replay endpoint's query pattern is real
  (`ponytail:` note in migration: no runner until migration 003 exists).
- **Feature 2.2 (ErrorCodeLookupTool):** map `meaning` ← `message_en`,
  `manual_section_id` ← `manual_reference`. **Code normalization is your job**: golden
  cases say `"700042"`, the table stores `"AL 700042"` as printed in the manual. Spike A's
  `_normalize_code` only fixes case/whitespace — extend it (strip/try `AL ` prefix).
- **Seed provenance:** 15 rows from the curated SIOS-derived YAML (fw 4.7 SP2); 5 rows
  (`3000`, `10720`, `25050`, `300500`, `600607`) worded from golden cases + standard 840D
  manual, **not yet verified against SIOS** — see the per-row `source` column. Verify
  before any pilot relies on them.
- **Reseeding after YAML updates:** seed SQL was generated from
  `Research_Data/01_error_code_databases/sinumerik_alarms.yaml`; regeneration is a
  15-minute one-off (script pattern in this spec's plan). No generator committed (YAGNI —
  Fanuc/Heidenhain seeds, Feature 2.2, can revive it).

## Deviations from Roadmap (ratified in requirements.md D1–D4)

- Acceptance command: `exec -T postgres ... -d repair < file` (service `postgres`, DB
  `repair`, file streamed — not mounted). Roadmap's `exec db psql -f` never worked.
- `error_codes` columns defined here (Roadmap named none): curated-YAML fields + JSONB
  lists + provenance columns.
- Seed = 15 curated + 5 golden-case/standard codes to reach the requested 20.

---

*Feature 1.1 · Stand: 12. Juli 2026*
