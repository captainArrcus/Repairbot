# Feature 2.7 — Learning Pipeline v1: Findings / Acceptance

**Status: COMPLETE — 2026-07-19, all three streams live-verified end to end
(hermes backend, real LLM session → outcome → S3 + queue → promote → tenant B).**

## Acceptance evidence

| Check (Roadmap) | Result |
|---|---|
| Dev session → trajectory in S3 + ref row in Postgres | **PASS** — live session `a44c71c0…` (tenant `acceptance27`, hermes backend, AL 309 turn): `learning/acceptance27/trajectories/<sid>.jsonl.gz` (5.6 KB) in MinIO, `trajectory_refs` row with entry_count=1 |
| Synthetic skill lands in the curation queue | **PASS** — `al309-axial-play` → `skill_curation_queue` status `pending_review` on outcome POST |
| Promotion copies it to the fleet skill base | **PASS** — `python -m app.services.learning_pipeline promote <id>` → `agents/.hermes_fleet_skills/al309-axial-play/`, status `promoted` |
| A tenant-B session can then use it | **PASS** — new session as `acceptance27b`: skill synced into its home at worker start AND present in `.skills_prompt_snapshot.json` (in the system-prompt skills index) |
| Guardrail: tenant-A skill NOT loadable by tenant B unless promoted | **PASS** — `test_cross_tenant_guardrail_until_promoted` (pre-promotion sync leaves B empty; scrub blocks tenant-string content; synced fleet skill is not re-queued as B's learning) |
| Tests + lint | **PASS** — 67 passed (6 new in `tests/agent/test_learning_pipeline.py`), ruff clean |

## What we had to learn

1. **Per-session trajectories cost one line, not a parser.** Hermes appends
   `trajectory_samples.jsonl` to the process CWD and entries carry no session id
   — session-scoped worker CWD (`<home>/trajectories/<sid>/`, spec D2) makes the
   file per-session by construction. Verified live: the file appeared in the
   session dir during turn 1.
2. **Fleet sync must not echo back into the queue.** A promoted skill synced
   into a tenant home would be re-harvested as that tenant's "learning" — the
   harvester skips skills whose content hash matches the fleet copy; a tenant's
   *modified* copy hashes differently and is queued (that's a curatable
   improvement, not noise).
3. **Port 8000 was occupied by the running dev server** during acceptance — ran
   the hermes-backend instance on 8010. No code impact.

## Notes for later features

- **Feature 3.1 (deploy):** memory stream is unit-tested but was not exercised
  live (a one-turn session writes no memories); `learning/<tenant>/memory.tar.gz`
  is a latest-snapshot overwrite, not history.
- **Feature 3.2/4+ (fine-tuning prep):** `trajectory_compressor` deliberately
  not wired (spec D3) — raw gzipped ShareGPT JSONL is compressor-compatible;
  run it as a batch step when trajectories exceed the token budget.
- **Backlog:** sessions abandoned without an outcome are never harvested (spec
  D1 ceiling — sweep CLI when pilot data shows it matters); scrub is
  tenant-string match only (D6 ceiling — NER/PII when curation volume demands);
  fleet skills reach a tenant at the *next* worker start (workers are
  per-session, so effectively next session).

## Deviations from Roadmap

- **No `trajectory_compressor` in v1** (Roadmap said "compressed via
  trajectory_compressor") — it only rewrites trajectories above its ~16k token
  budget and needs transformers + an LLM summarizer; our sessions are far below.
  Ratified in requirements D3, mirrored in Roadmap.
- Migration file is `003_learning_tables.sql` (Roadmap placeholder said `00X`).
- Trigger point pinned to POST /outcome, best-effort (D1) — Roadmap only said
  "after each session".

---

*Feature 2.7 · Stand: 2026-07-19 · 67 tests green, live acceptance complete.*
