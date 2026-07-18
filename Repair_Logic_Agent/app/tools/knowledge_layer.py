"""Feature 2.2 — KnowledgeRetrievalTool.

The KnowledgeLayer Protocol (Techstack) made concrete. search_semantic is the
slow path of the hybrid knowledge winner: fuzzy candidate search that narrows
the field for the reasoning agent (Feature 2.5). Backed by Postgres full-text
search over the error_codes rows — the only ingested corpus today (spec D3);
embeddings arrive with the PDF manual corpus.
"""

import re

from psycopg.rows import dict_row

from app import db
from app.tools.error_code_lookup import ErrorCodeLookup

# bilingual rows (message_de German, message_en + JSONB fields English) and the
# query language is unknown -> run the OR-token query in both configs, sum ranks
_SEARCH_SQL = """
    WITH q AS (
        SELECT to_tsquery('german', %(tokens)s) AS qde,
               to_tsquery('english', %(tokens)s) AS qen
    )
    SELECT controller_family, code, category, severity, message_de, message_en,
           probable_causes, recommended_actions, related_components,
           discriminating_questions, manual_reference,
           ts_rank(tsv, qde) + ts_rank(tsv, qen) AS score
    FROM (
        SELECT *,
               setweight(to_tsvector('german', coalesce(message_de, '')), 'A')
             || setweight(to_tsvector('english', coalesce(message_en, '')), 'A')
             || setweight(to_tsvector('english', probable_causes::text || ' '
                          || related_components::text), 'B')
             || setweight(to_tsvector('english', recommended_actions::text), 'C') AS tsv
        FROM error_codes
    ) ec, q
    WHERE tsv @@ qde OR tsv @@ qen
    ORDER BY score DESC
    LIMIT %(top_k)s
"""


class KnowledgeRetrieval:
    def __init__(self, conn=None):
        self._conn = conn

    def search_semantic(self, query: str, top_k: int = 5) -> list[dict]:
        """Fuzzy search over prose fields; rows ranked by ts_rank, best first."""
        # ponytail: on-the-fly tsvector over 20 rows; index/pgvector when a real corpus lands
        tokens = " | ".join(re.findall(r"\w+", query or ""))
        if not tokens:
            return []
        params = {"tokens": tokens, "top_k": top_k}
        if self._conn is not None:
            return self._conn.cursor(row_factory=dict_row).execute(_SEARCH_SQL, params).fetchall()
        with db.connect() as conn:
            return conn.cursor(row_factory=dict_row).execute(_SEARCH_SQL, params).fetchall()

    def lookup_error_code(self, code: str, controller_family: str | None = None) -> dict | None:
        """Exact structured lookup. Error codes are data, not prose."""
        return ErrorCodeLookup(self._conn).lookup(controller_family, code)

    def get_page_image(self, doc_id: str, page: int) -> bytes:
        """Raw page image for direct VLM consumption."""
        # no document corpus ingested yet (Feature 0.0 known gap) — honest failure, no fake path
        raise FileNotFoundError(
            f"no document corpus ingested — cannot serve page {page} of {doc_id!r}"
        )

    def get_compiled_article(self, topic: str) -> str | None:
        """Compiled wiki article — Spike B lost the shootout; no wiki pipeline exists."""
        return None
