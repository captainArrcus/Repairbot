# Feature 1.1 — Plan

1. `db/migrations/001_create_schema.sql` — Techstack v3 Session Trace Schema verbatim
   (5 tables) + `diagnostic_turn_events` (Roadmap exact SQL) + `error_codes` (shape per
   requirements D2). Single transaction, plain psql.
2. `db/seeds/seed_error_codes.sql` — generated from
   `Research_Data/01_error_code_databases/sinumerik_alarms.yaml` (15 entries) + 5 inline
   extras (D3). Idempotent insert.
3. Apply both against the dev stack (`repair` DB), verify `\dt` + count = 20, rerun seed
   (must insert 0).
4. `tests/test_schema.py` — tables exist, ≥20 SINUMERIK codes, AL 309 carries
   discriminating questions; skips without DB.
5. Mirror back: Roadmap Feature 1.1 → DONE + corrected acceptance command; Techstack
   schema section gains the `error_codes` DDL.

*Feature 1.1 · Stand: 12. Juli 2026*
