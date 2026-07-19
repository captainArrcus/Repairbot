"""Feature 2.7 — Learning Pipeline v1: field → cloud.

Three streams per closed session (Techstack §Learning Pipeline):
trajectory → S3 + trajectory_refs row; new/changed skills → skill_curation_queue
(pending_review); memory → tenant-scoped S3 backup. Curation gate (spec D6):
`python -m app.services.learning_pipeline queue|promote <id>|reject <id>` —
nothing crosses a tenant boundary without the scrub check + a human promote.

Trajectories are per-session because the worker CWD is session-scoped (spec D2,
hermes appends to CWD — 0.2 finding #5). Every stream no-ops on missing files
(spec D8: the scripted backend produces no tenant home).
"""

import gzip
import hashlib
import json
import sys
import tarfile
from io import BytesIO
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import config, db
from app.services import storage


def harvest_session(session_id: str) -> None:
    """Run all three streams for a closed session. Idempotent: re-harvest
    skips an uploaded trajectory and queues no duplicate skills."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT tenant_id FROM diagnostic_sessions WHERE id = %s", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        tenant_id = row[0]
        home = Path(config.HERMES_HOME_ROOT) / tenant_id
        _harvest_trajectory(conn, tenant_id, session_id, home)
        _harvest_skills(conn, tenant_id, home)
        conn.commit()
    _backup_memory(tenant_id, home)


def _harvest_trajectory(conn, tenant_id: str, session_id: str, home: Path) -> None:
    path = home / "trajectories" / session_id / "trajectory_samples.jsonl"
    if not path.is_file():
        return
    if conn.execute(
        "SELECT 1 FROM trajectory_refs WHERE session_id = %s", (session_id,)
    ).fetchone():
        return
    raw = path.read_bytes()
    entries = sum(1 for line in raw.splitlines() if line.strip())
    if not entries:
        return
    # raw ShareGPT JSONL, gzipped — no trajectory_compressor in v1 (spec D3:
    # it only rewrites trajectories over its token budget; ours are far below)
    s3_key = f"learning/{tenant_id}/trajectories/{session_id}.jsonl.gz"
    storage.put_object(s3_key, gzip.compress(raw), "application/gzip")
    conn.execute(
        """INSERT INTO trajectory_refs (tenant_id, session_id, s3_key, entry_count)
           VALUES (%s, %s, %s, %s)""",
        (tenant_id, session_id, s3_key, entries),
    )


def _harvest_skills(conn, tenant_id: str, home: Path) -> None:
    skills_dir = home / "skills"
    if not skills_dir.is_dir():
        return
    for skill_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        content = _skill_content(skill_dir)
        if not content:
            continue
        digest = _content_hash(content)
        # a fleet skill synced into this home (spec D7) is not a new learning;
        # a tenant's MODIFIED copy hashes differently and is queued
        fleet_copy = Path(config.FLEET_SKILLS_DIR) / skill_dir.name
        if fleet_copy.is_dir() and _content_hash(_skill_content(fleet_copy)) == digest:
            continue
        conn.execute(
            """INSERT INTO skill_curation_queue (tenant_id, skill_name, content_hash, content)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (tenant_id, skill_name, content_hash) DO NOTHING""",
            (tenant_id, skill_dir.name, digest, Jsonb(content)),
        )


def _skill_content(skill_dir: Path) -> dict[str, str]:
    return {
        str(p.relative_to(skill_dir)): p.read_text(errors="replace")
        for p in sorted(skill_dir.rglob("*"))
        if p.is_file()
    }


def _content_hash(content: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def _backup_memory(tenant_id: str, home: Path) -> None:
    memories = home / "memories"
    if not memories.is_dir() or not any(p.is_file() for p in memories.rglob("*")):
        return
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(memories, arcname="memories")
    # latest-snapshot backup, overwritten per harvest (spec D4); never shared
    storage.put_object(f"learning/{tenant_id}/memory.tar.gz", buf.getvalue(), "application/gzip")


# --- curation gate (spec D6) ---


def promote(conn, queue_id: str) -> Path:
    """Scrub-check a queued skill and copy it into the fleet skill base.
    Raises KeyError (unknown id), ValueError (scrub failed / bad state)."""
    row = conn.execute(
        "SELECT tenant_id, skill_name, content, status FROM skill_curation_queue WHERE id = %s",
        (queue_id,),
    ).fetchone()
    if row is None:
        raise KeyError(queue_id)
    tenant_id, skill_name, content, status = row
    if status != "pending_review":
        raise ValueError(f"queue entry is {status!r}, not pending_review")
    # ponytail: tenant-string scrub only; NER/PII scrubbing when curation volume demands it
    if tenant_id.lower() in json.dumps(content).lower():
        raise ValueError(
            f"scrub failed: content mentions tenant {tenant_id!r} — edit before promoting"
        )
    dest = Path(config.FLEET_SKILLS_DIR) / skill_name
    for fname, text in content.items():
        if ".." in Path(fname).parts or Path(fname).is_absolute():
            raise ValueError(f"unsafe path in skill content: {fname!r}")
        target = dest / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    _set_status(conn, queue_id, "promoted")
    return dest


def _set_status(conn, queue_id: str, status: str) -> None:
    conn.execute(
        "UPDATE skill_curation_queue SET status = %s, reviewed_at = now() WHERE id = %s",
        (status, queue_id),
    )
    conn.commit()


def _cli(argv: list[str]) -> None:
    cmd = argv[0] if argv else "queue"
    with db.connect() as conn:
        if cmd == "queue":
            rows = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    """SELECT id, tenant_id, skill_name, status, created_at
                       FROM skill_curation_queue ORDER BY created_at"""
                )
                .fetchall()
            )
            for r in rows:
                print(f"{r['id']}  [{r['status']:>14}]  {r['tenant_id']}/{r['skill_name']}")
            print(f"{len(rows)} entries")
        elif cmd == "promote":
            dest = promote(conn, argv[1])
            print(f"promoted → {dest}")
        elif cmd == "reject":
            _set_status(conn, argv[1], "rejected")
            print("rejected")
        else:
            sys.exit("usage: python -m app.services.learning_pipeline [queue|promote ID|reject ID]")


if __name__ == "__main__":
    _cli(sys.argv[1:])
