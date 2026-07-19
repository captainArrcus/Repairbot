# Feature 2.7 — Learning Pipeline v1: field → cloud: Requirements

> **One sentence:** Every closed session's learnings (trajectory, new skills, memory)
> flow from the tenant's hermes home to cloud storage — tenant-isolated, with a
> curation gate before any skill crosses a tenant boundary.

---

## Context

The Techstack v3 "what the hermes bet buys us" feature. The raw artifacts already
exist since 2.5: tenant homes produce `trajectory_samples.jsonl` (ShareGPT JSONL,
0.2 Q4), autonomous skills land in `HERMES_HOME/<tenant>/skills/<name>/`, memory in
`memories/`. What's missing is the pipeline: per-session slicing, upload, refs,
curation queue, promotion, fleet distribution.

## Scope (from Roadmap Feature 2.7)

1. `app/services/learning_pipeline.py` — the three streams + curation CLI
2. `db/migrations/003_learning_tables.sql` — `trajectory_refs`, `skill_curation_queue`
3. Trigger wiring (outcome POST) + fleet-skill distribution at worker start
4. Guardrail test: tenant-A skill not loadable by tenant B until promoted

Out of scope: admin UI (Roadmap: CLI/SQL is fine in Phase 2); harvesting sessions
that never get an outcome (D1 ceiling); trajectory compression (D3 → Phase 4);
automated PII/NER scrubbing beyond the tenant-string check (D6 ceiling).

## Decisions

### D1: Trigger = POST /outcome, best-effort

The session's explicit closure point (2.1 Data Bridge; the 2.6 app posts it from
the outcome card). Outcome handler: record outcome (unchanged) → `drop_worker`
(session over, process freed, trajectory file complete — turns are synchronous)
→ `learning_pipeline.harvest_session` best-effort: a pipeline failure logs to
Langfuse (`observability.log_agent_error`) but never fails the outcome POST — the
training label must persist regardless. Sessions abandoned without an outcome are
not harvested in v1 (ceiling: a sweep CLI when pilot data shows abandonment matters).

### D2: Per-session trajectories via session-scoped worker CWD

Hermes appends trajectories to the process CWD (0.2 finding #5); entries carry no
session id. Instead of slicing a shared file by timestamp, the worker CWD moves
from `<tenant_home>` to `<tenant_home>/trajectories/<session_id>/` (created
parent-side in `Worker.__init__`; docker runner: `-w /hermes/trajectories/<sid>`,
same volume). `trajectory_samples.jsonl` there IS the session's trajectory —
zero slicing, zero format guessing. `HERMES_HOME` stays the tenant home
(skills/memory stay tenant-scoped).

### D3: No trajectory_compressor in v1 (Roadmap deviation, mirrored)

The compressor only rewrites trajectories that exceed its token budget (default
16k) and needs the transformers tokenizer plus an LLM summarizer to do so. Our
diagnostic sessions are far below the budget — running it would be a dependency-
heavy no-op. v1 uploads the raw JSONL gzipped. Revisit when Phase 4 fine-tuning
prep actually sees over-budget trajectories (the file format is compressor-
compatible — it can run as a batch step then).

### D4: Cloud layout — same bucket, `learning/` prefix; refs in Postgres

- Trajectory: `learning/<tenant>/trajectories/<session_id>.jsonl.gz` +
  `trajectory_refs` row (tenant_id, session_id, s3_key, entry_count).
- Memory: `learning/<tenant>/memory.tar.gz` — latest-snapshot backup, overwritten
  per harvest (it's a backup, not history; never shared, never crosses tenants).
- No new bucket, no new infra: `storage.put_object` (2.3) does the upload.

### D5: Skills stream = post-session scan + content-hash dedupe

After each harvested session, scan `<tenant_home>/skills/*/`: read all files per
skill dir, sha256 the content. Unknown (tenant, name, hash) → insert into
`skill_curation_queue` with status `pending_review` and the full content stored
in the row (skills are small markdown — no S3 detour). Re-scans and unchanged
skills are no-ops (unique index on tenant/name/hash).

### D6: Curation gate = CLI promotion with automated tenant-string scrub

`python -m app.services.learning_pipeline queue|promote <id>|reject <id>`.
Promote: refuse if the tenant id appears in the skill content (case-insensitive)
— the automated scrub; the human running the CLI is the human approval (Roadmap:
manual review is fine in Phase 2). On promote: write the skill files to the fleet
skill base (`FLEET_SKILLS_DIR`, config, default `agents/.hermes_fleet_skills/`),
set status `promoted`. Ceiling: string-match scrub only — NER/PII scrubbing when
curation volume demands it.

### D7: Fleet distribution = sync at worker start

`Worker.__init__` copies fleet skills into the tenant's `skills/` before hermes
boots — only skill names the tenant doesn't already have (a tenant's own skill
always wins, never overwritten). This is the redistribution mechanism: promoted
skills reach every tenant lazily at their next session, and the guardrail test
falls out naturally (tenant B lacks A's skill until promotion + next session).

### D8: Works without hermes — graceful no-ops

Every stream skips missing dirs/empty files silently (scripted backend produces
no tenant home). Tests fabricate tenant homes (fake JSONL, fake skill dirs) and a
fake S3 — no LLM, no worker, CI-safe.
