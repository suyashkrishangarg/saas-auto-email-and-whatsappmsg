"""Simple GSTIN/phone helpers.

NO pattern matching / regex anywhere. Length + uppercase + alnum checks only,
per product requirement: the LLM owns authoritative GSTIN parsing.
"""
from __future__ import annotations

from typing import Optional


def normalize_gstin(value: Optional[str]) -> Optional[str]:
    """Uppercase, trim, return only if it is exactly 15 alphanumeric chars."""
    if value is None:
        return None
    v = str(value).strip().upper().strip(".")
    if len(v) == 15 and v.isalnum():
        return v
    return None


def normalize_phone(value: Optional[str]) -> Optional[str]:
    """10-digit Indian number with optional +91 / 91 prefix -> '+91XXXXXXXXXX'."""
    if value is None:
        return None
    v = str(value).strip().replace(" ", "").replace("-", "").replace(".", "")
    if not v:
        return None
    if v.startswith("+91"):
        v = v[3:]
    elif v.startswith("0"):
        v = v[1:]
    if len(v) == 12 and v.startswith("91"):
        v = v[2:]
    if not v.isdigit() or len(v) != 10:
        return None
    return "+91" + v


def is_valid_gstin(value: Optional[str]) -> bool:
    return normalize_gstin(value) is not None


def is_valid_phone(value: Optional[str]) -> bool:
    return normalize_phone(value) is not None
