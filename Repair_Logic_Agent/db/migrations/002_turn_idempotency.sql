-- Feature 1.3 — turn idempotency (Techstack API contract: "Turn submissions are
-- idempotent via client-generated idempotency_key"; flaky factory WiFi retries).
--
-- Apply (dev stack, database "repair"):
--   docker compose -f infra/docker-compose.yml exec -T postgres \
--     psql -U postgres -d repair -v ON_ERROR_STOP=1 < db/migrations/002_turn_idempotency.sql

BEGIN;

ALTER TABLE diagnostic_turns ADD COLUMN idempotency_key TEXT;

CREATE UNIQUE INDEX diagnostic_turns_idempotency_uq
    ON diagnostic_turns (session_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

COMMIT;
