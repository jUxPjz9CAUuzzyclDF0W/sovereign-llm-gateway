"""Question-answering set for the utility benchmark.

    python -m evals.data.build_qa        ->  evals/data/qa.jsonl

Each item simulates the generation step of a RAG pipeline: three retrieved
documents (one relevant, two distractors that also mention people and
companies) and a question with a verifiable answer. Retrieval is held fixed on
purpose: the gateway retrieves on clear text inside the perimeter, so only the
generation step is affected by pseudonymisation.

Questions come in two kinds:
* `entity`: the answer is personal data (a name, a company, an IBAN...). A
  privacy layer must hide it from the model AND give it back to the user.
* `non_entity`: the answer is not personal data (an amount, a weekday, a
  deadline). A good privacy layer should not damage these at all.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from evals.synthetic import make_iban_ch, make_phone

from .build_dataset import _address, _dob, _org, _person

OUT = Path(__file__).parent / "qa.jsonl"

WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"],
}
CITIES = ["Zürich", "Genève", "Bern", "Basel", "Lausanne", "Lugano", "Luzern"]

# Each scenario: document template + questions. Slots: {P1:full} {ORG} {IBAN} ...
# A question's answer is a slot; `aliases` lists other acceptable slot forms.
SCENARIOS = {
    "en": {
        "kyc": (
            "KYC note. Beneficial owner: {P1:full}, born {DOB}, resident at {ADDR}. Shareholder of {ORG}. "
            "Introduced by {P2:full}. Declared assets: {AMOUNT}.",
            [
                ("Who is the beneficial owner?", "P1:full", ["P1:last"], "entity"),
                ("What is the beneficial owner's date of birth?", "DOB", [], "entity"),
                ("Which company is the beneficial owner a shareholder of?", "ORG", [], "entity"),
                ("Who introduced the client?", "P2:full", ["P2:last"], "entity"),
                ("What amount of assets was declared?", "AMOUNT", [], "non_entity"),
            ],
        ),
        "payout": (
            "E-mail. {P2:full} from {ORG} asked us to change the payout account to {IBAN}. You can reach "
            "{P2:first} on {PHONE}. The change takes effect on {DAY}.",
            [
                ("What is the new payout account?", "IBAN", [], "entity"),
                ("On which phone number can the requester be reached?", "PHONE", [], "entity"),
                ("Which company does the requester work for?", "ORG", [], "entity"),
                ("On which day does the change take effect?", "DAY", [], "non_entity"),
            ],
        ),
        "minutes": (
            "Minutes. Present: {P1:full} (chair), {P2:full}, {P3:full}. The committee approved a loan of {AMOUNT} "
            "to {ORG}. {P2:first} will brief the client by {DAY}.",
            [
                ("Who chaired the meeting?", "P1:full", ["P1:last"], "entity"),
                ("Who will brief the client?", "P2:full", ["P2:first", "P2:last"], "entity"),
                ("Which company received the loan?", "ORG", [], "entity"),
                ("How much was the approved loan?", "AMOUNT", [], "non_entity"),
                ("By which day will the client be briefed?", "DAY", [], "non_entity"),
            ],
        ),
        "policy": (
            "Policy section. Claims above {AMOUNT} are escalated to the legal team led by {P1:full}. Clients in "
            "{CITY} are handled by {P2:full}. Answers are due within {N} working days.",
            [
                ("Who leads the legal team?", "P1:full", ["P1:last"], "entity"),
                ("Who handles clients in {CITY}?", "P2:full", ["P2:last"], "entity"),
                ("Above which amount are claims escalated?", "AMOUNT", [], "non_entity"),
                ("Within how many working days are answers due?", "N", [], "non_entity"),
            ],
        ),
    },
    "fr": {
        "kyc": (
            "Note KYC. Ayant droit économique : {P1:full}, né le {DOB}, domicilié {ADDR}. Associé de {ORG}. "
            "Introduit par {P2:full}. Fortune déclarée : {AMOUNT}.",
            [
                ("Qui est l'ayant droit économique ?", "P1:full", ["P1:last"], "entity"),
                ("Quelle est la date de naissance de l'ayant droit économique ?", "DOB", [], "entity"),
                ("De quelle société l'ayant droit est-il associé ?", "ORG", [], "entity"),
                ("Qui a introduit le client ?", "P2:full", ["P2:last"], "entity"),
                ("Quel est le montant de la fortune déclarée ?", "AMOUNT", [], "non_entity"),
            ],
        ),
        "payout": (
            "E-mail. {P2:full} de {ORG} demande de verser le montant sur le compte {IBAN}. On peut joindre "
            "{P2:first} au {PHONE}. Le changement prend effet {DAY}.",
            [
                ("Quel est le nouveau compte de versement ?", "IBAN", [], "entity"),
                ("À quel numéro peut-on joindre le demandeur ?", "PHONE", [], "entity"),
                ("Pour quelle société le demandeur travaille-t-il ?", "ORG", [], "entity"),
                ("Quel jour le changement prend-il effet ?", "DAY", [], "non_entity"),
            ],
        ),
        "minutes": (
            "Procès-verbal. Présents : {P1:full} (présidence), {P2:full}, {P3:full}. Le comité approuve un crédit "
            "de {AMOUNT} à {ORG}. {P2:first} informera le client d'ici {DAY}.",
            [
                ("Qui a présidé la séance ?", "P1:full", ["P1:last"], "entity"),
                ("Qui informera le client ?", "P2:full", ["P2:first", "P2:last"], "entity"),
                ("Quelle société reçoit le crédit ?", "ORG", [], "entity"),
                ("Quel est le montant du crédit approuvé ?", "AMOUNT", [], "non_entity"),
                ("D'ici quel jour le client sera-t-il informé ?", "DAY", [], "non_entity"),
            ],
        ),
        "policy": (
            "Directive. Les réclamations supérieures à {AMOUNT} sont transmises au service juridique dirigé par "
            "{P1:full}. Les clients de {CITY} sont suivis par {P2:full}. Les réponses sont dues sous {N} jours "
            "ouvrables.",
            [
                ("Qui dirige le service juridique ?", "P1:full", ["P1:last"], "entity"),
                ("Qui suit les clients de {CITY} ?", "P2:full", ["P2:last"], "entity"),
                (
                    "Au-delà de quel montant les réclamations sont-elles transmises ?",
                    "AMOUNT",
                    [],
                    "non_entity",
                ),
                ("Sous combien de jours ouvrables les réponses sont-elles dues ?", "N", [], "non_entity"),
            ],
        ),
    },
    "de": {
        "kyc": (
            "KYC-Notiz. Wirtschaftlich berechtigt: {P1:full}, geboren am {DOB}, wohnhaft {ADDR}. Gesellschafter "
            "der {ORG}. Vermittelt durch {P2:full}. Deklariertes Vermögen: {AMOUNT}.",
            [
                ("Wer ist wirtschaftlich berechtigt?", "P1:full", ["P1:last"], "entity"),
                ("Wann ist die wirtschaftlich berechtigte Person geboren?", "DOB", [], "entity"),
                ("An welcher Firma ist die Person beteiligt?", "ORG", [], "entity"),
                ("Wer hat den Kunden vermittelt?", "P2:full", ["P2:last"], "entity"),
                ("Wie hoch ist das deklarierte Vermögen?", "AMOUNT", [], "non_entity"),
            ],
        ),
        "payout": (
            "E-Mail. {P2:full} von der {ORG} möchte das Auszahlungskonto auf {IBAN} ändern. {P2:first} ist unter "
            "{PHONE} erreichbar. Die Änderung gilt ab {DAY}.",
            [
                ("Wie lautet das neue Auszahlungskonto?", "IBAN", [], "entity"),
                ("Unter welcher Nummer ist die anfragende Person erreichbar?", "PHONE", [], "entity"),
                ("Für welche Firma arbeitet die anfragende Person?", "ORG", [], "entity"),
                ("Ab welchem Tag gilt die Änderung?", "DAY", [], "non_entity"),
            ],
        ),
        "minutes": (
            "Protokoll. Anwesend: {P1:full} (Vorsitz), {P2:full}, {P3:full}. Der Ausschuss genehmigt einen Kredit "
            "von {AMOUNT} an die {ORG}. {P2:first} informiert den Kunden bis {DAY}.",
            [
                ("Wer hatte den Vorsitz?", "P1:full", ["P1:last"], "entity"),
                ("Wer informiert den Kunden?", "P2:full", ["P2:first", "P2:last"], "entity"),
                ("Welche Firma erhält den Kredit?", "ORG", [], "entity"),
                ("Wie hoch ist der genehmigte Kredit?", "AMOUNT", [], "non_entity"),
                ("Bis wann wird der Kunde informiert?", "DAY", [], "non_entity"),
            ],
        ),
        "policy": (
            "Weisung. Reklamationen über {AMOUNT} gehen an das Rechtsteam unter der Leitung von {P1:full}. Kunden "
            "in {CITY} betreut {P2:full}. Antworten sind innert {N} Arbeitstagen fällig.",
            [
                ("Wer leitet das Rechtsteam?", "P1:full", ["P1:last"], "entity"),
                ("Wer betreut Kunden in {CITY}?", "P2:full", ["P2:last"], "entity"),
                ("Ab welchem Betrag gehen Reklamationen an das Rechtsteam?", "AMOUNT", [], "non_entity"),
                ("Innert wie vielen Arbeitstagen sind Antworten fällig?", "N", [], "non_entity"),
            ],
        ),
    },
}

ENTITY_SLOT_TYPES = {
    "ORG": "ORG",
    "ADDR": "ADDRESS",
    "DOB": "DATE_OF_BIRTH",
    "PHONE": "PHONE_CH",
    "IBAN": "IBAN",
}


def _values(rng: random.Random, lang: str) -> dict[str, str]:
    v: dict[str, str] = {}
    for p in ("P1", "P2", "P3"):
        for form, value in _person(rng, lang).items():
            v[f"{p}:{form}"] = value
    v.update(
        {
            "ORG": _org(rng, lang),
            "ADDR": _address(rng, lang),
            "DOB": _dob(rng, lang),
            "PHONE": make_phone(rng),
            "IBAN": make_iban_ch(rng),
            "AMOUNT": f"CHF {rng.randint(5, 900) * 1000:,}".replace(",", "'"),
            "DAY": rng.choice(WEEKDAYS[lang]),
            "CITY": rng.choice(CITIES),
            "N": str(rng.randint(3, 30)),
        }
    )
    return v


def _render(template: str, values: dict[str, str]) -> tuple[str, list[dict]]:
    """Fill a template and return the text and its personal-data spans."""
    import re

    out, ents, pos, cursor = [], [], 0, 0
    for m in re.finditer(r"\{(\w+(?::\w+)?)\}", template):
        lit = template[cursor : m.start()]
        out.append(lit)
        pos += len(lit)
        key = m.group(1)
        value = values[key]
        etype = "PERSON" if key.startswith("P") and ":" in key else ENTITY_SLOT_TYPES.get(key)
        if etype:
            ents.append({"start": pos, "end": pos + len(value), "type": etype, "text": value})
        out.append(value)
        pos += len(value)
        cursor = m.end()
    out.append(template[cursor:])
    return "".join(out), ents


def build(per_scenario: int = 2, seed: int = 41) -> list[dict]:
    rng = random.Random(seed)
    items: list[dict] = []
    for lang, scenarios in SCENARIOS.items():
        names = list(scenarios)
        for name in names:
            for k in range(per_scenario):
                values = _values(rng, lang)
                template, questions = scenarios[name]
                target_text, target_ents = _render(template, values)
                docs = [{"text": target_text, "entities": target_ents, "relevant": True}]
                for other in rng.sample([n for n in names if n != name], 2):
                    d_text, d_ents = _render(scenarios[other][0], _values(rng, lang))
                    docs.append({"text": d_text, "entities": d_ents, "relevant": False})
                rng.shuffle(docs)
                for qi, (q, slot, aliases, kind) in enumerate(questions):
                    items.append(
                        {
                            "id": f"qa-{lang}-{name}-{k}-{qi}",
                            "lang": lang,
                            "scenario": name,
                            "kind": kind,
                            "question": q.format(CITY=values["CITY"]),
                            "answer": values[slot],
                            "aliases": [values[a] for a in aliases]
                            + ([values[slot].replace("CHF ", "")] if slot == "AMOUNT" else []),
                            "docs": docs,
                        }
                    )
    return items


def main() -> None:
    items = build()
    with OUT.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    kinds = {k: sum(1 for i in items if i["kind"] == k) for k in ("entity", "non_entity")}
    print(f"{OUT.name}: {len(items)} questions {kinds}")


if __name__ == "__main__":
    main()
