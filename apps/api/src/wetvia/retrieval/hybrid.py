"""Pure helpers shared by the pg-hybrid retriever."""

from __future__ import annotations

import re

QUERY_INSTRUCTION = "Zoek de wettelijke bepalingen die relevant zijn voor de vraag."
ARTICLE_REFERENCE_PATTERN = re.compile(r"\b\d+[.:]\d+[a-z]?\b", re.IGNORECASE)


def extract_article_references(query: str) -> tuple[str, ...]:
    """Extract complete article numbers without matching numeric substrings."""
    return tuple(
        dict.fromkeys(match.group(0).lower() for match in ARTICLE_REFERENCE_PATTERN.finditer(query))
    )


__all__ = ["ARTICLE_REFERENCE_PATTERN", "QUERY_INSTRUCTION", "extract_article_references"]
