# Feature 2.1 — Data Bridge completion & export: Findings / Acceptance

**Status: COMPLETE (dev-verified, 2026-07-12). Sessions are now full training
traces: hypotheses + updates + outcome in first-class tables, export endpoint
returns the Roadmap training JSON.**

## Acceptance evidence (live uvicorn + dev Postgres)

| Check | Result |
|---|---|
| `uv run pytest -q` | **21 passed** (14 existing + 7 new in tests/traces/) |
| `uv run ruff check` + `format --check` | clean |
| curl: session → turn ("AL 309 …", media_key) → outcome → export | full JSON: machine_context, initial_observation (media_keys + symptom), 2-entry diagnostic_chain (user + agent with 9 events), final_diagnosis, outcome |
| `hypotheses` rows after turn | 4 (probable_causes ladder) + 1 technician-named final (confidence 1.0, is_final_diagnosis=t) |
| `session_outcomes` row | outcome=resolved, repair_action, technician_confidence=5; `diagnostic_sessions.status` mirrored to resolved |
| hypothesis_updates on confidence delta | before/after + evidence_text row, confidence updated (test_confidence_change_writes_hypothesis_update) |
| outcome correction (2nd POST without final_diagnosis) | upsert keeps final_diagnosis_id (COALESCE) — no label loss |
| export mid-session / empty session / ghost session | nulls (D6) / empty chain / 404 |

## Notes for later features

- **Feature 2.5 (embedded hermes):** `_persist_hypotheses` upserts by
  (session_id, description) with SELECT-then-INSERT — single writer per turn
  transaction. Concurrent writers need a unique index (ponytail note in code).
  The real agent should emit stable hypothesis descriptions or carry its own
  hypothesis identity through to persistence.
- **Feature 2.6 (mobile app):** outcome form posts to
  `POST /api/v1/sessions/{id}/outcome` (outcome, final_diagnosis text,
  repair_action, verification_media_ref, resolution_time_minutes,
  technician_confidence 1–5). Re-POST is a safe correction (upsert).
- **Feature 2.7 (learning pipeline):** `traces.assemble_export()` is the
  Postgres-truth export; the hermes trajectory format is additional, not a
  replacement (Techstack). `hypotheses_before/after` per chain step was NOT
  duplicated into the export (spec D4) — reconstruct from hypotheses +
  hypothesis_updates if the trajectory compressor needs it.

## Deviations from Roadmap (ratified in requirements.md, Roadmap corrected)

- `POST /api/v1/sessions/{id}/outcome` added — Roadmap 2.1 listed no outcome
  write path but the export's training label requires one (D3, user-ratified
  2026-07-12). Unknown final_diagnosis text becomes a new hypothesis row
  (confidence 1.0) — technician-named diagnoses the agent never raised are
  training signal, not errors.
- No new SQL migration — all six tables shipped with Feature 1.1 (D1).

---

*Feature 2.1 · Stand: 12. Juli 2026*
