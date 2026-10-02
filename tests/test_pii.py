import random

import pytest

from evals.synthetic import make_ahv, make_card, make_iban_ch
from sovgate.pii import DictionaryDetector, Pseudonymizer, RegexDetector
from sovgate.pii.detectors import ahv_is_valid, iban_is_valid, luhn_is_valid

RNG = random.Random(1)
SECRET = b"test-secret-0123456789"


@pytest.fixture
def pseudo():
    return Pseudonymizer([RegexDetector(), DictionaryDetector({"CLIENT": ["Muster Holding AG"]})], SECRET)


def test_validators_accept_generated_values():
    for _ in range(50):
        assert ahv_is_valid(make_ahv(RNG))
        assert iban_is_valid(make_iban_ch(RNG))
        assert luhn_is_valid(make_card(RNG))


def test_validators_reject_corrupted_values():
    ahv = make_ahv(RNG)
    bad = ahv[:-1] + str((int(ahv[-1]) + 1) % 10)
    assert not ahv_is_valid(bad)
    assert not iban_is_valid("CH00 0000 0000 0000 0000 0")


@pytest.mark.parametrize(
    "text,etype",
    [
        ("Write to anna.meier@example.ch today", "EMAIL"),
        ("Rufen Sie +41 44 123 45 67 an", "PHONE_CH"),
        ("Appelez le 079 123 45 67", "PHONE_CH"),
    ],
)
def test_regex_detects(text, etype):
    assert [s.entity_type for s in RegexDetector().detect(text)] == [etype]


def test_structured_ids_detected():
    ahv, iban = make_ahv(RNG), make_iban_ch(RNG)
    types = {s.entity_type for s in RegexDetector().detect(f"AHV {ahv}, IBAN {iban}")}
    assert types == {"AHV_NUMBER", "IBAN"}


def test_checksum_failures_are_not_flagged():
    ahv = make_ahv(RNG)
    bad_ahv = ahv[:-1] + str((int(ahv[-1]) + 1) % 10)
    card = make_card(RNG)
    bad_card = card[:-1] + str((int(card[-1]) + 1) % 10)
    assert RegexDetector().detect(f"Order {bad_ahv} shipped, ref {bad_card}") == []


def test_consistent_tokens_across_texts(pseudo):
    a = pseudo.pseudonymise("Mail anna@example.ch now", "s1").text
    b = pseudo.pseudonymise("Again: ANNA@example.ch", "s1").text
    token_a = a.split()[1]
    assert token_a.startswith("<EMAIL_") and token_a in b


def test_tokens_depend_on_secret():
    p1 = Pseudonymizer([RegexDetector()], b"secret-one-0123456789")
    p2 = Pseudonymizer([RegexDetector()], b"secret-two-0123456789")
    assert p1.token_for("EMAIL", "a@b.ch") != p2.token_for("EMAIL", "a@b.ch")


def test_roundtrip(pseudo):
    text = f"Muster Holding AG pays to {make_iban_ch(RNG)}, contact bob@example.ch"
    out = pseudo.pseudonymise(text, "s2")
    assert "Muster Holding AG" not in out.text and "bob@example.ch" not in out.text
    assert out.entity_counts == {"CLIENT": 1, "IBAN": 1, "EMAIL": 1}
    assert pseudo.reidentify(out.text, "s2") == text


def test_reidentify_tolerates_llm_mangling(pseudo):
    out = pseudo.pseudonymise("Contact bob@example.ch", "s3").text
    token = out.split()[-1]  # <EMAIL_abcdef>
    digest = token[len("<EMAIL_") : -1]
    mangled = f"I emailed email_{digest.upper()} and EMAIL {digest}."
    assert pseudo.reidentify(mangled, "s3") == "I emailed bob@example.ch and bob@example.ch."


def test_sessions_are_isolated(pseudo):
    out = pseudo.pseudonymise("Contact bob@example.ch", "alice-session").text
    assert pseudo.reidentify(out, "other-session") == out


def test_short_secret_rejected():
    with pytest.raises(ValueError):
        Pseudonymizer([RegexDetector()], b"short")


def test_reidentify_bare_digest(pseudo):
    out = pseudo.pseudonymise("Contact bob@example.ch", "s4").text
    digest = out.split()[-1][len("<EMAIL_") : -1]
    assert pseudo.reidentify(f"Answer: {digest}.", "s4") == "Answer: bob@example.ch."
    assert pseudo.reidentify(f"x{digest}y", "s4") == f"x{digest}y"  # not inside other words
