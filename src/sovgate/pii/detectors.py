"""Entity detectors.

Every detector returns a list of `Span` objects. Detectors are deliberately
small and composable: the regex detectors below cover structured Swiss and
European identifiers with checksum validation (to keep false positives low),
and model-based detectors in `ner.py` handle free-text entities such as
person or organisation names.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    text: str
    score: float = 1.0
    source: str = "regex"

    def overlaps(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end


class Detector(Protocol):
    name: str

    def detect(self, text: str) -> list[Span]: ...


# ---------------------------------------------------------------- validators


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def ahv_is_valid(value: str) -> bool:
    """Swiss social security number (AHV/AVS), EAN-13 check digit."""
    d = _digits(value)
    if len(d) != 13 or not d.startswith("756"):
        return False
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d[:12]))
    return (10 - total % 10) % 10 == int(d[12])


def iban_is_valid(value: str) -> bool:
    """ISO 13616 mod-97 check."""
    s = re.sub(r"\s", "", value).upper()
    if len(s) < 15 or len(s) > 34:
        return False
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


def luhn_is_valid(value: str) -> bool:
    d = _digits(value)
    if not 13 <= len(d) <= 19:
        return False
    total = 0
    for i, c in enumerate(reversed(d)):
        n = int(c)
        if i % 2:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# ------------------------------------------------------------ regex detector


@dataclass(frozen=True)
class Pattern:
    entity_type: str
    regex: re.Pattern[str]
    validator: object = None  # Callable[[str], bool] | None


DEFAULT_PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        "AHV_NUMBER",
        re.compile(r"(?<!\d)756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}(?!\d)"),
        ahv_is_valid,
    ),
    Pattern(
        "IBAN",
        re.compile(r"\b(?:CH|LI)\d{2}(?:\s?[0-9A-Z]{4}){4}\s?[0-9A-Z]\b"),
        iban_is_valid,
    ),
    Pattern(
        "CREDIT_CARD",
        re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
        luhn_is_valid,
    ),
    Pattern(
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    Pattern(
        "PHONE_CH",
        re.compile(
            r"(?<![\d+])(?:\+41|0041|0)\s?(?:\(0\)\s?)?[1-9]\d[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}(?!\d)"
        ),
    ),
)


class RegexDetector:
    name = "regex"

    def __init__(self, patterns: Iterable[Pattern] = DEFAULT_PATTERNS) -> None:
        self.patterns = tuple(patterns)

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for p in self.patterns:
            for m in p.regex.finditer(text):
                value = m.group(0)
                if p.validator is not None and not p.validator(value):  # type: ignore[operator]
                    continue
                spans.append(Span(m.start(), m.end(), p.entity_type, value))
        return spans


class DictionaryDetector:
    """Exact-match detector for known sensitive terms (client names, project
    code names...). Configured from the policy file."""

    name = "dictionary"

    def __init__(self, terms: dict[str, list[str]] | None = None) -> None:
        self._compiled: list[tuple[str, re.Pattern[str]]] = []
        for entity_type, values in (terms or {}).items():
            for v in sorted(values, key=len, reverse=True):
                self._compiled.append(
                    (entity_type, re.compile(rf"(?<!\w){re.escape(v)}(?!\w)", re.IGNORECASE))
                )

    def detect(self, text: str) -> list[Span]:
        return [
            Span(m.start(), m.end(), et, m.group(0), source="dictionary")
            for et, rx in self._compiled
            for m in rx.finditer(text)
        ]


def resolve_overlaps(spans: Iterable[Span]) -> list[Span]:
    """Keep the longest span when spans overlap (ties: highest score)."""
    ordered = sorted(spans, key=lambda s: (-(s.end - s.start), -s.score, s.start))
    kept: list[Span] = []
    for s in ordered:
        if not any(s.overlaps(k) for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s.start)
