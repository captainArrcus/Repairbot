"""Feature 2.2 — ErrorCodeLookupTool.

Exact structured lookup in the error_codes table — the fast path of the hybrid
knowledge winner. Codes are stored as printed in the manual ("AL 309",
"F07011", "10720"); query-time normalization lives HERE (Techstack), so callers
pass whatever the technician typed.

Registered as a hermes tool in Feature 2.5; until then the Wizard-of-Oz
agent_service calls it directly inside its per-turn transaction.
"""

import re

from psycopg.rows import dict_row

from app import db

# matches the seeded formats: "AL 309", "AL-309", "AL309", "F07011", bare "10720"/"309"
CODE_RE = re.compile(r"\b(?:AL[\s-]?\d{3,6}|F\s?\d{4,6}|\d{3,6})\b", re.IGNORECASE)

_LOOKUP_SQL = """
    SELECT controller_family, code, category, severity, message_de, message_en,
           probable_causes, recommended_actions, related_components,
           discriminating_questions, manual_reference, spare_part_refs,
           software_version, source
    FROM error_codes
    WHERE code = ANY(%s) AND (%s::text IS NULL OR controller_family = %s)
    LIMIT 1
"""


def _variants(code: str) -> list[str]:
    """Normalized candidates for a code as the technician typed it."""
    cleaned = re.sub(r"[\s\-_]+", " ", code.strip())
    if not cleaned:
        return []
    upper = cleaned.upper()
    out = [cleaned, upper]
    if m := re.fullmatch(r"AL\s?(\d+)", upper):
        out.append(f"AL {m.group(1)}")
    if m := re.fullmatch(r"F\s?(\d+)", upper):
        out.append(f"F{m.group(1)}")
    if upper.isdigit():
        out.append(f"AL {upper}")  # bare number may be a printed AL code
    return list(dict.fromkeys(out))


class ErrorCodeLookup:
    def __init__(self, conn=None):
        self._conn = conn

    @staticmethod
    def extract_codes(text: str) -> list[str]:
        return list(dict.fromkeys(CODE_RE.findall(text or "")))

    def lookup(self, controller_family: str | None, code: str) -> dict | None:
        """Exact match after normalization; confidence 1.0 by definition.

        controller_family=None searches all families (family-string
        normalization like SINUMERIK_840D vs _sl is out of scope, spec D2).
        """
        variants = _variants(code)
        if not variants:
            return None
        params = (variants, controller_family, controller_family)
        if self._conn is not None:
            row = self._conn.cursor(row_factory=dict_row).execute(_LOOKUP_SQL, params).fetchone()
        else:
            with db.connect() as conn:
                row = conn.cursor(row_factory=dict_row).execute(_LOOKUP_SQL, params).fetchone()
        if row is None:
            return None
        return {**row, "confidence": 1.0}
