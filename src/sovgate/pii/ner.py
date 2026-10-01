"""Model-based detectors for free-text entities (names, organisations, addresses).

Two backends behind the same `Detector` interface:

* `GlinerDetector`: GLiNER, a zero-shot span-extraction model. The multilingual
  PII checkpoint handles FR/DE/IT/EN without language detection, which matters
  in Switzerland where one e-mail thread can switch languages.
* `PresidioDetector`: Microsoft Presidio with spaCy models; the de-facto
  baseline (it is what LiteLLM's PII guardrail uses).

Both are optional dependencies: `pip install .[ner]`.
"""

from __future__ import annotations

from .detectors import Span

GLINER_LABELS: dict[str, str] = {
    "person": "PERSON",
    "organization": "ORG",
    "street address": "ADDRESS",
    "date of birth": "DATE_OF_BIRTH",
}


# Pronouns and generic words that zero-shot models sometimes tag as persons.
_NOT_NAMES = {
    "i",
    "you",
    "he",
    "she",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
    "user",
    "assistant",
    "client",
    "customer",
    "je",
    "tu",
    "il",
    "elle",
    "nous",
    "vous",
    "ils",
    "elles",
    "cliente",
    "ich",
    "du",
    "er",
    "sie",
    "wir",
    "ihr",
    "kunde",
    "kundin",
}


def _windows(text: str, size: int = 900, overlap: int = 150) -> list[tuple[int, str]]:
    """Split long texts on whitespace so the model's context limit is respected."""
    if len(text) <= size:
        return [(0, text)]
    out: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut > 0 else end
        out.append((start, text[start:end]))
        if end >= len(text):
            break
        nxt = text.find(" ", end - overlap, end)
        start = nxt + 1 if nxt > start else end
    return out


class GlinerDetector:
    name = "gliner"

    def __init__(
        self,
        model: str = "urchade/gliner_multi_pii-v1",
        threshold: float = 0.5,
        labels: dict[str, str] | None = None,
    ) -> None:
        try:
            from gliner import GLiNER  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("GLiNER backend requires `pip install .[ner]`") from exc
        self._model = GLiNER.from_pretrained(model)
        self.threshold = threshold
        self.labels = labels or GLINER_LABELS

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for offset, chunk in _windows(text):
            for e in self._model.predict_entities(chunk, list(self.labels), threshold=self.threshold):
                if self.labels[e["label"]] == "PERSON" and e["text"].strip().lower() in _NOT_NAMES:
                    continue
                start, end = offset + e["start"], offset + e["end"]
                spans.append(
                    Span(start, end, self.labels[e["label"]], text[start:end], float(e["score"]), "gliner")
                )
        return spans


PRESIDIO_MAPPING: dict[str, str] = {
    "PERSON": "PERSON",
    "ORGANIZATION": "ORG",
    "LOCATION": "LOCATION",
    "NRP": "NRP",
    "DATE_TIME": "DATE",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "IBAN_CODE": "IBAN",
    "CREDIT_CARD": "CREDIT_CARD",
}

_SPACY_MODELS = {"en": "en_core_web_sm", "fr": "fr_core_news_sm", "de": "de_core_news_sm"}


class PresidioDetector:
    """Presidio analyzer. `languages` are tried in order and results merged,
    because a gateway does not know the language of a prompt in advance."""

    name = "presidio"

    def __init__(self, languages: tuple[str, ...] = ("en",), threshold: float = 0.5) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine  # type: ignore
            from presidio_analyzer.nlp_engine import NlpEngineProvider  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Presidio backend requires `pip install .[ner]`") from exc
        config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": lang, "model_name": _SPACY_MODELS[lang]} for lang in languages],
        }
        nlp = NlpEngineProvider(nlp_configuration=config).create_engine()
        self._engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=list(languages))
        self.languages = languages
        self.threshold = threshold

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for lang in self.languages:
            for r in self._engine.analyze(text, language=lang, entities=list(PRESIDIO_MAPPING)):
                if r.score >= self.threshold:
                    spans.append(
                        Span(
                            r.start,
                            r.end,
                            PRESIDIO_MAPPING[r.entity_type],
                            text[r.start : r.end],
                            float(r.score),
                            "presidio",
                        )
                    )
        return spans
