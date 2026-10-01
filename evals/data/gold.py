"""Hand-written gold documents (EN / FR / DE).

Written by hand to look like real Swiss business text, not like the templates
the regex detectors were designed for. Every person, organisation, address and
number is fictional. Structured identifiers are written as placeholders
({AHV}, {IBAN}, {CARD}, {PHONE}, {PHONE2}) and filled with generated, valid,
fictional values by `build_dataset.py`.

Annotation guidelines
* PERSON: the name only, without titles ("Herr", "Mme", "Dr"). Initials count
  ("T. Keller"). Lower-case chat mentions count.
* ORG: legal or trading names of organisations, including suffix (AG, SA, GmbH).
* ADDRESS: street + number + postcode + town when present, as one span.
* DATE_OF_BIRTH: only dates that are birth dates; other dates are not annotated.
* Cities, countries, regulations and products are NOT annotated (hard negatives).

Each document lists (surface, TYPE); every case-sensitive, word-bounded
occurrence of the surface is annotated.
"""

GOLD = [
    # ------------------------------------------------------------------ EN
    {
        "lang": "en",
        "doc_type": "email",
        "text": (
            "Hi Sarah,\n\nFollowing our call, Thomas Keller from Alpenblick Treuhand AG confirmed that "
            "the payout should go to {IBAN}. He can be reached on {PHONE}. Please update the file "
            "before the Zurich office closes the quarter.\n\nBest regards,\nDaniel Brunner\nCompliance, "
            "Banque du Léman SA"
        ),
        "entities": [
            ("Sarah", "PERSON"),
            ("Thomas Keller", "PERSON"),
            ("Alpenblick Treuhand AG", "ORG"),
            ("Daniel Brunner", "PERSON"),
            ("Banque du Léman SA", "ORG"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "kyc_note",
        "text": (
            "KYC review, client file 2024-118. Beneficial owner: Arben Krasniqi, born 14.02.1979, "
            "residing at Seestrasse 41, 8800 Thalwil. Social security number {AHV}. Source of funds: "
            "sale of shares in Krasniqi Bau GmbH. Mr Krasniqi was referred by Laura Fontana."
        ),
        "entities": [
            ("Arben Krasniqi", "PERSON"),
            ("Krasniqi", "PERSON"),
            ("14.02.1979", "DATE_OF_BIRTH"),
            ("Seestrasse 41, 8800 Thalwil", "ADDRESS"),
            ("Krasniqi Bau GmbH", "ORG"),
            ("Laura Fontana", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "chat",
        "text": (
            "[09:12] marco: can someone check why the card {CARD} got declined?\n"
            "[09:13] priya: on it. customer is Mrs Yilmaz, the one who called yesterday\n"
            "[09:15] priya: looks like a fraud rule, I'll ask jonas to whitelist it\n"
            "[09:16] marco: thx, cc Ayşe Yilmaz on the reply"
        ),
        "entities": [
            ("marco", "PERSON"),
            ("priya", "PERSON"),
            ("Yilmaz", "PERSON"),
            ("jonas", "PERSON"),
            ("Ayşe Yilmaz", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "meeting_minutes",
        "text": (
            "Minutes, credit committee, 3 June. Present: Dr. Elena Rossi (chair), Marc Favre, "
            "Sophie Meier. The committee reviewed the Basel III impact and approved the facility for "
            "Jura Mécanique Sàrl. Action: Marc to send the term sheet to the client's CFO, "
            "Pascal Rochat, by Friday."
        ),
        "entities": [
            ("Elena Rossi", "PERSON"),
            ("Marc Favre", "PERSON"),
            ("Sophie Meier", "PERSON"),
            ("Jura Mécanique Sàrl", "ORG"),
            ("Marc", "PERSON"),
            ("Pascal Rochat", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "support_ticket",
        "text": (
            "Ticket #55821. Caller: Thi Hoa Nguyen ({PHONE}). She moved from Bern to "
            "Rue de la Servette 12, 1201 Genève and her statements still go to the old address. "
            "Date of birth on file: 1991-07-30. Escalated to back office (owner: S. Weber)."
        ),
        "entities": [
            ("Thi Hoa Nguyen", "PERSON"),
            ("Rue de la Servette 12, 1201 Genève", "ADDRESS"),
            ("1991-07-30", "DATE_OF_BIRTH"),
            ("S. Weber", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "hr_letter",
        "text": (
            "Dear Ms Wolf,\n\nWe are pleased to confirm your appointment as Senior Analyst at "
            "Helvetic Data Services AG starting 1 September. Your salary will be paid to the account "
            "{IBAN}. Please return the signed contract to Peter Huber in HR.\n\nKind regards,\n"
            "Nadia Gashi"
        ),
        "entities": [
            ("Wolf", "PERSON"),
            ("Helvetic Data Services AG", "ORG"),
            ("Peter Huber", "PERSON"),
            ("Nadia Gashi", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "insurance_claim",
        "text": (
            "Claim 7781-B. Policyholder Frank Leblanc reported water damage at Chemin des Vignes 8, "
            "1110 Morges. The plumber, Fuchs Sanitär GmbH, estimated CHF 12,400. Contact the "
            "policyholder at {PHONE} or frank.leblanc@example.ch. Adjuster: Isabelle Christen."
        ),
        "entities": [
            ("Frank Leblanc", "PERSON"),
            ("Chemin des Vignes 8, 1110 Morges", "ADDRESS"),
            ("Fuchs Sanitär GmbH", "ORG"),
            ("frank.leblanc@example.ch", "EMAIL"),
            ("Isabelle Christen", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "rag_chunk",
        "text": (
            "Section 4.2 Escalation. Disputes above CHF 50,000 are escalated to the Legal team, "
            "currently led by Martina Bianchi. For clients of Banque du Léman SA in Ticino, the "
            "contact is Luca Bernasconi in Lugano. The Matterhorn project is out of scope."
        ),
        "entities": [
            ("Martina Bianchi", "PERSON"),
            ("Banque du Léman SA", "ORG"),
            ("Luca Bernasconi", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "email",
        "text": (
            "From: Kevin Schmid\nTo: Ana Silva Ferreira\n\nAna, the AHV number you sent ({AHV}) "
            "does not match the one in the payroll export. Can you double-check with Rolf at "
            "Treuhand Zollinger & Partner AG? Thanks, Kevin"
        ),
        "entities": [
            ("Kevin Schmid", "PERSON"),
            ("Ana Silva Ferreira", "PERSON"),
            ("Ana", "PERSON"),
            ("Rolf", "PERSON"),
            ("Treuhand Zollinger & Partner AG", "ORG"),
            ("Kevin", "PERSON"),
        ],
    },
    {
        "lang": "en",
        "doc_type": "rag_chunk",
        "text": (
            "Onboarding checklist: verify identity documents, check the client against sanctions "
            "lists, and record the source of wealth. For corporate clients in Geneva or Lausanne, "
            "request the commercial register extract. No personal data should be stored in email."
        ),
        "entities": [],
    },
    # ------------------------------------------------------------------ FR
    {
        "lang": "fr",
        "doc_type": "email",
        "text": (
            "Bonjour Madame Rochat,\n\nSuite à notre entretien, je vous confirme que le versement "
            "sera effectué sur le compte {IBAN} au nom de Marie-Claire Rochat. Pour toute question, "
            "vous pouvez joindre mon collègue Julien Perret au {PHONE}.\n\nMeilleures salutations,\n"
            "Claude Monnier\nFiduciaire Lémanique SA"
        ),
        "entities": [
            ("Rochat", "PERSON"),
            ("Marie-Claire Rochat", "PERSON"),
            ("Julien Perret", "PERSON"),
            ("Claude Monnier", "PERSON"),
            ("Fiduciaire Lémanique SA", "ORG"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "kyc_note",
        "text": (
            "Note KYC. Client : M. Karim Benali, né le 3 mars 1985, domicilié avenue de la Gare 17, "
            "1003 Lausanne. Numéro AVS : {AHV}. Activité : associé gérant de Benali Import-Export "
            "Sàrl. Introduit par Mme Chantal Girard."
        ),
        "entities": [
            ("Karim Benali", "PERSON"),
            ("3 mars 1985", "DATE_OF_BIRTH"),
            ("avenue de la Gare 17, 1003 Lausanne", "ADDRESS"),
            ("Benali Import-Export Sàrl", "ORG"),
            ("Chantal Girard", "PERSON"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "chat",
        "text": (
            "[14:02] léa : quelqu'un peut rappeler le client au {PHONE} ? c'est M. Petit\n"
            "[14:03] nicolas : je m'en occupe\n"
            "[14:05] nicolas : il veut parler à Sandrine Favre directement"
        ),
        "entities": [
            ("léa", "PERSON"),
            ("Petit", "PERSON"),
            ("nicolas", "PERSON"),
            ("Sandrine Favre", "PERSON"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "meeting_minutes",
        "text": (
            "Procès-verbal du conseil de fondation, Fondation Horizon Santé. Présents : "
            "Pr Jean-Luc Mercier (président), Fatima Haddad, Olivier Blanc. Le conseil approuve le "
            "budget 2027. M. Blanc présentera le rapport à la séance de Neuchâtel."
        ),
        "entities": [
            ("Fondation Horizon Santé", "ORG"),
            ("Jean-Luc Mercier", "PERSON"),
            ("Fatima Haddad", "PERSON"),
            ("Olivier Blanc", "PERSON"),
            ("Blanc", "PERSON"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "insurance_claim",
        "text": (
            "Sinistre n° 2026-4471. L'assurée, Mme Nathalie Dubois, née le 22.11.1972, signale un vol "
            "à son domicile, rue du Marché 4, 1204 Genève. La carte {CARD} a été bloquée. "
            "Expert mandaté : Bureau d'expertises Roux SA."
        ),
        "entities": [
            ("Nathalie Dubois", "PERSON"),
            ("22.11.1972", "DATE_OF_BIRTH"),
            ("rue du Marché 4, 1204 Genève", "ADDRESS"),
            ("Bureau d'expertises Roux SA", "ORG"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "hr_letter",
        "text": (
            "Madame Leroy,\n\nNous avons le plaisir de vous confirmer votre engagement au sein de "
            "Jura Mécanique Sàrl à partir du 1er octobre. Votre salaire sera versé sur le compte "
            "{IBAN}. Veuillez retourner le contrat signé à M. Thierry Aubert.\n\nCordialement,\n"
            "Valérie Junod, RH"
        ),
        "entities": [
            ("Leroy", "PERSON"),
            ("Jura Mécanique Sàrl", "ORG"),
            ("Thierry Aubert", "PERSON"),
            ("Valérie Junod", "PERSON"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "support_ticket",
        "text": (
            "Ticket 30912. Le client Jonathan Moret ({PHONE2}) n'arrive plus à se connecter depuis "
            "son déménagement à Fribourg. Ancienne adresse : chemin des Pâquerettes 2, 1700 Fribourg. "
            "Assigné à : g.pittet"
        ),
        "entities": [
            ("Jonathan Moret", "PERSON"),
            ("chemin des Pâquerettes 2, 1700 Fribourg", "ADDRESS"),
            ("g.pittet", "PERSON"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "rag_chunk",
        "text": (
            "Article 12. Les demandes de crédit supérieures à CHF 1 million sont soumises au comité. "
            "Pour la Suisse romande, le responsable est Grégoire Vuilleumier, basé à Sion. Les "
            "dossiers de la Banque du Léman SA suivent la même procédure."
        ),
        "entities": [
            ("Grégoire Vuilleumier", "PERSON"),
            ("Banque du Léman SA", "ORG"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "email",
        "text": (
            "De : Sébastien Rey\nÀ : équipe conformité\n\nLe nouveau client, Lumière Conseil SA, "
            "a fourni l'extrait du registre du commerce. L'administrateur unique est M. Hugo Lambert, "
            "né le 9 juin 1990. Je vous laisse valider. Seb"
        ),
        "entities": [
            ("Sébastien Rey", "PERSON"),
            ("Lumière Conseil SA", "ORG"),
            ("Hugo Lambert", "PERSON"),
            ("9 juin 1990", "DATE_OF_BIRTH"),
            ("Seb", "PERSON"),
        ],
    },
    {
        "lang": "fr",
        "doc_type": "rag_chunk",
        "text": (
            "Procédure de clôture de compte : vérifier l'identité du titulaire, solder les ordres "
            "permanents et envoyer la confirmation par courrier recommandé. Les comptes ouverts à "
            "Genève et à Lausanne sont traités par le même service."
        ),
        "entities": [],
    },
    # ------------------------------------------------------------------ DE
    {
        "lang": "de",
        "doc_type": "email",
        "text": (
            "Sehr geehrter Herr Zimmermann\n\nBesten Dank für Ihre Unterlagen. Die Auszahlung erfolgt "
            "auf das Konto {IBAN}. Bei Fragen erreichen Sie Frau Brigitte Steiner unter {PHONE}.\n\n"
            "Freundliche Grüsse\nMarkus Graf\nAlpenblick Treuhand AG"
        ),
        "entities": [
            ("Zimmermann", "PERSON"),
            ("Brigitte Steiner", "PERSON"),
            ("Markus Graf", "PERSON"),
            ("Alpenblick Treuhand AG", "ORG"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "kyc_note",
        "text": (
            "KYC-Notiz. Kundin: Keller Andrea (amtliche Schreibweise), geboren am 12. März 1987, "
            "wohnhaft Bahnhofstrasse 12, 8001 Zürich. AHV-Nr. {AHV}. Wirtschaftlich Berechtigte der "
            "Keller Immobilien AG. Vermittelt durch Herrn Reto Baumann."
        ),
        "entities": [
            ("Keller Andrea", "PERSON"),
            ("12. März 1987", "DATE_OF_BIRTH"),
            ("Bahnhofstrasse 12, 8001 Zürich", "ADDRESS"),
            ("Keller Immobilien AG", "ORG"),
            ("Reto Baumann", "PERSON"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "chat",
        "text": (
            "[08:45] stefan: kann jemand die Karte {CARD} prüfen? Kunde ist Herr Weiss\n"
            "[08:47] corinne: mach ich, ist das der von gestern?\n"
            "[08:48] stefan: ja genau, Lukas Weiss aus Winterthur"
        ),
        "entities": [
            ("stefan", "PERSON"),
            ("Weiss", "PERSON"),
            ("corinne", "PERSON"),
            ("Lukas Weiss", "PERSON"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "meeting_minutes",
        "text": (
            "Protokoll Verwaltungsratssitzung, Helvetic Data Services AG, 14. Mai. Anwesend: "
            "Dr. Ursula Frey (Präsidentin), Beat Wyss, Mirjam Hofer. Der Verwaltungsrat genehmigt die "
            "Jahresrechnung. Herr Wyss informiert über das Projekt in St. Gallen."
        ),
        "entities": [
            ("Helvetic Data Services AG", "ORG"),
            ("Ursula Frey", "PERSON"),
            ("Beat Wyss", "PERSON"),
            ("Mirjam Hofer", "PERSON"),
            ("Wyss", "PERSON"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "insurance_claim",
        "text": (
            "Schadenfall 88-1205. Versicherungsnehmer Jan Fuchs, geb. 05.09.1968, meldet einen "
            "Wasserschaden an der Liegenschaft Dorfstrasse 3, 3612 Steffisburg. Offerte der "
            "Sanitär Aebi GmbH liegt vor. Rückruf unter {PHONE2}."
        ),
        "entities": [
            ("Jan Fuchs", "PERSON"),
            ("05.09.1968", "DATE_OF_BIRTH"),
            ("Dorfstrasse 3, 3612 Steffisburg", "ADDRESS"),
            ("Sanitär Aebi GmbH", "ORG"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "hr_letter",
        "text": (
            "Liebe Frau Lehmann\n\nWir freuen uns, Ihnen die Anstellung als Projektleiterin bei der "
            "Rheintal Logistik GmbH zu bestätigen. Der Lohn wird auf das Konto {IBAN} überwiesen. "
            "Ihre Vorgesetzte ist Sandra Kälin.\n\nHerzliche Grüsse\nThomas Egli, Personalabteilung"
        ),
        "entities": [
            ("Lehmann", "PERSON"),
            ("Rheintal Logistik GmbH", "ORG"),
            ("Sandra Kälin", "PERSON"),
            ("Thomas Egli", "PERSON"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "support_ticket",
        "text": (
            "Ticket 77310. Kunde Mehmet Demir ({PHONE}) meldet, dass seine E-Mail-Adresse "
            "m.demir@example.ch nicht mehr funktioniert. Neue Adresse: Hauptstrasse 55, 4051 Basel. "
            "Bearbeitet von: N. Schneider"
        ),
        "entities": [
            ("Mehmet Demir", "PERSON"),
            ("m.demir@example.ch", "EMAIL"),
            ("Hauptstrasse 55, 4051 Basel", "ADDRESS"),
            ("N. Schneider", "PERSON"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "rag_chunk",
        "text": (
            "Ziffer 7.3 Eskalation. Reklamationen über CHF 10'000 werden an das Rechtsteam unter der "
            "Leitung von Claudia Meyer weitergeleitet. Für Kunden der Rheintal Logistik GmbH ist "
            "Roger Ammann in Chur zuständig."
        ),
        "entities": [
            ("Claudia Meyer", "PERSON"),
            ("Rheintal Logistik GmbH", "ORG"),
            ("Roger Ammann", "PERSON"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "email",
        "text": (
            "Von: Patrick Odermatt\nAn: Team Compliance\n\nHallo zusammen, die Firma Sonnenberg "
            "Holding AG hat den Handelsregisterauszug geschickt. Einziger Verwaltungsrat ist "
            "Herr Simon Imhof, geboren 1975-04-18. Bitte prüfen. Gruss Pädi"
        ),
        "entities": [
            ("Patrick Odermatt", "PERSON"),
            ("Sonnenberg Holding AG", "ORG"),
            ("Simon Imhof", "PERSON"),
            ("1975-04-18", "DATE_OF_BIRTH"),
            ("Pädi", "PERSON"),
        ],
    },
    {
        "lang": "de",
        "doc_type": "rag_chunk",
        "text": (
            "Kontoschliessung: Identität des Inhabers prüfen, Daueraufträge auflösen und die "
            "Bestätigung eingeschrieben versenden. Konten in Zürich und Bern werden zentral "
            "bearbeitet. Die Weisung gilt ab dem 1. Januar."
        ),
        "entities": [],
    },
]
