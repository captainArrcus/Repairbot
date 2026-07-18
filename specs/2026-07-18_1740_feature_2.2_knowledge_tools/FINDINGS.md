# Feature 2.2 — ErrorCodeLookupTool + KnowledgeRetrievalTool: Findings / Acceptance

**Status: COMPLETE (dev-verified, 2026-07-18). The knowledge tools are real
modules in `app/tools/`; the Wizard-of-Oz agent walks both paths of the hybrid
winner and streams `tool_call`/`tool_result` events for each.**

## Acceptance evidence (live uvicorn + dev Postgres)

| Check | Result |
|---|---|
| `uv run pytest -q` | **31 passed** (22 existing + 9 new in tests/tools/ + 2 rewritten flow tests) |
| `uv run ruff check app tests` + `format --check app tests` (CI scope) | clean |
| curl: turn "AL 309 beim Verfahren der X-Achse…" | fast path: `error_code_lookup` tool_call/result → 4 cause hypotheses → discriminating question → done |
| curl: turn "Die Spindel erreicht die Drehzahl nicht" (no code) | slow path: `knowledge_retrieval` tool_call/result → candidate hypotheses AL 500 / AL 310 / AL 510 (AL 500 top) → question → done |
| SSE stream | 17 typed events, monotonic wire ids (`1.0…1.8`, `3.0…3.7`) across both turns |
| Normalization | `al-309`, `AL309`, bare `309` → seeded `AL 309`; `f 07011` → `F07011`; bare `10720` found as printed |
| FTS determinism | real hit scores ~0.97, noise ~0.04 → stub threshold 0.1 separates cleanly; vague text ("Maschine macht komische Geräusche") → 0 hits → photo ask preserved |

## Notes for later features

- **Feature 2.5 (embedded hermes):** register `ErrorCodeLookup.lookup` and
  `KnowledgeRetrieval.search_semantic` as hermes tools (names on the wire:
  `error_code_lookup`, `knowledge_retrieval`). The stub's `_MIN_SEARCH_SCORE`
  threshold and confidence ladder are stand-ins for LLM judgment — they die
  with the stub. Tools accept an injected connection (`Tool(conn)`) or open
  their own (`Tool()`).
- **Feature 2.3 (vision):** detected codes from photos should go through
  `ErrorCodeLookup.lookup` — normalization already handles OCR-ish variants
  (`AL309`, `f07011`).
- **PDF corpus (Feature 0.0 gap):** when manuals are ingested, revisit spec D3
  — `search_semantic` moves from on-the-fly FTS over 20 rows to an indexed /
  embedding-backed search; `get_page_image` gets a real backing store.
- **Family-string normalization** (`SINUMERIK_840D` vs `_sl`) is still open —
  the stub passes `controller_family=None` for this reason (spec D2).

## Deviations from Roadmap (ratified in requirements.md, Roadmap corrected)

- Tool returns `manual_reference` (the Feature 1.1 DDL column) — Roadmap said
  `manual_section_id`, which never existed in the schema (D2).
- `lookup(controller_family: str | None, …)` — None searches all families (D2).
- The stub gained the hybrid slow path (semantic candidate search on no exact
  hit) — Roadmap 2.2 only demanded the tools exist, but without a caller the
  acceptance ("agent calls both tools") is unmeetable; D5 keeps it minimal.

---

*Feature 2.2 · Stand: 18. Juli 2026*
