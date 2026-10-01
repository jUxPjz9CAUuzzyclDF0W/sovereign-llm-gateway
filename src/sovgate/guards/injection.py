"""Baseline prompt-injection detector for untrusted content.

Retrieved RAG chunks and tool outputs are untrusted input: a poisoned document
can carry instructions aimed at the model (indirect prompt injection). This
heuristic baseline catches the common patterns and, more importantly, defines
the interface. The roadmap replaces/augments it with a classifier
(e.g. a Prompt Guard model) and measures both against the same eval set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_RULES: tuple[tuple[str, str], ...] = (
    (
        "override",
        r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|all)\b.{0,20}\b(instructions?|rules|prompts?)\b",
    ),
    ("override_fr", r"\b(ignore[rz]?|oublie[rz]?)\b.{0,40}\b(instructions?|consignes?|r[eè]gles)\b"),
    ("override_de", r"\b(ignoriere|vergiss)\b.{0,40}\b(anweisungen|regeln|instruktionen)\b"),
    (
        "role_hijack",
        r"\b(you are now|from now on you|act as)\b.{0,40}\b(dan|developer mode|unrestricted|jailbroken)\b",
    ),
    (
        "prompt_leak",
        r"\b(reveal|print|show|repeat)\b.{0,30}\b(system prompt|hidden instructions|initial instructions)\b",
    ),
    ("exfil_markdown", r"!\[[^\]]*\]\(https?://[^)]*[?&][^)=]+=[^)]*\)"),
    ("fake_role_tag", r"(^|\n)\s*(system|assistant)\s*:\s"),
    ("tool_abuse", r"\b(call|invoke|use)\b.{0,20}\b(tool|function)\b.{0,40}\b(send|email|upload|post)\b"),
)
_COMPILED = tuple((name, re.compile(rx, re.IGNORECASE)) for name, rx in _RULES)


@dataclass
class InjectionVerdict:
    flagged: bool
    score: float
    rules: list[str] = field(default_factory=list)


def scan(text: str) -> InjectionVerdict:
    hits = [name for name, rx in _COMPILED if rx.search(text)]
    score = min(1.0, 0.5 * len(hits))
    return InjectionVerdict(flagged=bool(hits), score=score, rules=hits)
