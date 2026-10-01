# Roadmap

Each milestone ships with a measurable result, published in the README.

## v0.1 Foundations (done)

- OpenAI-compatible proxy (`/v1/chat/completions`, `/v1/inspect`)
- Swiss structured detectors with checksum validation (AHV/AVS, IBAN, cards, phones, e-mails) and dictionary detector
- Consistent HMAC pseudonymisation, session vault with TTL, tolerant re-identification
- Policy-driven routing: passthrough / pseudonymise / local / block
- Heuristic prompt-injection scan (EN/FR/DE)
- Hash-chained audit log with verifier
- Leak evaluation as a CI gate, Docker image, Compose stack with Ollama

## v0.2 Free-text entities, multilingual

- NER backends behind the `Detector` interface: Presidio (spaCy) and GLiNER, for EN/FR/DE/IT
- Annotated evaluation set with names, organisations and addresses (synthetic, manually reviewed)
- Metric: precision / recall / leak rate per entity and per language; pick the default backend from the numbers

## v0.3 Utility benchmark: what does privacy cost?

- Demo RAG: Qdrant + local embeddings (bge-m3) over a public document corpus seeded with synthetic personal data
- Compare answer quality across: no protection, typed tokens, realistic surrogates (Faker), local-only model
- Metrics: faithfulness and answer correctness (LLM-as-judge, RAGAS), latency overhead, cost per 1k requests
- Publish the results table and a short write-up

## v0.4 Agents and MCP

- Tool-call guard for agent traffic: tool allowlist per policy, PII checks on tool arguments, egress rules
- Pseudonymisation of tool results before they re-enter the context
- LangGraph demo agent with two MCP servers; every tool call audited

## v0.5 Injection classifier

- Add a small classifier (e.g. a Prompt Guard model) next to the heuristics
- Benchmark both on public prompt-injection datasets plus a multilingual set: detection rate vs false positives

## v0.6 Production readiness

- Streaming (SSE) with incremental re-identification
- Encrypted vault on Redis with key rotation
- OpenTelemetry traces and Langfuse integration
- Auth (API keys / OIDC), rate limiting, Helm chart
- Hosted demo: side-by-side view of what the user sends and what the provider receives
