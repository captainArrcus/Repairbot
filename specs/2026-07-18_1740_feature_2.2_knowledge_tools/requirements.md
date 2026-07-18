# Feature 2.2 — ErrorCodeLookupTool + KnowledgeRetrievalTool: Requirements

> **One sentence:** The knowledge tools become real modules in `app/tools/` — exact
> error-code lookup with query-time normalization plus the KnowledgeLayer retrieval
> interface — and the Wizard-of-Oz agent calls them, streaming `tool_call`/`tool_result`
> events for both paths of the hybrid knowledge winner.

---

## Context

The Feature 1.3 stub does its own inline regex + SQL lookup inside
`agent_service.py`. Feature 2.2 extracts that into the two tool modules the
embedded hermes agent will register in Feature 2.5, adds the normalization the
Techstack explicitly assigns to this feature ("codes are stored as printed in
the manual — query-time normalization belongs to the ErrorCodeLookupTool"), and
gives the stub the hybrid slow path: semantic candidate search when there is no
exact code hit (knowledge-spike FINDINGS: structured spine + narrowed candidates).

## Scope (from Roadmap Feature 2.2)

1. `app/tools/error_code_lookup.py` — `class ErrorCodeLookup`,
   `lookup(controller_family, code) -> Optional[dict]`, plus code extraction +
   normalization (moved out of `agent_service`)
2. `app/tools/knowledge_layer.py` — `class KnowledgeRetrieval` with the four
   KnowledgeLayer Protocol methods: `search_semantic`, `lookup_error_code`,
   `get_page_image`, `get_compiled_article`
3. `app/services/agent_service.py` — calls both tools; new semantic fallback
   branch; `tool_call`/`tool_result` events for both
4. `tests/tools/test_tools.py` + updated `tests/test_sessions.py`

Out of scope: hermes registration of the tools (→ 2.5), embeddings/FAISS over a
PDF corpus (no corpus ingested yet — spike FINDINGS known gap), vision (→ 2.3),
web search tool (already built, wired in 2.5).

## Decisions

### D1: Plain classes, injected connection, no Protocol class

`ErrorCodeLookup(conn=None)` / `KnowledgeRetrieval(conn=None)` — inside the
per-turn transaction `agent_service` passes its open connection; standalone use
(2.5 hermes registration, scripts) opens one per call via `app.db`. The
`KnowledgeLayer` Protocol stays documentation (Techstack) — one implementation,
no runtime Protocol class.

### D2: Normalization lives in `ErrorCodeLookup.lookup`; full row returned

`lookup(controller_family, code)` expands the given code to normalized variants
and matches `code = ANY(variants)`:

- case/whitespace/hyphen cleanup: `al-309`, `AL309`, `al 309` → `AL 309`
- F-code compaction: `F 07011`, `f07011` → `F07011`
- bare digits keep both readings: `309` → `309`, `AL 309` (seeds contain both
  bare-digit codes like `10720` and AL-prefixed ones)

Returns the full `error_codes` row + `confidence: 1.0`. **Roadmap correction:**
Roadmap 2.2 says the tool returns `manual_section_id` — the column (Feature 1.1
DDL) is `manual_reference`; "meaning" = `message_de`/`message_en`. The tool
returns the DDL fields.

`controller_family=None` searches all families. The stub passes `None`:
family-name variants (`SINUMERIK_840D` vs seeded `SINUMERIK_840D_sl`) would
false-negative on a strict filter; family-string normalization is not this
feature. Filter is exact-match when provided.

### D3: `search_semantic` = Postgres full-text search, no new dependency

Corpus today is 20 structured rows — embeddings buy nothing (spike A: TF-IDF was
enough for pre-filtering; the LLM refines, Feature 2.5). Native Postgres FTS:

- tsvector: `message_de` (german config, weight A) + `message_en` (english, A)
  + `probable_causes`/`related_components` (english, B) +
  `recommended_actions` (english, C)
- query: word tokens OR-joined, run in **both** german and english config
  (bilingual rows, unknown query language); rank = sum of `ts_rank`
- computed on the fly, no index, no migration — 20 rows

Revisit (embeddings/FAISS or pgvector) when the PDF manual corpus lands.

### D4: `get_page_image` raises, `get_compiled_article` returns None

No document corpus is ingested (Feature 0.0 known gap) → `get_page_image`
raises `FileNotFoundError` with that message. Spike B (LLM wiki) lost the
shootout and no wiki pipeline exists → `get_compiled_article` returns `None`.
Protocol-complete, honestly empty — no fake data paths.

### D5: Stub gains the hybrid slow path

- code found + exact hit → fast path unchanged (now via `ErrorCodeLookup`)
- code found, no exact hit → `search_semantic` over the turn text; the
  unknown-code photo question stays the zero-hit fallback
- no code at all → `search_semantic` over the turn text (previously: photo
  question immediately); zero hits → photo question unchanged
- semantic hits become **candidate-alarm hypotheses** (up to 4, description
  `"{code}: {message_de}"`, existing fabricated confidence ladder) + the top
  hit's discriminating question — mirrors the hybrid winner's "narrowed
  candidates" shape that the 2.5 agent will reason over
- the stub drops hits below a minimal `ts_rank` score (0.1) — a stand-in for
  the LLM judging candidate relevance (real hits score ~1.0, noise ~0.04 on the
  seed corpus); the tool itself stays an unfiltered ranked list, judgment
  belongs to the caller

### D6: Tool names on the wire

`tool: "error_code_lookup"` (unchanged from 1.3) and
`tool: "knowledge_retrieval"` — the registered tool name the hermes agent calls
(Roadmap Feature 0.2: `knowledge_retrieval(query)`).

---

## Acceptance (Roadmap)

Agent can call both tools and incorporate `tool_result` events into the event
stream — verified live: turn with `AL 309` → `error_code_lookup`
`tool_call`/`tool_result` + hypotheses; turn without a code → `knowledge_retrieval`
`tool_call`/`tool_result` + candidate hypotheses; both streamed as typed SSE.

---

*Feature 2.2 · Stand: 18. Juli 2026*
