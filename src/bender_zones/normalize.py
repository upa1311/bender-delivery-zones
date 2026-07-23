"""Conservative text normalization for the *preliminary* duplicate metric.

Only four operations are permitted, in this order:

1. Unicode NFKC normalization
2. trim (strip leading/trailing whitespace)
3. collapse internal whitespace runs to a single space
4. casefold

No transliteration, no fuzzy matching, no accent stripping, no punctuation
removal. The duplicate count produced from these keys is explicitly a
*lower-effort preliminary signal*, not a deduplicated address database.
"""

from __future__ import annotations

import unicodedata

__all__ = ["normalize_text", "address_key"]


def normalize_text(value: str) -> str:
    """Apply NFKC → trim → collapse-whitespace → casefold to *value*."""
    text = unicodedata.normalize("NFKC", value)
    text = text.strip()
    text = " ".join(text.split())
    return text.casefold()


def address_key(street: str | None, housenumber: str | None) -> tuple[str, str]:
    """Return a normalized ``(street, housenumber)`` key for duplicate counting."""
    return (normalize_text(street or ""), normalize_text(housenumber or ""))
