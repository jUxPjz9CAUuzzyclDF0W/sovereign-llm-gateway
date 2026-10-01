"""Consistent, reversible pseudonymisation.

* Consistent: the same value always maps to the same token (keyed HMAC), so the
  LLM can still reason about "who did what" across chunks.
* Typed: tokens carry the entity type (`<PERSON_3f9a1c>`), which preserves far
  more utility than blanket redaction.
* Reversible only through the vault: the HMAC key never leaves the gateway.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter
from dataclasses import dataclass

from .detectors import Detector, Span, resolve_overlaps
from .vault import InMemoryVault

TOKEN_RE = re.compile(r"<([A-Z_]+)_([0-9a-f]{6,12})>")


@dataclass
class PseudonymisationResult:
    text: str
    spans: list[Span]

    @property
    def entity_counts(self) -> dict[str, int]:
        return dict(Counter(s.entity_type for s in self.spans))


def _normalise(entity_type: str, value: str) -> str:
    if entity_type in {"AHV_NUMBER", "IBAN", "CREDIT_CARD", "PHONE_CH"}:
        v = re.sub(r"[\s.()-]", "", value)
        if entity_type == "PHONE_CH":
            v = re.sub(r"^(?:\+41|0041)0?", "0", v)
        return v.upper()
    return value.strip().lower()


class Pseudonymizer:
    def __init__(
        self,
        detectors: list[Detector],
        secret: bytes,
        vault: InMemoryVault | None = None,
        token_length: int = 6,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("HMAC secret must be at least 16 bytes")
        self.detectors = detectors
        self._secret = secret
        self.vault = vault or InMemoryVault()
        self.token_length = token_length

    # ------------------------------------------------------------- forward

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for d in self.detectors:
            spans.extend(d.detect(text))
        return resolve_overlaps(spans)

    def token_for(self, entity_type: str, value: str) -> str:
        digest = hmac.new(
            self._secret, f"{entity_type}:{_normalise(entity_type, value)}".encode(), hashlib.sha256
        ).hexdigest()
        return f"<{entity_type}_{digest[: self.token_length]}>"

    def pseudonymise(self, text: str, session_id: str) -> PseudonymisationResult:
        spans = self.detect(text)
        out: list[str] = []
        cursor = 0
        for s in spans:
            token = self.token_for(s.entity_type, s.text)
            self.vault.put(session_id, token, s.text)
            out.append(text[cursor : s.start])
            out.append(token)
            cursor = s.end
        out.append(text[cursor:])
        return PseudonymisationResult("".join(out), spans)

    # ------------------------------------------------------------- reverse

    def reidentify(self, text: str, session_id: str) -> str:
        mapping = self.vault.items(session_id)
        if not mapping:
            return text
        # 1. exact tokens
        text = TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)
        # 2. tolerant pass: LLMs sometimes drop the brackets or change case/separators
        for token, original in mapping.items():
            m = TOKEN_RE.fullmatch(token)
            if not m:
                continue
            etype, digest = m.groups()
            loose = re.compile(
                rf"(?:<\s*)?\b{re.escape(etype).replace('_', '[ _-]?')}[ _-]?{digest}\b(?:\s*>)?",
                re.IGNORECASE,
            )
            text = loose.sub(lambda _m, o=original: o, text)
        return text
