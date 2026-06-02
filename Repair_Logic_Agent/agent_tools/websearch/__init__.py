# Search Package
"""
Search engine integration and utilities.

This package provides tools for:
- Unified search across multiple engines
- Google Custom Search API integration
- DuckDuckGo search capabilities
- Tavily search integration
"""

from .unified_search import UnifiedSearchEngine

__all__ = ["UnifiedSearchEngine"]
