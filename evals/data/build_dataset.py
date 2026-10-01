"""Build the benchmark dataset (JSON Lines, character-level span annotations).

    python -m evals.data.build_dataset

Writes:
  evals/data/gold.jsonl       hand-written documents (see gold.py)
  evals/data/synthetic.jsonl  procedurally generated documents, 3 languages

Synthetic documents deliberately vary how people are named (full name, official
"surname first" order, initials, title + surname, first name only, lower-case
chat handles), use names that are also common words (Wolf, Fuchs, Weiss, Petit,
Blanc...), names from communities living in Switzerland, and include hard
negatives (cities, streets in non-personal context, regulations).
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from evals.synthetic import make_ahv, make_card, make_iban_ch, make_phone

from .gold import GOLD

OUT = Path(__file__).parent

PLACEHOLDER_TYPES = {
    "AHV": "AHV_NUMBER",
    "IBAN": "IBAN",
    "CARD": "CREDIT_CARD",
    "PHONE": "PHONE_CH",
    "PHONE2": "PHONE_CH",
}

# ---------------------------------------------------------------- name pools

FIRST = {
    "de": [
        "Andrea",
        "Thomas",
        "Reto",
        "Brigitte",
        "Lukas",
        "Mirjam",
        "Beat",
        "Corinne",
        "Urs",
        "Nadine",
        "Simon",
        "Ursula",
        "Stefan",
        "Jasmin",
        "Marco",
        "Sandra",
        "Fabian",
        "Monika",
    ],
    "fr": [
        "Chloé",
        "Julien",
        "Nathalie",
        "Olivier",
        "Marie-Claire",
        "Sébastien",
        "Valérie",
        "Thierry",
        "Léa",
        "Grégoire",
        "Sandrine",
        "Hugo",
        "Céline",
        "Pascal",
        "Mathilde",
        "Yannick",
    ],
    "it": ["Luca", "Martina", "Matteo", "Giulia", "Paolo", "Chiara", "Davide", "Elena"],
    "mixed": [
        "Arben",
        "Ayşe",
        "Mehmet",
        "Thi Hoa",
        "Karim",
        "Fatima",
        "Ana",
        "João",
        "Priya",
        "Nadia",
        "Dragan",
        "Selin",
        "Tesfay",
        "Kumaran",
        "Leutrim",
        "Mariana",
        "Frank",
        "Rose",
        "Grace",
    ],
}
LAST = {
    "de": [
        "Keller",
        "Meier",
        "Brunner",
        "Steiner",
        "Zimmermann",
        "Baumann",
        "Huber",
        "Graf",
        "Frey",
        "Wyss",
        "Hofer",
        "Imhof",
        "Egli",
        "Kälin",
        "Odermatt",
        "Ammann",
        "Wolf",
        "Fuchs",
        "Weiss",
        "Schwarz",
        "Koch",
        "Bauer",
        "Meister",
        "Vogel",
    ],
    "fr": [
        "Dubois",
        "Favre",
        "Rochat",
        "Perret",
        "Monnier",
        "Girard",
        "Mercier",
        "Junod",
        "Aubert",
        "Moret",
        "Pittet",
        "Vuilleumier",
        "Lambert",
        "Petit",
        "Blanc",
        "Leblanc",
        "Roux",
        "Martin",
    ],
    "it": ["Rossi", "Bianchi", "Fontana", "Bernasconi", "Ferrari", "Colombo", "Galli", "Bianco"],
    "mixed": [
        "Krasniqi",
        "Yilmaz",
        "Demir",
        "Nguyen",
        "Benali",
        "Haddad",
        "Silva",
        "Ferreira",
        "Gashi",
        "Petrović",
        "Kaya",
        "Tesfamariam",
        "Sivakumar",
        "Berisha",
        "Santos",
    ],
}

ORG_PREFIX = [
    "Alpenblick",
    "Seeland",
    "Rigiblick",
    "Léman",
    "Jura",
    "Aaretal",
    "Säntis",
    "Rhône",
    "Gotthard",
    "Bodensee",
    "Sonnenberg",
    "Lavaux",
    "Engadin",
    "Mittelland",
]
ORG_SECTOR = {
    "de": ["Treuhand", "Logistik", "Immobilien", "Bau", "Versicherungen", "Informatik", "Medizintechnik"],
    "fr": ["Fiduciaire", "Assurances", "Conseil", "Immobilier", "Informatique", "Transports"],
    "en": ["Consulting", "Capital", "Data Services", "Logistics", "Health", "Software"],
}
ORG_FORM = {"de": ["AG", "GmbH"], "fr": ["SA", "Sàrl"], "en": ["AG", "SA", "Ltd"]}

STREETS = {
    "de": ["Bahnhofstrasse", "Seestrasse", "Dorfstrasse", "Hauptstrasse", "Kirchweg", "Industriestrasse"],
    "fr": ["rue du Marché", "avenue de la Gare", "chemin des Vignes", "rue de Lausanne", "route de Berne"],
    "it": ["Via Nassa", "Via Cantonale", "Via San Gottardo"],
}
TOWNS = {
    "de": [
        ("8001", "Zürich"),
        ("3011", "Bern"),
        ("4051", "Basel"),
        ("6003", "Luzern"),
        ("9000", "St. Gallen"),
        ("8400", "Winterthur"),
        ("6300", "Zug"),
        ("5000", "Aarau"),
    ],
    "fr": [
        ("1204", "Genève"),
        ("1003", "Lausanne"),
        ("2000", "Neuchâtel"),
        ("1700", "Fribourg"),
        ("1950", "Sion"),
        ("1110", "Morges"),
    ],
    "it": [("6900", "Lugano"), ("6500", "Bellinzona"), ("6600", "Locarno")],
}
CITIES = ["Zürich", "Genève", "Bern", "Basel", "Lausanne", "Lugano", "Luzern", "St. Gallen", "Winterthur"]

MONTHS = {
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
}

# ---------------------------------------------------------------- templates
# {P1:full} {P1:official} {P1:initial} {P1:first} {P1:last} {P1:lower} {P1:email}
# {ORG} {ADDR} {DOB} {PHONE} {IBAN} {AHV} {CARD}; not annotated: {CITY} {AMOUNT} {REF}

TEMPLATES = {
    "en": [
        (
            "email",
            "Hi {P1:first},\n\nAs discussed, {P2:full} from {ORG} asked us to change the payout account "
            "to {IBAN}. You can reach {P2:first} on {PHONE}.\n\nBest,\n{P3:full}",
        ),
        (
            "email",
            "Dear Mr {P1:last},\n\nThank you for your documents. We have updated your address to "
            "{ADDR}. If anything is wrong, write to {P1:email}.\n\nKind regards,\n{P2:full}\n{ORG}",
        ),
        (
            "kyc_note",
            "KYC file {REF}. Beneficial owner: {P1:full}, born {DOB}, resident at {ADDR}. "
            "AHV {AHV}. Shareholder of {ORG}. Introduced by {P2:initial}.",
        ),
        (
            "chat",
            "[10:01] {P1:lower}: card {CARD} declined again, customer is Ms {P2:last}\n"
            "[10:02] {P3:lower}: I'll call her on {PHONE}\n[10:05] {P3:lower}: done, {P1:lower} pls close",
        ),
        (
            "meeting_minutes",
            "Minutes, {CITY}. Present: {P1:full} (chair), {P2:full}, {P3:full}. The board "
            "approved the loan to {ORG}. {P2:first} will brief the client.",
        ),
        (
            "support_ticket",
            "Ticket {REF}. Caller {P1:full} ({PHONE}) moved to {ADDR}. Date of birth: {DOB}. "
            "Owner: {P2:initial}.",
        ),
        (
            "rag_chunk",
            "Section {REF}. Claims above {AMOUNT} go to the legal team led by {P1:full}. Clients of "
            "{ORG} in {CITY} are handled by {P2:full}.",
        ),
        (
            "rag_chunk",
            "Accounts opened in {CITY} follow the same closing procedure as all other branches. "
            "Limits above {AMOUNT} require a second signature.",
        ),
        (
            "hr_letter",
            "Dear Ms {P1:last},\n\nWe are pleased to offer you the position at {ORG}. Salary will be "
            "paid to {IBAN}. Please send the signed copy to {P2:full}.\n\nRegards,\n{P3:full}",
        ),
        ("official_list", "Participants: {P1:official}; {P2:official}; {P3:official}. Venue: {CITY}."),
    ],
    "fr": [
        (
            "email",
            "Bonjour {P1:first},\n\nComme convenu, {P2:full} de {ORG} souhaite modifier le compte de "
            "versement : {IBAN}. Tu peux joindre {P2:first} au {PHONE}.\n\nBonne journée,\n{P3:full}",
        ),
        (
            "email",
            "Madame {P1:last},\n\nNous avons bien reçu vos documents et mis à jour votre adresse : "
            "{ADDR}. En cas d'erreur, écrivez à {P1:email}.\n\nMeilleures salutations,\n{P2:full}\n{ORG}",
        ),
        (
            "kyc_note",
            "Dossier KYC {REF}. Ayant droit économique : {P1:full}, né le {DOB}, domicilié {ADDR}. "
            "N° AVS {AHV}. Associé de {ORG}. Introduit par {P2:initial}.",
        ),
        (
            "chat",
            "[10:01] {P1:lower} : la carte {CARD} est refusée, c'est M. {P2:last}\n"
            "[10:02] {P3:lower} : je le rappelle au {PHONE}\n[10:05] {P3:lower} : ok c'est réglé",
        ),
        (
            "meeting_minutes",
            "PV de séance, {CITY}. Présents : {P1:full} (présidence), {P2:full}, {P3:full}. "
            "Le comité approuve le crédit à {ORG}. {P2:first} informera le client.",
        ),
        (
            "support_ticket",
            "Ticket {REF}. Appel de {P1:full} ({PHONE}), nouvelle adresse {ADDR}. Date de "
            "naissance : {DOB}. Responsable : {P2:initial}.",
        ),
        (
            "rag_chunk",
            "Article {REF}. Les réclamations supérieures à {AMOUNT} sont transmises au service "
            "juridique dirigé par {P1:full}. Les clients de {ORG} à {CITY} sont suivis par {P2:full}.",
        ),
        (
            "rag_chunk",
            "Les comptes ouverts à {CITY} suivent la même procédure de clôture que les autres "
            "succursales. Au-delà de {AMOUNT}, une double signature est requise.",
        ),
        (
            "hr_letter",
            "Madame {P1:last},\n\nNous avons le plaisir de vous engager au sein de {ORG}. Le salaire "
            "sera versé sur {IBAN}. Merci de retourner le contrat à {P2:full}.\n\nCordialement,\n"
            "{P3:full}",
        ),
        ("official_list", "Participants : {P1:official} ; {P2:official} ; {P3:official}. Lieu : {CITY}."),
    ],
    "de": [
        (
            "email",
            "Hoi {P1:first}\n\nWie besprochen möchte {P2:full} von der {ORG} das Auszahlungskonto auf "
            "{IBAN} ändern. Du erreichst {P2:first} unter {PHONE}.\n\nLiebe Grüsse\n{P3:full}",
        ),
        (
            "email",
            "Sehr geehrter Herr {P1:last}\n\nBesten Dank für Ihre Unterlagen. Wir haben Ihre Adresse auf "
            "{ADDR} geändert. Bei Fehlern schreiben Sie an {P1:email}.\n\nFreundliche Grüsse\n"
            "{P2:full}\n{ORG}",
        ),
        (
            "kyc_note",
            "KYC-Dossier {REF}. Wirtschaftlich berechtigt: {P1:official}, geboren am {DOB}, wohnhaft "
            "{ADDR}. AHV-Nr. {AHV}. Gesellschafter der {ORG}. Vermittelt durch {P2:initial}.",
        ),
        (
            "chat",
            "[10:01] {P1:lower}: Karte {CARD} wieder abgelehnt, Kundin ist Frau {P2:last}\n"
            "[10:02] {P3:lower}: ich ruf sie unter {PHONE} an\n[10:05] {P3:lower}: erledigt",
        ),
        (
            "meeting_minutes",
            "Protokoll, {CITY}. Anwesend: {P1:full} (Vorsitz), {P2:full}, {P3:full}. Der "
            "Ausschuss genehmigt den Kredit an die {ORG}. {P2:first} informiert den Kunden.",
        ),
        (
            "support_ticket",
            "Ticket {REF}. Anruf von {P1:full} ({PHONE}), neue Adresse {ADDR}. Geburtsdatum: "
            "{DOB}. Zuständig: {P2:initial}.",
        ),
        (
            "rag_chunk",
            "Ziffer {REF}. Reklamationen über {AMOUNT} gehen an das Rechtsteam unter der Leitung "
            "von {P1:full}. Kunden der {ORG} in {CITY} betreut {P2:full}.",
        ),
        (
            "rag_chunk",
            "Konten, die in {CITY} eröffnet wurden, folgen derselben Schliessungsprozedur wie alle "
            "anderen Filialen. Über {AMOUNT} ist eine Doppelunterschrift nötig.",
        ),
        (
            "hr_letter",
            "Liebe Frau {P1:last}\n\nWir freuen uns, Ihnen die Stelle bei der {ORG} anzubieten. Der "
            "Lohn wird auf {IBAN} überwiesen. Bitte senden Sie den Vertrag an {P2:full}.\n\n"
            "Herzliche Grüsse\n{P3:full}",
        ),
        ("official_list", "Teilnehmende: {P1:official}; {P2:official}; {P3:official}. Ort: {CITY}."),
    ],
}

SLOT_RE = re.compile(r"\{(\w+)(?::(\w+))?\}")


def _strip_accents_lower(s: str) -> str:
    table = str.maketrans("éèêëàâäöüôîïçşăćČ", "eeeeaaaouoiicsacc")
    return re.sub(r"[^a-z.-]", "", s.lower().translate(table).replace(" ", "."))


def _person(rng: random.Random, lang: str) -> dict[str, str]:
    pool = rng.choices([lang if lang in FIRST else "de", "it", "mixed"], weights=[6, 1, 3])[0]
    first, last = rng.choice(FIRST[pool]), rng.choice(LAST[pool])
    return {
        "full": f"{first} {last}",
        "official": f"{last} {first}",
        "initial": f"{first[0]}. {last}",
        "first": first,
        "last": last,
        "lower": first.split()[0].lower(),
        "email": f"{_strip_accents_lower(first)}.{_strip_accents_lower(last)}@example.ch",
    }


def _dob(rng: random.Random, lang: str) -> str:
    y, m, d = rng.randint(1950, 2004), rng.randint(1, 12), rng.randint(1, 28)
    style = rng.randint(0, 2)
    if style == 0:
        return f"{d:02d}.{m:02d}.{y}"
    if style == 1:
        return f"{y}-{m:02d}-{d:02d}"
    if lang == "fr":
        return f"{d} {MONTHS['fr'][m - 1]} {y}"
    if lang == "de":
        return f"{d}. {MONTHS['de'][m - 1]} {y}"
    return f"{d} {MONTHS['en'][m - 1]} {y}"


def _address(rng: random.Random, lang: str) -> str:
    region = (
        rng.choices(["de", "fr", "it"], weights=[5, 4, 1])[0]
        if lang == "en"
        else (lang if rng.random() < 0.8 else rng.choice(["de", "fr", "it"]))
    )
    postcode, town = rng.choice(TOWNS[region])
    return f"{rng.choice(STREETS[region])} {rng.randint(1, 120)}, {postcode} {town}"


def _org(rng: random.Random, lang: str) -> str:
    return f"{rng.choice(ORG_PREFIX)} {rng.choice(ORG_SECTOR[lang])} {rng.choice(ORG_FORM[lang])}"


def render(template: str, rng: random.Random, lang: str) -> tuple[str, list[dict]]:
    people = {f"P{i}": _person(rng, lang) for i in (1, 2, 3)}
    cache: dict[str, str] = {}
    out: list[str] = []
    ents: list[dict] = []
    pos = 0
    cursor = 0
    for m in SLOT_RE.finditer(template):
        literal = template[cursor : m.start()]
        out.append(literal)
        pos += len(literal)
        slot, form = m.group(1), m.group(2)
        etype: str | None
        if slot in people:
            value = people[slot][form]
            etype = "EMAIL" if form == "email" else "PERSON"
        else:
            if slot not in cache:
                cache[slot] = {
                    "ORG": lambda: _org(rng, lang),
                    "ADDR": lambda: _address(rng, lang),
                    "DOB": lambda: _dob(rng, lang),
                    "PHONE": lambda: make_phone(rng),
                    "IBAN": lambda: make_iban_ch(rng),
                    "AHV": lambda: make_ahv(rng),
                    "CARD": lambda: make_card(rng),
                    "CITY": lambda: rng.choice(CITIES),
                    "AMOUNT": lambda: f"CHF {rng.randint(5, 500) * 1000:,}".replace(",", "'"),
                    "REF": lambda: f"{rng.randint(1, 9)}.{rng.randint(1, 20)}",
                }[slot]()
            value = cache[slot]
            etype = {
                "ORG": "ORG",
                "ADDR": "ADDRESS",
                "DOB": "DATE_OF_BIRTH",
                "PHONE": "PHONE_CH",
                "IBAN": "IBAN",
                "AHV": "AHV_NUMBER",
                "CARD": "CREDIT_CARD",
            }.get(slot)
        if etype:
            ents.append({"start": pos, "end": pos + len(value), "type": etype, "text": value})
        out.append(value)
        pos += len(value)
        cursor = m.end()
    out.append(template[cursor:])
    return "".join(out), ents


def build_gold(seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    docs = []
    for i, d in enumerate(GOLD):
        text = d["text"]
        ents: list[dict] = []
        # fill placeholders first, recording spans
        values = {
            k: {
                "AHV": make_ahv,
                "IBAN": make_iban_ch,
                "CARD": make_card,
                "PHONE": make_phone,
                "PHONE2": make_phone,
            }[k](rng)
            for k in PLACEHOLDER_TYPES
        }
        out, cursor, pos = [], 0, 0
        for m in re.finditer(r"\{(AHV|IBAN|CARD|PHONE2?)\}", text):
            lit = text[cursor : m.start()]
            out.append(lit)
            pos += len(lit)
            v = values[m.group(1)]
            ents.append({"start": pos, "end": pos + len(v), "type": PLACEHOLDER_TYPES[m.group(1)], "text": v})
            out.append(v)
            pos += len(v)
            cursor = m.end()
        out.append(text[cursor:])
        text = "".join(out)
        # then the hand annotations: longest surfaces first, no overlaps
        taken = [(e["start"], e["end"]) for e in ents]
        for surface, etype in sorted(d["entities"], key=lambda x: -len(x[0])):
            hits = 0
            for m in re.finditer(rf"(?<!\w){re.escape(surface)}(?!\w)", text):
                if any(m.start() < b and a < m.end() for a, b in taken):
                    continue
                ents.append({"start": m.start(), "end": m.end(), "type": etype, "text": surface})
                taken.append((m.start(), m.end()))
                hits += 1
            if hits == 0 and not any(surface in e["text"] for e in ents):
                raise ValueError(f"gold doc {i}: '{surface}' not found")
        docs.append(
            {
                "id": f"gold-{i:03d}",
                "source": "gold",
                "lang": d["lang"],
                "doc_type": d["doc_type"],
                "text": text,
                "entities": sorted(ents, key=lambda e: e["start"]),
            }
        )
    return docs


def build_synthetic(n_per_lang: int = 200, seed: int = 23) -> list[dict]:
    rng = random.Random(seed)
    docs = []
    for lang in ("en", "fr", "de"):
        for i in range(n_per_lang):
            doc_type, tpl = TEMPLATES[lang][i % len(TEMPLATES[lang])]
            text, ents = render(tpl, rng, lang)
            docs.append(
                {
                    "id": f"syn-{lang}-{i:03d}",
                    "source": "synthetic",
                    "lang": lang,
                    "doc_type": doc_type,
                    "text": text,
                    "entities": ents,
                }
            )
    return docs


def main() -> None:
    for name, docs in (("gold", build_gold()), ("synthetic", build_synthetic())):
        path = OUT / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for d in docs:
                for e in d["entities"]:
                    assert d["text"][e["start"] : e["end"]] == e["text"], (d["id"], e)
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        n_ent = sum(len(d["entities"]) for d in docs)
        print(f"{path.name}: {len(docs)} documents, {n_ent} entities")


if __name__ == "__main__":
    main()
