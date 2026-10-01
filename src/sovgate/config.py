"""Policy and runtime configuration."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Sensitivity(str, Enum):
    PUBLIC = "public"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

    @property
    def rank(self) -> int:
        return {"public": 0, "confidential": 1, "restricted": 2}[self.value]


class Action(str, Enum):
    PASSTHROUGH = "passthrough"  # send to external provider unchanged
    PSEUDONYMISE = "pseudonymise"  # pseudonymise, then send to external provider
    LOCAL = "local"  # keep inside the perimeter (self-hosted model)
    BLOCK = "block"  # refuse the request


class Upstream(BaseModel):
    base_url: str
    model: str
    api_key_env: str | None = None

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env) if self.api_key_env else None


class InjectionAction(str, Enum):
    FLAG = "flag"  # audit only
    STRIP_TOOLS = "strip_tools"  # remove tool definitions so a hijacked model cannot act
    BLOCK = "block"  # refuse the request


class InjectionPolicy(BaseModel):
    """Defence against indirect prompt injection.

    Routing a poisoned document to another model does not neutralise it, so the
    defence is layered instead: untrusted content is always *spotlighted*
    (wrapped in per-request random boundaries the model is told never to obey),
    and a positive detection removes the model's ability to act (tools) or
    blocks the request.
    """

    enabled: bool = True
    spotlight: bool = True
    on_detect: InjectionAction = InjectionAction.STRIP_TOOLS
    untrusted_roles: list[str] = Field(default_factory=lambda: ["tool"])
    untrusted_tags: list[str] = Field(
        default_factory=lambda: ["document", "context", "retrieved", "search_result"]
    )


class PseudonymScope(str, Enum):
    """Which population shares the same pseudonym for the same value.

    `global` lets the provider link a person across all customers of the
    gateway; `tenant` (default) limits linkage to one organisation; `session`
    prevents linkage across conversations at the cost of cross-session memory.
    """

    GLOBAL = "global"
    TENANT = "tenant"
    SESSION = "session"


class FailMode(str, Enum):
    CLOSED = "closed"  # detector failure -> request refused (default)
    OPEN = "open"  # detector failure -> request forwarded unprotected, audited


class NerConfig(BaseModel):
    backend: str = "none"  # none | gliner | presidio
    model: str | None = None
    threshold: float = 0.5
    languages: list[str] = Field(default_factory=lambda: ["en", "fr", "de"])


class Policy(BaseModel):
    upstreams: dict[str, Upstream]
    entities: dict[str, Sensitivity] = Field(default_factory=dict)
    actions: dict[Sensitivity, Action] = Field(
        default_factory=lambda: {
            Sensitivity.PUBLIC: Action.PASSTHROUGH,
            Sensitivity.CONFIDENTIAL: Action.PSEUDONYMISE,
            Sensitivity.RESTRICTED: Action.LOCAL,
        }
    )
    default_entity_sensitivity: Sensitivity = Sensitivity.CONFIDENTIAL
    injection: InjectionPolicy = Field(default_factory=InjectionPolicy)
    dictionary: dict[str, list[str]] = Field(default_factory=dict)
    pseudonym_scope: PseudonymScope = PseudonymScope.TENANT
    # System prompts are written by the application, not by users or documents.
    pseudonymise_system: bool = False
    fail_mode: FailMode = FailMode.CLOSED
    ner: NerConfig = Field(default_factory=NerConfig)

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        with open(path, encoding="utf-8") as fh:
            return cls.model_validate(yaml.safe_load(fh))

    def sensitivity_of(self, entity_type: str) -> Sensitivity:
        return self.entities.get(entity_type, self.default_entity_sensitivity)


class Settings(BaseModel):
    policy_path: str = Field(default_factory=lambda: os.getenv("SOVGATE_POLICY", "config/policy.yaml"))
    hmac_secret: str = Field(default_factory=lambda: os.getenv("SOVGATE_HMAC_SECRET", ""))
    audit_path: str = Field(default_factory=lambda: os.getenv("SOVGATE_AUDIT_PATH", "audit/audit.jsonl"))
    vault_ttl_seconds: int = Field(default_factory=lambda: int(os.getenv("SOVGATE_VAULT_TTL", "3600")))
