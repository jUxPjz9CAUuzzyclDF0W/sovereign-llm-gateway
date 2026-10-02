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
from .propagation import propagate
from .vault import InMemoryVault

TOKEN_RE = re.compile(r"<([A-Z_]+)_([0-9a-f]{4,12})>")


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
        if not 4 <= token_length <= 12:
            raise ValueError("token_length must be between 4 and 12")
        self.detectors = detectors
        self._secret = secret
        self.vault = vault or InMemoryVault()
        self.token_length = token_length
        self._scope_keys: dict[str, bytes] = {}

    # ------------------------------------------------------------- forward

    def detect(self, text: str, propagate_names: bool = True) -> list[Span]:
        spans: list[Span] = []
        for d in self.detectors:
            spans.extend(d.detect(text))
        spans = resolve_overlaps(spans)
        if propagate_names:
            spans = resolve_overlaps(spans + propagate(text, spans))
        return spans

    def _key(self, scope_key: str) -> bytes:
        """Derive one HMAC key per pseudonym scope (tenant, session...)."""
        key = self._scope_keys.get(scope_key)
        if key is None:
            key = hmac.new(self._secret, f"scope:{scope_key}".encode(), hashlib.sha256).digest()
            if len(self._scope_keys) > 10_000:  # bounded cache (session scope creates many keys)
                self._scope_keys.clear()
            self._scope_keys[scope_key] = key
        return key

    def token_for(self, entity_type: str, value: str, scope_key: str = "", length: int | None = None) -> str:
        digest = hmac.new(
            self._key(scope_key), f"{entity_type}:{_normalise(entity_type, value)}".encode(), hashlib.sha256
        ).hexdigest()
        return f"<{entity_type}_{digest[: length or self.token_length]}>"

    def pseudonymise(
        self,
        text: str,
        session_id: str,
        scope_key: str = "",
        spans: list[Span] | None = None,
    ) -> PseudonymisationResult:
        """Replace detected entities by tokens.

        `spans` can be passed when detection already ran (avoids running slow
        NER models twice on the same text).
        """
        spans = self.detect(text) if spans is None else spans
        out: list[str] = []
        cursor = 0
        for s in spans:
            token = self._unique_token(s, session_id, scope_key)
            out.append(text[cursor : s.start])
            out.append(token)
            cursor = s.end
        out.append(text[cursor:])
        return PseudonymisationResult("".join(out), spans)

    def _unique_token(self, span: Span, session_id: str, scope_key: str) -> str:
        """Lengthen the token on the (rare) collision with a different value."""
        norm = _normalise(span.entity_type, span.text)
        for length in range(self.token_length, 13, 2):
            token = self.token_for(span.entity_type, span.text, scope_key, length)
            existing = self.vault.get(session_id, token)
            if existing is None or _normalise(span.entity_type, existing) == norm:
                self.vault.put(session_id, token, span.text)
                return token
        raise RuntimeError("unresolvable pseudonym collision")

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
        # 3. bare digest: small models sometimes answer with the hex part only
        #    ("7d8241"). Six random hex chars are specific enough to map back.
        for token, original in mapping.items():
            m = TOKEN_RE.fullmatch(token)
            if m and len(m.group(2)) >= 6:
                bare = re.compile(rf"(?<![0-9A-Za-z]){m.group(2)}(?![0-9A-Za-z])", re.IGNORECASE)
                text = bare.sub(lambda _m, o=original: o, text)
        return text
