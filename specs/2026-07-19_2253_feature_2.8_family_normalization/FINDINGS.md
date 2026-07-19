# Feature 2.8 — FINDINGS

Implemented 2026-07-19. ~30 lines of diff total.

## Verification

- Full suite: `uv run pytest` → 69 passed (dev Postgres up, DB-backed tests ran).
- Acceptance case ran against the real seed:
  `ErrorCodeLookup().lookup("SINUMERIK", "AL 309")["code"] == "AL 309"` —
  exact hit through the alias map, no family=None retry in the code path.
- Dispatcher retry removed from `hermes_backend.py`; agent/golden tests green.
- `uv run ruff check` clean.

## Findings

1. Only ONE controller family is seeded so far (`SINUMERIK_840D_sl`, 20 rows).
   The alias map therefore has one canonical target; the mechanism (normalized
   key → seeded value) is what 2.8 adds. When HEIDENHAIN/FANUC seeds land,
   extend `FAMILY_ALIASES` in the same commit as the seed batch (map comment
   says so).
2. Unmapped families pass through unchanged (spec D2): `lookup("FANUC_30i",
   "AL 309")` still correctly returns None — no silent widening.
3. agent_service's scripted path keeps `family=None` deliberately: it does the
   broadest exact-code search across candidate codes and never had the masking
   problem; comment updated to cite the alias map instead of the old gap.
