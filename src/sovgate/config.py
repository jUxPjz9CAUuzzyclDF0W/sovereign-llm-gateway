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


class InjectionPolicy(BaseModel):
    enabled: bool = True
    on_detect: Action = Action.LOCAL


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
