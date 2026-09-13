"""Source-quote normalization and matching (spec/backend.md B7).

A published fact must carry ``{document_id, page, source_text}`` where the quote
actually appears in the stored page text. This module owns that comparison and
nothing else, so the policy is auditable in one place.

Permitted normalization, exactly as B7 allows:

* line-ending and whitespace collapse,
* documented equivalent quotation marks and dashes,
* conservative Unicode normalization (NFC) plus case folding,
* Arabic/Persian digit-script mapping onto ASCII digits.

Explicitly **not** permitted, and not implemented:

* fuzzy or approximate matching of any kind -- a near miss is a miss,
* global punctuation stripping,
* treating ``1,000``, ``1.000`` and ``1000`` as equivalent (that lives in
  :mod:`app.money` and stays deliberately conservative),
* removing signs, parentheses, currency, units or Arabic letters.

A failed match quarantines the fact, and any judgment that depended on it cannot
be published as supported (B7). Matching proves correspondence to stored text --
never scan authenticity, OCR correctness or interpretation.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from app.money import normalize_digits

#: Version of this policy, stored on every fact so a future change is
#: distinguishable from this one (B7).
NORMALIZATION_VERSION: Final[str] = "v1"

#: Quotation marks and dashes treated as equivalent to their ASCII form. Listed
#: explicitly rather than derived from a Unicode category, so the set is
#: reviewable.
_EQUIVALENT_CHARACTERS: Final[dict[str, str]] = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u2032": "'",
    "\u00ab": '"',
    "\u00bb": '"',
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u2033": '"',
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    # Arabic punctuation that OCR and typists interchange with ASCII.
    "\u060c": ",",
    "\u061b": ";",
    "\u061f": "?",
    # Non-breaking and thin spaces become ordinary spaces before collapse.
    "\u00a0": " ",
    "\u202f": " ",
    "\u2009": " ",
    "\u200a": " ",
    "\u2007": " ",
}

_WHITESPACE_RUN = re.compile(r"\s+")

#: Zero-width characters OCR and copy/paste inject between glyphs. Removing them
#: cannot change which characters a human reads.
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")


def normalize_for_match(text: str) -> str:
    """Return the comparison form of ``text`` under the versioned policy (B7).

    The transformation is deliberately lossy in *layout* only: characters that a
    reader would consider the same are unified, and nothing that changes meaning
    (digits, signs, letters, currency) is removed.
    """
    normalized = unicodedata.normalize("NFC", text)
    normalized = _ZERO_WIDTH.sub("", normalized)
    normalized = "".join(_EQUIVALENT_CHARACTERS.get(char, char) for char in normalized)
    normalized = normalize_digits(normalized)
    normalized = _WHITESPACE_RUN.sub(" ", normalized)
    return normalized.strip().casefold()


def quote_matches_page(quote: str, page_text: str) -> bool:
    """Return True when ``quote`` occurs in ``page_text`` after normalization.

    Substring containment only. An empty or whitespace-only quote never matches:
    it would otherwise "match" every page and let an unsupported judgment through
    (B7).
    """
    needle = normalize_for_match(quote)
    if not needle:
        return False
    return needle in normalize_for_match(page_text)


def value_anchored_in_quote(value_text: str, quote: str) -> bool:
    """Return True when the literal value appears inside its own quote (B6).

    Stops a real-but-irrelevant quote from carrying an unrelated amount: the
    numeric substring must actually be part of the text that was cited.
    """
    needle = normalize_for_match(value_text)
    if not needle:
        return False
    return needle in normalize_for_match(quote)
