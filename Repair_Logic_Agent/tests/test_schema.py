"""Feature 1.1 smoke check: schema applied + error codes seeded.

Needs the dev Postgres (docker compose -f infra/docker-compose.yml up -d);
skips otherwise, e.g. in CI.
"""

import psycopg
import pytest

from app.config import DATABASE_URL

TABLES = {
    "diagnostic_sessions",
    "diagnostic_turns",
    "hypotheses",
    "hypothesis_updates",
    "session_outcomes",
    "diagnostic_turn_events",
    "error_codes",
}


@pytest.fixture(scope="module")
def conn():
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("dev Postgres not running")
    with c:
        yield c


def test_all_tables_exist(conn):
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = 'public'"
    ).fetchall()
    assert TABLES <= {r[0] for r in rows}


def test_error_codes_seeded(conn):
    (n,) = conn.execute(
        "select count(*) from error_codes where controller_family like 'SINUMERIK%'"
    ).fetchone()
    assert n >= 20


def test_al309_has_discriminating_questions(conn):
    (n,) = conn.execute(
        "select jsonb_array_length(discriminating_questions) from error_codes where code = 'AL 309'"
    ).fetchone()
    assert n >= 1
