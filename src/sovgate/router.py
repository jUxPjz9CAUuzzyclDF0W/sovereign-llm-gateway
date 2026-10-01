"""Sensitivity-based routing decision.

The decision is a pure function of (detected entities, injection verdict,
policy), which makes it trivially unit-testable and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Action, Policy, Sensitivity
from .guards import InjectionVerdict
from .pii import Span


@dataclass
class RoutingDecision:
    action: Action
    upstream: str | None
    sensitivity: Sensitivity
    reasons: list[str] = field(default_factory=list)


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

    if verdict.flagged and policy.injection.enabled:
        reasons.append(f"prompt injection suspected: {','.join(verdict.rules)}")
        # an injection verdict can only make the decision stricter
        order = [Action.PASSTHROUGH, Action.PSEUDONYMISE, Action.LOCAL, Action.BLOCK]
        action = max(action, policy.injection.on_detect, key=order.index)

    upstream = {
        Action.PASSTHROUGH: "external",
        Action.PSEUDONYMISE: "external",
        Action.LOCAL: "local",
        Action.BLOCK: None,
    }[action]
    return RoutingDecision(action, upstream, sensitivity, reasons)
