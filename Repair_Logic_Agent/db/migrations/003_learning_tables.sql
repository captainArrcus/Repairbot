-- Feature 2.7 — Learning Pipeline v1: trajectory refs + skill curation queue
-- (spec D4/D5; Techstack §Learning Pipeline — field → cloud).
--
-- Apply (dev stack, database "repair"):
--   docker compose -f infra/docker-compose.yml exec -T postgres \
--     psql -U postgres -d repair -v ON_ERROR_STOP=1 < db/migrations/003_learning_tables.sql

BEGIN;

CREATE TABLE trajectory_refs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    session_id UUID NOT NULL REFERENCES diagnostic_sessions(id),
    s3_key TEXT NOT NULL,
    entry_count INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (session_id)
);

CREATE TABLE skill_curation_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content JSONB NOT NULL,  -- {filename: text} — skills are small markdown
    status TEXT NOT NULL DEFAULT 'pending_review',  -- pending_review|promoted|rejected
    created_at TIMESTAMPTZ DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    UNIQUE (tenant_id, skill_name, content_hash)
);

COMMIT;
