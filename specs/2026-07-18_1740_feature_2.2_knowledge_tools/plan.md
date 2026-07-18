# Feature 2.2 — Plan

1. `app/tools/__init__.py` + `app/tools/error_code_lookup.py`
   - `ErrorCodeLookup(conn=None)`: `lookup(controller_family, code) -> dict | None`
     (normalization variants → `code = ANY`, full row + confidence 1.0),
     `extract_codes(text)` staticmethod (regex moved from agent_service)
2. `app/tools/knowledge_layer.py`
   - `KnowledgeRetrieval(conn=None)`: `search_semantic(query, top_k=5)` (Postgres
     FTS, german+english), `lookup_error_code(code, controller_family)` (delegates),
     `get_page_image` (raises — no corpus), `get_compiled_article` (None — no wiki)
3. `app/services/agent_service.py`
   - delete `_CODE_RE`, `_extract_candidates`, `_lookup`; call the tools;
     add semantic-fallback branch per requirements D5
4. Tests
   - `tests/tools/test_tools.py`: normalization matrix, exact lookup,
     family filter, semantic hit ("Spindel erreicht Drehzahl nicht" → AL 500/510),
     semantic miss, protocol stubs
   - `tests/test_sessions.py`: no-code flow now shows `knowledge_retrieval`
     tool events; gibberish still ends in the photo question
5. Verify: `uv run pytest`, `uv run ruff check`, live uvicorn + curl both paths
6. FINDINGS.md; mark 2.2 DONE in Roadmap (+ manual_section_id correction);
   Techstack stays accurate (tool table already lists both tools)
