# Feature 2.8 — Controller-family normalization

## Problem

The 2.2-D2 gap (family-string normalization declared out of scope) bit twice:

- 2.3: vision returns brand-level `detected_controller` ("SINUMERIK"), seeds
  store `SINUMERIK_840D_sl` — the brand string can never exact-match.
- 2.5 finding #2: the hermes agent passes "SINUMERIK" as
  `controller_family`, exact lookup misses, and the dispatcher's family=None
  retry masks the miss instead of solving it.

## Requirement

Canonical family-alias map — **data, not code** — living in
`app/tools/error_code_lookup.py` next to the existing code normalization:
brand + variant strings → seeded `controller_family` values. Applied inside
`ErrorCodeLookup.lookup()`, so every caller (scripted agent_service, hermes
dispatcher, KnowledgeRetrieval delegate) gets it for free.

## Decisions

- D1: Normalization lives in the tool's `lookup()`, not in callers — one
  guard where all callers route through.
- D2: Unmapped family strings pass through unchanged. A family with no seeds
  (HEIDENHAIN, FANUC today) honestly returns no rows; silently widening to
  all families would reintroduce the masking the retry had.
- D3: Alias keys are normalized (upper, `[\s\-_]+` → `_`), so casing and
  separator variants ("siemens sinumerik", "840d-sl") need no extra entries.
- D4: Map extension is part of seeding new controller families — noted in
  the map's comment.

## Acceptance (from Roadmap)

- `lookup("SINUMERIK", "AL 309")` exact-hits without the family=None retry.
- The 2.5 dispatcher retry is dead code and removed.
