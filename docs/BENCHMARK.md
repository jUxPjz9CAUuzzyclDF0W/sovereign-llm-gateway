# Detector benchmark

Reproduce with `make install-ner && make benchmark` (CPU is enough). Results below: 2 vCPU cloud container, no GPU.

## Question

Before a prompt leaves the perimeter, how much personal data is still readable by the model provider, and how much harmless text is masked for nothing?

## Datasets

| set | documents | entities | how it was made |
|---|---|---|---|
| gold | 30 (10 EN, 10 FR, 10 DE) | 145 | written by hand to look like real Swiss business text: e-mails, KYC notes, chat transcripts, meeting minutes, claims, HR letters, support tickets, RAG chunks, including 3 documents with no personal data |
| synthetic | 600 (200 per language) | 2,720 | procedural generator: 10 document types per language, names from Swiss and diaspora communities, varied mention forms (full name, surname-first, initials, title + surname, first name only, lower-case chat handles), names that are also common words (Wolf, Fuchs, Weiss, Petit, Blanc) |

All names, organisations and numbers are fictional; identifiers are valid (checksums) but generated. Annotation guidelines are in [`evals/data/gold.py`](../evals/data/gold.py). `tests/test_dataset.py` checks that the committed JSONL files are reproducible from the generator.

## Metrics

- **Residual leak rate**: an entity is protected only if every alphanumeric character of it is masked. Partially masked names count as leaks.
- **Full leak rate**: entities with no character masked at all.
- **Precision**: share of masked spans that overlap a real entity (over-masking costs answer quality).
- **Latency**: detection time per document.

## Systems

- `regex (v0.1)`: structured identifiers with checksum validation only.
- `presidio-en`: Microsoft Presidio, default recognisers, English spaCy model. This approximates the default PII masking of LiteLLM, which uses Presidio.
- `presidio-multi`: Presidio with English, French and German spaCy models, results merged.
- `regex+gliner (no propagation)`: ablation.
- `sovgate regex+gliner@t`: the gateway's chain, GLiNER `urchade/gliner_multi_pii-v1` at threshold `t`, plus name propagation.

## Results

### gold set (145 entities)

| system | residual leak | full leak | precision | ms/doc (p95) |
|---|---|---|---|---|
| regex (v0.1) | 83.5% | 83.5% | 100.0% | 0.0 (0.1) |
| presidio-en | 33.8% | 19.3% | 58.7% | 18.5 (24.9) |
| presidio-multi | 17.9% | 8.3% | 54.3% | 53.3 (81.4) |
| regex+gliner@0.3 (no propagation) | 6.2% | 6.2% | 95.8% | 209.5 (232.9) |
| sovgate regex+gliner@0.3 | 2.1% | 2.1% | 96.0% | 200.7 (221.6) |
| sovgate regex+gliner@0.5 | 4.1% | 4.1% | 97.9% | 196.1 (214.5) |

Residual leak rate per entity type:

| system | ADDRESS | AHV_NUMBER | CREDIT_CARD | DATE_OF_BIRTH | EMAIL | IBAN | ORG | PERSON | PHONE_CH |
|---|---|---|---|---|---|---|---|---|---|
| regex (v0.1) | 100% | 0% | 0% | 100% | 0% | 0% | 100% | 100% | 0% |
| presidio-en | 89% | 100% | 0% | 25% | 0% | 0% | 14% | 29% | 89% |
| presidio-multi | 44% | 100% | 0% | 25% | 0% | 0% | 5% | 9% | 89% |
| regex+gliner@0.3 (no propagation) | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 11% | 0% |
| sovgate regex+gliner@0.3 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 4% | 0% |
| sovgate regex+gliner@0.5 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 7% | 0% |

Residual leak rate on free-text entities (person, org, address, birth date) per language:

| system | de | en | fr |
|---|---|---|---|
| regex (v0.1) | 100% | 100% | 100% |
| presidio-en | 32% | 27% | 34% |
| presidio-multi | 8% | 13% | 13% |
| regex+gliner@0.3 (no propagation) | 5% | 11% | 5% |
| sovgate regex+gliner@0.3 | 3% | 2% | 3% |
| sovgate regex+gliner@0.5 | 8% | 2% | 5% |

### synthetic set (2720 entities)

| system | residual leak | full leak | precision | ms/doc (p95) |
|---|---|---|---|---|
| regex (v0.1) | 82.3% | 82.3% | 100.0% | 0.0 (0.0) |
| presidio-en | 33.0% | 20.5% | 68.9% | 11.7 (15.2) |
| presidio-multi | 21.2% | 9.9% | 61.5% | 32.8 (42.8) |
| regex+gliner@0.3 (no propagation) | 6.2% | 6.2% | 97.0% | 174.6 (201.5) |
| sovgate regex+gliner@0.3 | 1.7% | 1.7% | 97.1% | 173.0 (199.5) |
| sovgate regex+gliner@0.5 | 2.5% | 2.5% | 97.4% | 174.9 (200.1) |

Residual leak rate per entity type:

| system | ADDRESS | AHV_NUMBER | CREDIT_CARD | DATE_OF_BIRTH | EMAIL | IBAN | ORG | PERSON | PHONE_CH |
|---|---|---|---|---|---|---|---|---|---|
| regex (v0.1) | 100% | 0% | 0% | 100% | 0% | 0% | 100% | 100% | 0% |
| presidio-en | 89% | 95% | 2% | 20% | 0% | 0% | 23% | 27% | 85% |
| presidio-multi | 69% | 70% | 2% | 20% | 0% | 0% | 18% | 12% | 73% |
| regex+gliner@0.3 (no propagation) | 0% | 0% | 0% | 0% | 0% | 0% | 1% | 10% | 0% |
| sovgate regex+gliner@0.3 | 0% | 0% | 0% | 0% | 0% | 0% | 1% | 3% | 0% |
| sovgate regex+gliner@0.5 | 0% | 0% | 0% | 0% | 0% | 0% | 1% | 4% | 0% |

Residual leak rate on free-text entities (person, org, address, birth date) per language:

| system | de | en | fr |
|---|---|---|---|
| regex (v0.1) | 100% | 100% | 100% |
| presidio-en | 36% | 24% | 32% |
| presidio-multi | 20% | 18% | 16% |
| regex+gliner@0.3 (no propagation) | 9% | 7% | 7% |
| sovgate regex+gliner@0.3 | 4% | 1% | 1% |
| sovgate regex+gliner@0.5 | 6% | 2% | 1% |

## Limitations and threats to validity

- Both datasets were authored alongside the system. Name propagation was added after error analysis on the gold set, and the GLiNER threshold (0.3) was chosen on these results: treat the gateway's numbers as optimistic. An external, independently annotated dataset is the next step.
- The gold set is small (145 entities): one entity is 0.7 points.
- Presidio runs with small spaCy models and without custom recognisers. A tuned Presidio deployment (large models, Swiss recognisers) would do better; the comparison shows defaults, which is what most deployments run.
- Detection quality is not answer quality: the cost of pseudonymisation on RAG answers is measured separately (roadmap v0.3).
- GLiNER costs about 200 ms per document on CPU; production needs batching or a GPU worker.

## Utility benchmark

Reproduce: `pip install -e ".[ner,bench]"`, start any OpenAI-compatible server, then `make utility BASE_URL=... MODEL=...`. Results below: Qwen2.5-1.5B-Instruct Q4_K_M served by llama.cpp on 2 vCPU, temperature 0.

**Question.** Does pseudonymisation degrade the answers of a RAG assistant, compared with sending clear text or with other privacy tools?

**Data.** [`evals/data/qa.jsonl`](../evals/data/qa.jsonl): 108 questions (36 per language) over 4 document types (KYC note, payout e-mail, meeting minutes, policy section). Each question comes with three documents, the relevant one and two distractors that also mention people and companies. 72 questions have personal data as their answer (name, company, IBAN, phone, date of birth), 36 do not (amount, weekday, deadline). Retrieval is held fixed: the gateway retrieves on clear text inside the perimeter, so only generation is affected.

**Metrics.** *Accuracy*: the expected value (or an accepted alias, e.g. the surname) appears in the answer the user receives, after re-identification when the condition supports it. *Outbound leak*: share of personal-data values from the documents that are still readable, word-bounded, in the prompt sent to the model.

**Results.**

| condition | accuracy | personal-data answers | other answers | outbound leak | privacy ms / question | EN / FR / DE |
|---|---|---|---|---|---|---|
| no protection | 90.7% | 86.1% | 100% | 100% | 0 | 86% / 100% / 86% |
| this gateway | 94.4% | 93.1% | 97.2% | 0% | 477 | 97% / 94% / 92% |
| same detection, `[REDACTED]` | 33.3% | 0% | 100% | 0% | 480 | 33% / 33% / 33% |
| Presidio defaults | 37.0% | 18.1% | 75.0% | 17.7% | 42 | 42% / 42% / 28% |
| LLM Guard defaults | 63.9% | 45.8% | 100% | 35.4% | 361 | 69% / 64% / 58% |

**What the errors show.**

- Presidio replaces every person with the same `<PERSON>` placeholder, so the model cannot say which person, and nothing maps the answer back. It also loses 9 of 36 non-personal answers although the amounts and weekdays are still in the prompt: with every person and company turned into the same placeholder, the three documents look alike and the model mixes them up.
- LLM Guard's numbered placeholders are reversible, but its default (English) model misses many Swiss names, identifiers and phone formats, so a third of the values still leave in clear, and some names are split into several placeholders.
- With the gateway, the small model sometimes answered with only the hex part of a token (`7d8241`). The benchmark caught this; re-identification now also maps a bare 6-character digest back. All rows were re-scored by replaying the deterministic privacy steps on the stored model answers (`--recompute-leak`), without new model calls.
- Remaining gateway errors are model mistakes: picking the wrong person token, or inventing a date when the real one is hidden behind a token.

**Limitations.** One small model; results with a frontier model may differ in both directions (better at handling tokens, but also better at answering in clear). Synthetic questions generated by the same code as the detection set, so the 0% leak is optimistic. 108 questions: differences of a few points are noise. Presidio and LLM Guard run with default settings, which is how most deployments start but not their best possible configuration.
