"""Sensitivity-based routing decision.

The decision is a pure function of (detected entities, injection verdict,
policy), which makes it trivially unit-testable and auditable.

Routing answers one question only: *where may this data be processed?*
Prompt injection is handled separately (spotlighting, tool stripping, block),
because sending a poisoned document to a different model does not neutralise it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Action, InjectionAction, Policy, Sensitivity
from .guards import InjectionVerdict
from .pii import Span


@dataclass
class RoutingDecision:
    action: Action
    upstream: str | None
    sensitivity: Sensitivity
    reasons: list[str] = field(default_factory=list)
    strip_tools: bool = False


_UPSTREAM = {
    Action.PASSTHROUGH: "external",
    Action.PSEUDONYMISE: "external",
    Action.LOCAL: "local",
    Action.BLOCK: None,
}


def decide(spans: list[Span], verdict: InjectionVerdict, policy: Policy) -> RoutingDecision:
    sensitivity = Sensitivity.PUBLIC
    reasons: list[str] = []
    for s in spans:
        level = policy.sensitivity_of(s.entity_type)
        if level.rank > sensitivity.rank:
            sensitivity = level
    if spans:
        reasons.append(f"max entity sensitivity: {sensitivity.value}")

    action = policy.actions[sensitivity]
    strip_tools = False

    if verdict.flagged and policy.injection.enabled:
        reasons.append(f"prompt injection suspected: {','.join(verdict.rules)}")
        if policy.injection.on_detect == InjectionAction.BLOCK:
            action = Action.BLOCK
        elif policy.injection.on_detect == InjectionAction.STRIP_TOOLS:
            strip_tools = True

    return RoutingDecision(action, _UPSTREAM[action], sensitivity, reasons, strip_tools)
