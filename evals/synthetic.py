"""Deterministic synthetic data with valid Swiss identifiers.

All values are generated: no real person, account or number is used.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


def make_ahv(rng: random.Random) -> str:
    body = "756" + "".join(str(rng.randint(0, 9)) for _ in range(9))
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(body))
    check = (10 - total % 10) % 10
    d = body + str(check)
    return f"{d[:3]}.{d[3:7]}.{d[7:11]}.{d[11:]}"


def make_iban_ch(rng: random.Random) -> str:
    bban = "".join(str(rng.randint(0, 9)) for _ in range(17))
    numeric = "".join(str(int(c, 36)) for c in bban + "CH00")
    check = 98 - int(numeric) % 97
    raw = f"CH{check:02d}{bban}"
    return " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def make_card(rng: random.Random) -> str:
    body = [4] + [rng.randint(0, 9) for _ in range(14)]
    total = 0
    for i, n in enumerate(reversed(body)):
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    digits = "".join(map(str, body)) + str((10 - total % 10) % 10)
    return " ".join(digits[i : i + 4] for i in range(0, 16, 4))


def make_phone(rng: random.Random) -> str:
    fmt = rng.choice(["+41 {a} {b} {c} {d}", "0{a} {b} {c} {d}", "+41{a}{b}{c}{d}"])
    return fmt.format(
        a=rng.choice(["44", "21", "22", "79", "76"]),
        b=rng.randint(100, 999),
        c=rng.randint(10, 99),
        d=rng.randint(10, 99),
    )


FIRST = ["Anna", "Luca", "Chloé", "Noah", "Elena", "Matteo", "Léa", "Jonas"]
LAST = ["Meier", "Rossi", "Dubois", "Keller", "Bianchi", "Favre", "Huber", "Weber"]

TEMPLATES = {
    "en": [
        "Customer {email} asked to update the payout account to {iban}.",
        "Please call back on {phone} regarding AHV number {ahv}.",
        "Card {card} was used twice; notify {email} and keep AHV {ahv} on file.",
    ],
    "fr": [
        "Le client {email} demande de verser le montant sur l'IBAN {iban}.",
        "Merci de rappeler au {phone}, numéro AVS {ahv}.",
        "La carte {card} a été bloquée, prévenir {email}.",
    ],
    "de": [
        "Kunde {email} möchte die Auszahlung auf {iban} ändern.",
        "Bitte unter {phone} zurückrufen, AHV-Nummer {ahv}.",
        "Karte {card} wurde gesperrt, bitte {email} informieren.",
    ],
}


@dataclass
class Sample:
    lang: str
    text: str
    entities: dict[str, str]  # entity_type -> value


def generate(n: int = 300, seed: int = 7) -> list[Sample]:
    rng = random.Random(seed)
    out: list[Sample] = []
    for i in range(n):
        lang = ["en", "fr", "de"][i % 3]
        tpl = rng.choice(TEMPLATES[lang])
        first, last = rng.choice(FIRST), rng.choice(LAST)
        values = {
            "email": f"{first}.{last}@example.ch".lower(),
            "iban": make_iban_ch(rng),
            "phone": make_phone(rng),
            "ahv": make_ahv(rng),
            "card": make_card(rng),
        }
        types = {
            "email": "EMAIL",
            "iban": "IBAN",
            "phone": "PHONE_CH",
            "ahv": "AHV_NUMBER",
            "card": "CREDIT_CARD",
        }
        used = {types[k]: v for k, v in values.items() if "{" + k + "}" in tpl}
        out.append(Sample(lang, tpl.format(**values), used))
    return out
