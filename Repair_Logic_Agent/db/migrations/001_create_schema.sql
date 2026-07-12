-- Feature 1.1 — Data Bridge schema + error_codes.
-- Session-trace tables verbatim from Techstack v3 "Session Trace Schema";
-- diagnostic_turn_events verbatim from Roadmap Feature 1.1.
--
-- Apply (dev stack, database "repair"):
--   docker compose -f infra/docker-compose.yml exec -T postgres \
--     psql -U postgres -d repair -v ON_ERROR_STOP=1 < db/migrations/001_create_schema.sql
--
-- ponytail: no migration runner — plain psql, rerun fails atomically (single
-- transaction). Add a runner when migration 003 exists.

BEGIN;

CREATE TABLE diagnostic_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    machine_family TEXT NOT NULL,
    controller_family TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'active',  -- active | resolved | escalated | failed
    metadata JSONB                 -- user_skill_level, factory, etc.
);

CREATE TABLE diagnostic_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES diagnostic_sessions(id),
    turn_index INT NOT NULL,
    role TEXT NOT NULL,             -- 'user' | 'agent'
    content TEXT,
    media_refs TEXT[],              -- S3 keys
    tools_called JSONB,             -- [{tool, args, result_summary}]
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE hypotheses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES diagnostic_sessions(id),
    introduced_at_turn INT NOT NULL,
    description TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    eliminated_at_turn INT,         -- NULL if still active
    elimination_reason TEXT,
    is_final_diagnosis BOOLEAN DEFAULT false
);

CREATE TABLE hypothesis_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis_id UUID REFERENCES hypotheses(id),
    turn_id UUID REFERENCES diagnostic_turns(id),
    confidence_before FLOAT,
    confidence_after FLOAT,
    evidence_text TEXT,             -- what caused the update
    evidence_media_ref TEXT         -- S3 key if visual evidence
);

CREATE TABLE session_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES diagnostic_sessions(id) UNIQUE,
    outcome TEXT NOT NULL,          -- 'resolved' | 'escalated' | 'failed'
    final_diagnosis_id UUID REFERENCES hypotheses(id),
    repair_action TEXT,
    verification_media_ref TEXT,    -- photo confirming fix
    resolution_time_minutes INT,
    technician_confidence INT,      -- 1-5 self-reported
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE diagnostic_turn_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id UUID REFERENCES diagnostic_turns(id),
    event_index INT,
    event_type TEXT,
    event_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Exact-lookup fast path of the hybrid knowledge winner (Feature 0.1) and the
-- ErrorCodeLookupTool contract (Feature 2.2): lookup(controller_family, code).
-- Columns mirror Research_Data/01_error_code_databases/*.yaml entries.
-- Codes are stored as printed in the manual ("AL 309", "F07011"); query-time
-- normalization (prefix/whitespace/case) is the lookup tool's job (Feature 2.2).
CREATE TABLE error_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    controller_family TEXT NOT NULL,
    code TEXT NOT NULL,
    category TEXT,                  -- NC | DRV | PLC | HMI
    severity TEXT,                  -- error | warning | fault
    message_de TEXT,
    message_en TEXT,
    probable_causes JSONB NOT NULL DEFAULT '[]',
    recommended_actions JSONB NOT NULL DEFAULT '[]',
    related_components JSONB NOT NULL DEFAULT '[]',
    discriminating_questions JSONB NOT NULL DEFAULT '[]',
    manual_reference TEXT,
    spare_part_refs JSONB NOT NULL DEFAULT '[]',
    software_version TEXT,          -- alarm meanings are firmware-version-specific
    source TEXT,
    UNIQUE (controller_family, code)
);

COMMIT;
