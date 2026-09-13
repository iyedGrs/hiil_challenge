"""Decimal money handling (spec/backend.md B3, B7).

Two very different jobs live here and must not be confused:

1. :func:`parse_claim_amount` validates a *canonical* decimal string typed by the
   preparer. It is strict: dot decimal separator, no grouping, no exponent.
2. :func:`parse_source_amount` interprets a *literal amount copied out of a
   document*. It is deliberately conservative and locale-aware: it returns
   ``None`` whenever the token's format is ambiguous, which makes the dependent
   check unassessable rather than silently guessing a value (B7).

Nothing here computes a balance from model output. All arithmetic is
:class:`~decimal.Decimal` in application code; no float ever touches a monetary
value, and currency is never converted (B7).
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Final

#: TND budget: 12 integer digits and 3 fractional digits (spec/backend.md B3).
MAX_INTEGER_DIGITS: Final[int] = 12
MAX_FRACTION_DIGITS: Final[int] = 3

#: Version of the numeric normalization policy, stored on every fact (B7).
NORMALIZATION_VERSION: Final[str] = "v1"

#: Canonical claim amount: optional digits, dot decimal separator only.
_CANONICAL_AMOUNT = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

#: Whitespace treated as digit grouping inside a source amount.
_GROUPING_SPACES: Final[str] = " \u00a0\u202f\u2009'"

#: Currency words/symbols stripped before parsing a source amount. Stripping a
#: currency label never changes the number; the currency itself is carried
#: separately and never converted (B7).
_CURRENCY_TOKENS: Final[tuple[str, ...]] = (
    "TND",
    "DT",
    "MILLIMES",
    "DINARS",
    "DINAR",
    "د.ت",
    "دينار",
    "€",
    "$",
)


class AmountFormatError(ValueError):
    """Raised when a claim amount is not a valid canonical decimal string."""


def normalize_digits(text: str) -> str:
    """Map Arabic-Indic and Eastern Arabic-Indic digits onto ASCII digits.

    Explicitly allowed by the normalization policy (B7). Only characters Unicode
    itself classifies as decimal digits are mapped, so no Arabic *letter* is
    touched.
    """
    out: list[str] = []
    for character in text:
        if character.isdigit() and not character.isascii():
            digit = unicodedata.decimal(character, None)
            out.append(str(digit) if digit is not None else character)
        else:
            out.append(character)
    return "".join(out)


def parse_claim_amount(raw: str) -> Decimal:
    """Validate and parse a preparer-supplied canonical decimal string (B3).

    Args:
        raw: Amount exactly as received in JSON. Must be a string; a JSON float
            is rejected by the schema layer before reaching here.

    Returns:
        The parsed nonnegative :class:`Decimal`.

    Raises:
        AmountFormatError: when the string is not canonical, is negative, or
            exceeds the TND digit budget.
    """
    text = raw.strip()
    if not text:
        raise AmountFormatError("An amount is required.")
    if not _CANONICAL_AMOUNT.match(text):
        raise AmountFormatError(
            "Use a plain decimal amount with a dot separator and no grouping, for example 20000.000."
        )
    integer_part, _, fraction_part = text.partition(".")
    if len(integer_part) > MAX_INTEGER_DIGITS:
        raise AmountFormatError(f"At most {MAX_INTEGER_DIGITS} digits before the decimal point.")
    if len(fraction_part) > MAX_FRACTION_DIGITS:
        raise AmountFormatError(f"At most {MAX_FRACTION_DIGITS} decimal places for TND.")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - regex already guards this
        raise AmountFormatError("The amount could not be parsed.") from exc


def format_amount(value: Decimal) -> str:
    """Render a Decimal as a canonical, non-exponential decimal string (B9)."""
    return format(value, "f")


def _strip_currency(text: str) -> str:
    """Remove currency labels/symbols from a source amount token."""
    cleaned = text
    upper = cleaned.upper()
    for token in _CURRENCY_TOKENS:
        upper = upper.replace(token.upper(), " ")
    # Rebuild from the case-insensitively cleaned string: amounts contain no
    # letters we need to preserve once the currency label is gone.
    return upper


def parse_source_amount(raw: str) -> Decimal | None:
    """Parse an amount copied from a document, or ``None`` when ambiguous (B7).

    The policy is intentionally narrow. ``1,000`` is **not** resolved: in a
    French/Tunisian document it can mean one thousand or one unit and three
    decimals, so the value stays unknown and the dependent check becomes
    unassessable rather than being decided by a guess.

    Resolved cases:

    * Both ``.`` and ``,`` present -- the rightmost is the decimal separator and
      the other is grouping (``1.234,567`` and ``1,234.567``).
    * Space/apostrophe grouping with one ``.``/``,`` -- that separator is decimal
      (``20 000,000`` is twenty thousand, three decimals).
    * One separator followed by a digit count other than 3 -- decimal separator
      (``1234,56``).
    * One separator followed by exactly 3 digits where the integer part is not a
      valid leading group of 1-3 digits -- decimal separator (``1234,567``).
    * No separator at all -- a plain integer.

    Sign handling preserves negation: a leading ``-`` or surrounding parentheses
    both yield a negative value, which stays negative (a credit/overpayment is
    never clamped to zero, B7).

    Returns:
        The parsed :class:`Decimal`, or ``None`` when the token is ambiguous,
        malformed or exceeds the TND digit budget.
    """
    text = normalize_digits(raw).strip()
    if not text:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = _strip_currency(text)
    text = text.strip()
    if text.startswith("-"):
        negative = not negative
        text = text[1:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()

    # Collapse grouping whitespace/apostrophes, remembering whether any existed:
    # its presence proves the remaining ``.``/``,`` is a decimal separator.
    had_space_grouping = any(character in _GROUPING_SPACES for character in text)
    for character in _GROUPING_SPACES:
        text = text.replace(character, "")

    if not text or not re.fullmatch(r"[0-9.,]+", text):
        return None

    dot_count = text.count(".")
    comma_count = text.count(",")

    integer_digits: str
    fraction_digits: str

    if dot_count and comma_count:
        # Rightmost separator is the decimal point; the other must be grouping.
        decimal_separator = "." if text.rfind(".") > text.rfind(",") else ","
        grouping_separator = "," if decimal_separator == "." else "."
        head, _, tail = text.rpartition(decimal_separator)
        if not _valid_grouping(head, grouping_separator):
            return None
        integer_digits = head.replace(grouping_separator, "")
        fraction_digits = tail
    elif dot_count + comma_count == 0:
        integer_digits, fraction_digits = text, ""
    elif dot_count > 1 or comma_count > 1:
        # Repeated separator can only be grouping: 1.234.567
        separator = "." if dot_count > 1 else ","
        if not _valid_grouping(text, separator):
            return None
        integer_digits, fraction_digits = text.replace(separator, ""), ""
    else:
        separator = "." if dot_count else ","
        head, _, tail = text.partition(separator)
        if not head.isdigit() or not tail.isdigit():
            return None
        if len(tail) == 3 and not had_space_grouping and 1 <= len(head) <= 3:
            # Ambiguous: "1,000" / "1.000" may be grouping or three decimals.
            return None
        integer_digits, fraction_digits = head, tail

    if not integer_digits.isdigit() or (fraction_digits and not fraction_digits.isdigit()):
        return None
    if len(integer_digits) > MAX_INTEGER_DIGITS or len(fraction_digits) > MAX_FRACTION_DIGITS:
        return None

    candidate = integer_digits + ("." + fraction_digits if fraction_digits else "")
    try:
        value = Decimal(candidate)
    except InvalidOperation:
        return None
    return -value if negative else value


def _valid_grouping(head: str, separator: str) -> bool:
    """Return True when ``head`` is digits grouped in valid 3-digit blocks."""
    if separator not in head:
        return head.isdigit()
    blocks = head.split(separator)
    if len(blocks) < 2:
        return False
    if not (1 <= len(blocks[0]) <= 3) or not blocks[0].isdigit():
        return False
    return all(len(block) == 3 and block.isdigit() for block in blocks[1:])
