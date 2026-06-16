"""Text normalization helpers."""

from __future__ import annotations

import re


def normalize(value: str) -> str:
    lowered = value.lower()
    lowered = lowered.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", lowered).strip()


def contains_term(text: str, term: str) -> bool:
    return normalize(term) in text
