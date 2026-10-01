import json
import re

from sovgate.config import Policy
from sovgate.pii import Pseudonymizer, RegexDetector, Span
from sovgate.pii.ner import _windows
from sovgate.pii.propagation import name_parts, propagate
from sovgate.pipeline import Gateway

SECRET = b"test-secret-0123456789"


class FullNameOnly:
    """Stands in for an NER model that only recognises full names."""

    name = "fake-ner"

    def __init__(self, names):
        self.names = names

    def detect(self, text):
        return [
            Span(m.start(), m.end(), "PERSON", m.group(0), 0.9, "fake")
            for n in self.names
            for m in re.finditer(re.escape(n), text)
        ]


def test_name_parts_skip_particles_and_short_tokens():
    spans = [
        Span(0, 0, "PERSON", "Anna von Allmen"),
        Span(0, 0, "PERSON", "T. Keller"),
        Span(0, 0, "ORG", "Wolf AG"),
    ]
    assert name_parts(spans) == {"Anna", "Allmen", "Keller"}


def test_propagation_masks_later_mentions():
    text = "Arben Krasniqi signed. Mr Krasniqi will call Arben's lawyer. Krasniqi Bau GmbH is his company (masked too: it identifies him)."
    spans = FullNameOnly(["Arben Krasniqi"]).detect(text)
    extra = propagate(text, spans)
    assert [e.text for e in extra] == ["Krasniqi", "Krasniqi", "Arben"]


def test_propagation_is_case_sensitive_and_word_bounded():
    text = "Rose Weber likes the rose garden at Weberstrasse."
    spans = FullNameOnly(["Rose Weber"]).detect(text)
    assert propagate(text, spans) == []


def test_pseudonymiser_uses_propagation():
    p = Pseudonymizer([RegexDetector(), FullNameOnly(["Sophie Meier"])], SECRET)
    out = p.pseudonymise("Sophie Meier approved. Meier will inform Sophie.", "s").text
    assert "Meier" not in out and "Sophie" not in out


def test_gateway_propagates_across_messages():
    policy = Policy.load("config/policy.yaml")
    gw = Gateway(policy, Pseudonymizer([RegexDetector(), FullNameOnly(["Laura Fontana"])], SECRET))
    body = {
        "messages": [
            {"role": "user", "content": "Summarise the file of Laura Fontana."},
            {"role": "tool", "content": "Fontana opened the account in 2019."},
        ]
    }
    sent = json.dumps(gw.prepare(body, "t", "s").outbound)
    assert "Fontana" not in sent


def test_windows_cover_long_text_with_offsets():
    text = " ".join(f"word{i}" for i in range(600))
    windows = _windows(text, size=300, overlap=50)
    assert windows[0][0] == 0 and len(windows) > 1
    for offset, chunk in windows:
        assert text[offset : offset + len(chunk)] == chunk
    assert windows[-1][0] + len(windows[-1][1]) == len(text)
