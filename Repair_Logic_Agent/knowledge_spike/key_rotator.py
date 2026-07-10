"""Round-robin over multiple Google API keys to spread rate-limit load.

TEST-ONLY helper for the knowledge spike. Production uses a single key — this
module exists so the free-tier RPM quota (~10 req/min/key) doesn't throttle the
evaluation. Delete when moving to a paid key or production.
"""
import itertools
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Order matters only for reproducibility; all are used round-robin.
_KEY_NAMES = ("GOOGLE_API_KEY", "TWOGOOGLE_API_KEY", "NEW_GOOGLE_API_KEY")

_keys = [v for n in _KEY_NAMES if (v := os.getenv(n))]
_cycle = itertools.cycle(_keys) if _keys else None


def next_key() -> str | None:
    """Next API key in round-robin order, or None if none are set."""
    return next(_cycle) if _cycle else None


def key_count() -> int:
    return len(_keys)


if __name__ == "__main__":
    # ponytail: self-check — proves rotation cycles through every key.
    n = key_count()
    print(f"{n} key(s) loaded: {[nm for nm in _KEY_NAMES if os.getenv(nm)]}")
    assert n >= 1, "no Google API keys found in .env"
    seen = {next_key() for _ in range(n)}
    assert len(seen) == n, "rotation did not cover all distinct keys"
    print("rotation OK")
