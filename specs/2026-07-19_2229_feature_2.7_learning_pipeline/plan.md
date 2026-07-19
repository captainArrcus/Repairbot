# Feature 2.7 — Plan

## Files

| File | Content |
|---|---|
| `db/migrations/003_learning_tables.sql` | `trajectory_refs` + `skill_curation_queue` (D4/D5) |
| `app/services/learning_pipeline.py` | `harvest_session()` (three streams, D2–D5, D8) + `queue`/`promote`/`reject` CLI (D6) |
| `app/services/hermes_backend.py` | session-scoped worker CWD (D2), fleet-skill sync in `Worker.__init__` (D7) |
| `app/api/sessions.py` | outcome route: `drop_worker` + best-effort harvest (D1) |
| `app/config.py` | `FLEET_SKILLS_DIR` |
| `tests/agent/test_learning_pipeline.py` | streams, dedupe, scrub gate, cross-tenant guardrail |

## Order

1. Migration 003, apply to dev DB
2. `learning_pipeline.py` (harvest + CLI)
3. `hermes_backend.py` CWD + fleet sync; `config.py`
4. Outcome route wiring
5. Tests, lint
6. Live acceptance: dev session (hermes backend) → outcome → trajectory in
   MinIO + ref row; synthetic skill → queue → promote → tenant-B session sees it
7. FINDINGS.md + mirror D3 (no compressor) into Roadmap.md, mark 2.7 DONE

## Test flow

```
pytest tests/agent/test_learning_pipeline.py   # fabricated homes + fake S3
# live (hermes backend, docker-compose infra up):
AGENT_BACKEND=hermes uvicorn app.main:app  →  run a session on /docs or curl
curl -X POST .../sessions/{id}/outcome -d '{"outcome":"resolved"}'
mc ls local/repair-media/learning/<tenant>/trajectories/   # <sid>.jsonl.gz
psql: select * from trajectory_refs; select * from skill_curation_queue;
python -m app.services.learning_pipeline queue / promote <id>
# new session as tenant B → skills index in prompt contains promoted skill
```

---

*Feature 2.7 · Stand: 2026-07-19*
