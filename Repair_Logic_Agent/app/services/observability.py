"""Cross-cutting observability (Roadmap): agent errors go to Langfuse + logs.

Sanitized/suppressed agent output and worker failures are recorded here (spec
2.5 D4/D5) — the raw payload lands in Langfuse for eval, never in the stream.
"""

import logging

from app import config

log = logging.getLogger("repair.agent")

_langfuse = None


def _client():
    global _langfuse
    if _langfuse is None and config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        from langfuse import Langfuse

        _langfuse = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_HOST,
        )
    return _langfuse


def log_agent_error(session_id: str, kind: str, detail: str) -> None:
    """kind: invalid_event | suppressed_event | allowlist_breach | worker_error"""
    log.warning("agent %s [%s]: %s", kind, session_id, detail[:500])
    client = _client()
    if client is None:
        return
    try:
        client.create_event(
            name=f"agent_{kind}",
            metadata={"session_id": session_id, "detail": detail[:2000]},
        )
    except Exception:  # observability must never break a turn
        log.exception("langfuse event failed")
