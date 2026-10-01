"""Build the detector chain from the policy."""

from __future__ import annotations

from ..config import Policy
from .detectors import Detector, DictionaryDetector, RegexDetector


def build_detectors(policy: Policy) -> list[Detector]:
    detectors: list[Detector] = [RegexDetector(), DictionaryDetector(policy.dictionary)]
    backend = policy.ner.backend.lower()
    if backend == "gliner":
        from .ner import GlinerDetector

        kwargs = {"threshold": policy.ner.threshold}
        if policy.ner.model:
            kwargs["model"] = policy.ner.model
        detectors.append(GlinerDetector(**kwargs))
    elif backend == "presidio":
        from .ner import PresidioDetector

        detectors.append(PresidioDetector(tuple(policy.ner.languages), policy.ner.threshold))
    elif backend != "none":
        raise ValueError(f"unknown NER backend: {policy.ner.backend}")
    return detectors
