"""Feature 2.2: knowledge tools.

Normalization tests run everywhere. DB-backed tests need the dev Postgres with
the Feature 1.1 seed applied (docker compose -f infra/docker-compose.yml up -d);
skip otherwise, e.g. in CI.
"""

import psycopg
import pytest

from app import config
from app.tools.error_code_lookup import ErrorCodeLookup, _canonical_family, _variants
from app.tools.knowledge_layer import KnowledgeRetrieval


def _db_ready() -> bool:
    try:
        with psycopg.connect(config.DATABASE_URL, connect_timeout=2) as conn:
            return conn.execute("SELECT count(*) FROM error_codes").fetchone()[0] > 0
    except psycopg.Error:
        return False


needs_db = pytest.mark.skipif(not _db_ready(), reason="dev Postgres not running/migrated/seeded")


def test_normalization_variants():
    assert "AL 309" in _variants("al-309")
    assert "AL 309" in _variants("AL309")
    assert "AL 309" in _variants("al  309")
    assert "F07011" in _variants("f 07011")
    # bare number keeps both readings: printed bare code and AL-prefixed code
    assert {"309", "AL 309"} <= set(_variants("309"))
    assert _variants("   ") == []


def test_family_normalization():
    # 2.8: brand + variant strings map to the seeded canonical family
    assert _canonical_family("SINUMERIK") == "SINUMERIK_840D_sl"
    assert _canonical_family("siemens sinumerik") == "SINUMERIK_840D_sl"
    assert _canonical_family("840d-sl") == "SINUMERIK_840D_sl"
    assert _canonical_family("SINUMERIK_840D_sl") == "SINUMERIK_840D_sl"
    assert _canonical_family("HEIDENHAIN") == "HEIDENHAIN"  # unmapped passes through
    assert _canonical_family(None) is None
    assert _canonical_family("  ") is None


def test_extract_codes():
    codes = ErrorCodeLookup.extract_codes("AL 309 und F07011, außerdem Fehler 25050")
    assert codes == ["AL 309", "F07011", "25050"]
    assert ErrorCodeLookup.extract_codes("") == []
    assert ErrorCodeLookup.extract_codes(None) == []


def test_protocol_stubs_are_honestly_empty():
    tool = KnowledgeRetrieval()
    with pytest.raises(FileNotFoundError):
        tool.get_page_image("dmgmori_manual", 84)
    assert tool.get_compiled_article("AL 309") is None
    assert tool.search_semantic("") == []  # no tokens, no query


@needs_db
def test_lookup_normalizes_to_seeded_code():
    alarm = ErrorCodeLookup().lookup(None, "al-309")
    assert alarm["code"] == "AL 309"
    assert alarm["confidence"] == 1.0
    assert isinstance(alarm["probable_causes"], list) and alarm["probable_causes"]
    assert alarm["manual_reference"]


@needs_db
def test_lookup_bare_digit_codes():
    assert ErrorCodeLookup().lookup(None, "10720")["code"] == "10720"  # printed bare
    assert ErrorCodeLookup().lookup(None, "309")["code"] == "AL 309"  # AL reading


@needs_db
def test_lookup_controller_family_filter():
    tool = ErrorCodeLookup()
    assert tool.lookup("SINUMERIK_840D_sl", "AL 309") is not None
    assert tool.lookup("FANUC_30i", "AL 309") is None
    assert tool.lookup(None, "AL 999999") is None


@needs_db
def test_lookup_brand_level_family_exact_hits():
    # 2.8 acceptance: vision's brand-level string exact-hits without a family=None retry
    assert ErrorCodeLookup().lookup("SINUMERIK", "AL 309")["code"] == "AL 309"


@needs_db
def test_search_semantic_ranks_relevant_alarm_first():
    results = KnowledgeRetrieval().search_semantic("Die Spindel erreicht die Drehzahl nicht")
    assert results[0]["code"] == "AL 500"  # "Spindel: Drehzahl nicht erreicht"
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert len(KnowledgeRetrieval().search_semantic("Spindel", top_k=1)) == 1


@needs_db
def test_search_semantic_no_match_is_empty():
    assert KnowledgeRetrieval().search_semantic("Maschine macht komische Geräusche") == []


@needs_db
def test_lookup_error_code_delegates():
    assert KnowledgeRetrieval().lookup_error_code("309")["code"] == "AL 309"
