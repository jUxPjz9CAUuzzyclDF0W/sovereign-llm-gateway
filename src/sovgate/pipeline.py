"""Request/response processing, independent of the web framework.

`Gateway.prepare()` turns an incoming OpenAI-style request into the request
that is allowed to leave, and `Gateway.restore()` maps the provider's answer
back. Keeping this out of the FastAPI layer makes every security property
unit-testable and lets the evaluation harness drive the exact production path.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .config import Action, FailMode, Policy, PseudonymScope
from .guards import InjectionVerdict, scan
from .guards.spotlight import Boundary, tag_pattern, untrusted_segments, wrap_segments
from .pii import Pseudonymizer, Span, resolve_overlaps
from .pii.propagation import name_parts, propagate
from .router import RoutingDecision, decide

PLACEHOLDER_NOTICE = (
    "Some values in this conversation were replaced by placeholders such as "
    "<PERSON_3f9a1c>. Treat each placeholder as an opaque name and reproduce it "
    "verbatim, including the angle brackets, whenever you refer to it."
)

TOOL_KEYS = ("tools", "tool_choice", "functions", "function_call", "parallel_tool_calls")


class DetectionFailure(RuntimeError):
    """A detector crashed and the policy is fail-closed."""


@dataclass
class TextField:
    container: dict[str, Any]
    key: str
    role: str
    kind: str  # "content" | "tool_args"

    @property
    def text(self) -> str:
        return self.container[self.key]

    @text.setter
    def text(self, value: str) -> None:
        self.container[self.key] = value


def iter_fields(messages: list[dict[str, Any]]) -> Iterator[TextField]:
    """Every text field of a conversation, including tool-call arguments."""
    for msg in messages:
        role = str(msg.get("role", ""))
        content = msg.get("content")
        if isinstance(content, str):
            yield TextField(msg, "content", role, "content")
        elif isinstance(content, list):
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "text"
                    and isinstance(part.get("text"), str)
                ):
                    yield TextField(part, "text", role, "content")
        for call in msg.get("tool_calls") or []:
            fn = call.get("function") if isinstance(call, dict) else None
            if isinstance(fn, dict) and isinstance(fn.get("arguments"), str):
                yield TextField(fn, "arguments", role, "tool_args")


@dataclass
class Prepared:
    decision: RoutingDecision
    verdict: InjectionVerdict
    spans: list[Span]
    outbound: dict[str, Any]
    vault_key: str
    scan_scope: str
    spotlighted: int = 0
    detection_failed: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def entity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.spans:
            counts[s.entity_type] = counts.get(s.entity_type, 0) + 1
        return counts


class Gateway:
    def __init__(self, policy: Policy, pseudonymizer: Pseudonymizer) -> None:
        self.policy = policy
        self.pseudo = pseudonymizer
        self._tags = tag_pattern(policy.injection.untrusted_tags)

    # ----------------------------------------------------------------- helpers

    def _scope_key(self, tenant: str, vault_key: str) -> str:
        return {
            PseudonymScope.GLOBAL: "",
            PseudonymScope.TENANT: f"tenant:{tenant}",
            PseudonymScope.SESSION: f"session:{vault_key}",
        }[self.policy.pseudonym_scope]

    def _untrusted_text(self, fields: list[TextField]) -> tuple[list[str], str]:
        roles = set(self.policy.injection.untrusted_roles)
        texts: list[str] = []
        for f in fields:
            if f.role in roles:
                texts.append(f.text)
            elif f.role != "system":
                texts.extend(untrusted_segments(f.text, self._tags))
        if texts:
            return texts, "untrusted"
        # nothing explicitly marked: fall back to everything the user side sent
        return [f.text for f in fields if f.role != "system"], "all"

    # ----------------------------------------------------------------- forward

    def prepare(self, body: dict[str, Any], tenant: str, session: str) -> Prepared:
        messages = copy.deepcopy(body.get("messages") or [])
        fields = list(iter_fields(messages))

        detection_failed = False
        try:
            field_spans = [
                []
                if f.role == "system" and not self.policy.pseudonymise_system
                else self.pseudo.detect(f.text, propagate_names=False)
                for f in fields
            ]
            # a name found in one message is masked in every message of the request
            parts = name_parts(s for group in field_spans for s in group)
            field_spans = [
                group
                if f.role == "system" and not self.policy.pseudonymise_system
                else resolve_overlaps(group + propagate(f.text, group, parts))
                for f, group in zip(fields, field_spans, strict=True)
            ]
        except Exception as exc:  # any detector crash
            if self.policy.fail_mode == FailMode.CLOSED:
                raise DetectionFailure(type(exc).__name__) from exc
            field_spans = [[] for _ in fields]
            detection_failed = True
        spans = [s for group in field_spans for s in group]

        untrusted, scan_scope = self._untrusted_text(fields)
        verdict = (
            scan("\n".join(untrusted)) if self.policy.injection.enabled else InjectionVerdict(False, 0.0)
        )
        decision = decide(spans, verdict, self.policy)
        if detection_failed:
            decision.reasons.append("detector failure: fail-open, forwarded without protection")

        vault_key = f"{tenant}:{session}"
        system_notes: list[str] = []

        if decision.action == Action.PSEUDONYMISE:
            scope_key = self._scope_key(tenant, vault_key)
            for f, f_spans in zip(fields, field_spans, strict=True):
                if f_spans:
                    f.text = self.pseudo.pseudonymise(f.text, vault_key, scope_key, f_spans).text
            if spans:
                system_notes.append(PLACEHOLDER_NOTICE)

        spotlighted = 0
        if self.policy.injection.spotlight and decision.action != Action.BLOCK:
            boundary = Boundary.new()
            roles = set(self.policy.injection.untrusted_roles)
            for f in fields:
                if f.kind != "content":
                    continue
                if f.role in roles:
                    f.text = boundary.wrap(f.text)
                    spotlighted += 1
                elif f.role != "system":
                    f.text, n = wrap_segments(f.text, self._tags, boundary)
                    spotlighted += n
            if spotlighted:
                system_notes.append(boundary.instruction())

        outbound = {k: v for k, v in body.items() if not (decision.strip_tools and k in TOOL_KEYS)}
        outbound["messages"] = _with_system_notes(messages, system_notes)

        return Prepared(
            decision=decision,
            verdict=verdict,
            spans=spans,
            outbound=outbound,
            vault_key=vault_key,
            scan_scope=scan_scope,
            spotlighted=spotlighted,
            detection_failed=detection_failed,
        )

    # ----------------------------------------------------------------- reverse

    def restore(self, payload: dict[str, Any], prepared: Prepared) -> dict[str, Any]:
        if prepared.decision.action != Action.PSEUDONYMISE:
            return payload
        key = prepared.vault_key
        for choice in payload.get("choices") or []:
            msg = choice.get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                msg["content"] = self.pseudo.reidentify(content, key)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        part["text"] = self.pseudo.reidentify(part["text"], key)
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                if isinstance(fn.get("arguments"), str):
                    fn["arguments"] = self._reidentify_json(fn["arguments"], key)
        return payload

    def _reidentify_json(self, raw: str, key: str) -> str:
        """Re-identify inside JSON tool arguments without breaking the JSON."""
        try:
            obj = json.loads(raw)
        except ValueError:
            return self.pseudo.reidentify(raw, key)

        def walk(node: Any) -> Any:
            if isinstance(node, str):
                return self.pseudo.reidentify(node, key)
            if isinstance(node, list):
                return [walk(n) for n in node]
            if isinstance(node, dict):
                return {k: walk(v) for k, v in node.items()}
            return node

        return json.dumps(walk(obj), ensure_ascii=False)


def _with_system_notes(messages: list[dict[str, Any]], notes: list[str]) -> list[dict[str, Any]]:
    """Prepend gateway notes to the first system message (some local model
    templates only honour a single system message)."""
    if not notes:
        return messages
    text = "\n\n".join(notes)
    if messages and messages[0].get("role") == "system" and isinstance(messages[0].get("content"), str):
        first = dict(messages[0])
        first["content"] = f"{text}\n\n{first['content']}"
        return [first, *messages[1:]]
    return [{"role": "system", "content": text}, *messages]
