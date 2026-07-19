# Feature 2.8 — Plan

1. `app/tools/error_code_lookup.py`
   - `FAMILY_ALIASES` dict (normalized alias → seeded canonical value)
   - `_canonical_family(family)` helper; applied at the top of `lookup()`
2. `app/services/hermes_backend.py`
   - remove the family=None retry in the `error_code_lookup` dispatch branch
3. Comment congruence
   - `app/services/agent_service.py`: None-filter comment now cites the alias map
   - `app/tools/vision_analysis.py`: docstring no longer calls 2.2-D2 open
4. Tests (`tests/tools/test_tools.py`)
   - `test_family_normalization` (no DB): alias, casing/separator variants,
     canonical identity, unmapped pass-through, None/blank
   - `test_lookup_brand_level_family_exact_hits` (DB): the acceptance case
5. Verify: `uv run pytest` (full suite), `uv run ruff check`
6. Docs: Roadmap 2.8 → DONE; Techstack tool table mentions family aliases
