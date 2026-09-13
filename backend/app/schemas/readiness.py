"""Readiness verdict schema (spec/progress.md change log).

Its own module so both ``schemas/cases.py`` and ``schemas/reviewer.py`` /
``schemas/submissions.py`` can import it without a circular import.
"""

from __future__ import annotations

from app.domain.enums import ReadinessStatus
from app.schemas.common import ResponseModel


class ReadinessOut(ResponseModel):
    """``{status, reasons}``: the automatic verdict, never set by a reviewer."""

    status: ReadinessStatus
    reasons: list[str]
