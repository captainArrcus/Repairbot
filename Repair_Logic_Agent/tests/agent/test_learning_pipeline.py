"""Feature 2.7: learning pipeline — streams, dedupe, curation gate, and the
non-negotiable guardrail (nothing crosses a tenant boundary without promotion).
Fabricated tenant homes + faked S3 (spec D8) — no hermes venv, no LLM; needs
the dev Postgres for the refs/queue tables."""

import gzip
import io
import json
import tarfile
import uuid

import psycopg
import pytest

from app import config, db
from app.services import hermes_backend, learning_pipeline, storage


def _dev_db_ready() -> bool:
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT 1 FROM trajectory_refs LIMIT 1")
            conn.execute("SELECT 1 FROM skill_curation_queue LIMIT 1")
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _dev_db_ready(), reason="dev Postgres with migration 003 not available"
)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    """Isolated homes + fleet dir + in-memory S3; a fresh session row per test."""
    monkeypatch.setattr(config, "HERMES_HOME_ROOT", str(tmp_path / "homes"))
    monkeypatch.setattr(config, "FLEET_SKILLS_DIR", str(tmp_path / "fleet"))
    s3: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "put_object", lambda key, data, ct: s3.__setitem__(key, data))

    class Env:
        home_root = tmp_path / "homes"
        fleet = tmp_path / "fleet"
        uploads = s3

        def session(self, tenant: str) -> str:
            with db.connect() as conn:
                row = conn.execute(
                    """INSERT INTO diagnostic_sessions (tenant_id, machine_family)
                       VALUES (%s, 'cnc') RETURNING id""",
                    (tenant,),
                ).fetchone()
                conn.commit()
                return str(row[0])

        def write_trajectory(self, tenant: str, session_id: str, entries: int = 2) -> None:
            d = self.home_root / tenant / "trajectories" / session_id
            d.mkdir(parents=True)
            lines = [json.dumps({"conversations": [], "completed": True})] * entries
            (d / "trajectory_samples.jsonl").write_text("\n".join(lines) + "\n")

        def write_skill(self, tenant: str, name: str, body: str) -> None:
            d = self.home_root / tenant / "skills" / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(body)

        def queue_rows(self, tenant: str) -> list:
            with db.connect() as conn:
                return conn.execute(
                    """SELECT id, skill_name, status FROM skill_curation_queue
                       WHERE tenant_id = %s ORDER BY created_at""",
                    (tenant,),
                ).fetchall()

    return Env()


def _tenant() -> str:
    return f"lpt-{uuid.uuid4().hex[:8]}"


def test_trajectory_uploaded_gzipped_with_ref(env):
    tenant = _tenant()
    sid = env.session(tenant)
    env.write_trajectory(tenant, sid, entries=3)

    learning_pipeline.harvest_session(sid)
    learning_pipeline.harvest_session(sid)  # idempotent re-harvest

    key = f"learning/{tenant}/trajectories/{sid}.jsonl.gz"
    assert key in env.uploads
    assert gzip.decompress(env.uploads[key]).count(b"\n") == 3
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT entry_count FROM trajectory_refs WHERE session_id = %s", (sid,)
        ).fetchall()
    assert rows == [(3,)]


def test_no_home_is_a_noop(env):
    sid = env.session(_tenant())  # scripted backend: no tenant home exists
    learning_pipeline.harvest_session(sid)
    assert env.uploads == {}


def test_skill_queued_once_and_requeued_on_change(env):
    tenant = _tenant()
    sid = env.session(tenant)
    env.write_skill(tenant, "al309-check", "measure axial play")

    learning_pipeline.harvest_session(sid)
    learning_pipeline.harvest_session(sid)
    assert [r[1:] for r in env.queue_rows(tenant)] == [("al309-check", "pending_review")]

    env.write_skill(tenant, "al309-check", "measure axial play, then check coupling")
    learning_pipeline.harvest_session(sid)
    assert len(env.queue_rows(tenant)) == 2


def test_memory_backed_up_as_tarball(env):
    tenant = _tenant()
    sid = env.session(tenant)
    mem = env.home_root / tenant / "memories"
    mem.mkdir(parents=True)
    (mem / "site.md").write_text("Halle 3, Hermle C42")

    learning_pipeline.harvest_session(sid)

    with tarfile.open(fileobj=io.BytesIO(env.uploads[f"learning/{tenant}/memory.tar.gz"])) as tar:
        assert "memories/site.md" in tar.getnames()


def test_scrub_blocks_tenant_identifying_content(env):
    tenant = _tenant()
    sid = env.session(tenant)
    env.write_skill(tenant, "leaky", f"customer {tenant} always has this fault")
    learning_pipeline.harvest_session(sid)
    ((queue_id, _, _),) = env.queue_rows(tenant)

    with db.connect() as conn:
        with pytest.raises(ValueError, match="scrub failed"):
            learning_pipeline.promote(conn, str(queue_id))
    assert env.queue_rows(tenant)[0][2] == "pending_review"
    assert not (env.fleet / "leaky").exists()


def test_cross_tenant_guardrail_until_promoted(env):
    """The Roadmap guardrail test: tenant A's skill is not loadable by tenant B
    unless promoted through the curation gate."""
    tenant_a, tenant_b = _tenant(), _tenant()
    sid = env.session(tenant_a)
    env.write_skill(tenant_a, "spindle-warmup", "run warmup cycle before probing")
    learning_pipeline.harvest_session(sid)

    home_b = env.home_root / tenant_b
    hermes_backend._sync_fleet_skills(home_b)  # worker start, pre-promotion
    assert not (home_b / "skills" / "spindle-warmup").exists()

    ((queue_id, _, _),) = env.queue_rows(tenant_a)
    with db.connect() as conn:
        learning_pipeline.promote(conn, str(queue_id))
    assert env.queue_rows(tenant_a)[0][2] == "promoted"

    hermes_backend._sync_fleet_skills(home_b)  # worker start, post-promotion
    assert (home_b / "skills" / "spindle-warmup" / "SKILL.md").read_text() == (
        "run warmup cycle before probing"
    )

    # a synced fleet skill is not re-queued as tenant B's own learning
    sid_b = env.session(tenant_b)
    learning_pipeline.harvest_session(sid_b)
    assert env.queue_rows(tenant_b) == []
