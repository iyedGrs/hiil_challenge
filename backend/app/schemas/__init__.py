"""Pydantic v2 request/response schemas for the canonical contract (B9).

Request models inherit :class:`app.schemas.common.StrictModel`, which forbids
extra fields: unknown fields and unknown enum values are rejected (B9, B5).
"""
