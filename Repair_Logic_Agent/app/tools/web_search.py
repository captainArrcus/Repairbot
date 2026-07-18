"""Feature 2.5 — WebSearchTool (agent fallback for unknown codes/symptoms/parts).

Thin ddgs wrapper (keyless DuckDuckGo) instead of the unified_search.py engine
zoo — the agent needs one function (spec 2.5 D9). Tavily is the upgrade path
when result quality demands it (key already in .env).
"""

from ddgs import DDGS

MAX_RESULTS = 5


def search(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """Returns [{title, href, body}] — empty list on zero hits; network errors
    propagate to the RPC dispatcher, which reports a failure tool_result."""
    with DDGS() as ddgs:
        return [
            {"title": r.get("title", ""), "href": r.get("href", ""), "body": r.get("body", "")}
            for r in ddgs.text(query, max_results=max_results)
        ]
