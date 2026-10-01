"""Mention propagation for person names.

NER models reliably find "Arben Krasniqi" but often miss the later, shorter
mentions ("Mr Krasniqi", "Arben"): there is no local context saying it is a
person. Leaving those in clear defeats the pseudonymisation, because the
provider can trivially re-link them. Once a full name is detected, every
exact-case, word-bounded occurrence of its parts is masked too, in the same
text and, at the gateway level, across all messages of the request.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .detectors import Span

_PARTICLES = {"de", "da", "di", "del", "della", "von", "van", "der", "le", "la", "du", "des", "dos"}


def name_parts(spans: Iterable[Span]) -> set[str]:
    parts: set[str] = set()
    for s in spans:
        if s.entity_type != "PERSON":
            continue
        tokens = re.findall(r"[\w'-]+", s.text)
        if len(tokens) < 2:
            continue
        for tok in tokens:
            if len(tok) >= 3 and tok.lower() not in _PARTICLES and tok[0].isupper():
                parts.add(tok)
    return parts


def propagate(text: str, spans: list[Span], parts: set[str] | None = None) -> list[Span]:
    """Return extra PERSON spans for name parts not already covered."""
    parts = name_parts(spans) if parts is None else parts
    if not parts:
        return []
    covered = [(s.start, s.end) for s in spans]
    extra: list[Span] = []
    for part in sorted(parts, key=len, reverse=True):
        for m in re.finditer(rf"(?<![\w-]){re.escape(part)}(?![\w-])", text):
            if any(m.start() < b and a < m.end() for a, b in covered):
                continue
            extra.append(Span(m.start(), m.end(), "PERSON", m.group(0), 0.5, "propagation"))
            covered.append((m.start(), m.end()))
    return extra
