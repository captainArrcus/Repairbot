"""Feature 2.11: the dev/field .env defaults AGENT_BACKEND=hermes; the suite
must stay deterministic on the scripted backend (2.5 D7). Hermes-path tests
opt in explicitly via their own monkeypatch (which wins over this autouse pin).
"""

import pytest

from app import config


@pytest.fixture(autouse=True)
def _scripted_backend_default(monkeypatch):
    monkeypatch.setattr(config, "AGENT_BACKEND", "scripted")
