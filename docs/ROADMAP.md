# Roadmap

Each milestone ships with a measurable result, published in the README.

## v0.1 Foundations (done)

- OpenAI-compatible proxy (`/v1/chat/completions`, `/v1/inspect`)
- Swiss structured detectors with checksum validation (AHV/AVS, IBAN, cards, phones, e-mails) and dictionary detector
- Consistent HMAC pseudonymisation, session vault with TTL, tolerant re-identification
- Policy-driven routing, hash-chained audit log, leak evaluation as a CI gate, Docker + Compose

## v0.2 Security hardening and free-text entities (done)

- Per-tenant (or per-session) pseudonym keys: the provider can no longer link a person across organisations
- Fail-closed by default when a detector crashes (configurable, audited)
- Indirect prompt injection: spotlighting with random per-request boundaries, tool stripping or blocking on detection (routing no longer used as a "defence")
- Tool-call arguments pseudonymised on the way out and re-identified inside JSON on the way back
- Token collision handling, vault namespaced by tenant, header validation
- GLiNER (multilingual, zero-shot) and Presidio backends behind one interface; name-mention propagation across messages
- Benchmark: 30 hand-written gold documents + 600 synthetic documents (EN/FR/DE), comparison with Presidio ([results](BENCHMARK.md))

## v0.3 Utility benchmark (done)

- 108 RAG-style questions (EN/FR/DE) with distractor documents; answers checked after re-identification
- Five conditions on the same model: no protection, gateway, `[REDACTED]`, Presidio defaults, LLM Guard defaults
- Result: no measurable accuracy loss with the gateway at 0% outbound leak ([results](BENCHMARK.md#utility-benchmark))
- Found and fixed: re-identification of bare token digests returned by small models
- Next: rerun on a frontier model and on a 7B local model; add retrieval (Qdrant + bge-m3) and LiteLLM's guardrail end to end

## v0.4 Agents and MCP

- Tool allowlist per policy, PII checks on tool arguments, egress rules
- LangGraph demo agent with two MCP servers; every tool call audited

## v0.5 Injection classifier

- Small classifier (e.g. a Prompt Guard model) next to the heuristics
- Benchmark on public prompt-injection datasets plus a multilingual set: detection rate vs false positives
- Measure spotlighting's effect on attack success rate with a real model

## v0.6 Production readiness

- Streaming (SSE) with incremental re-identification
- Encrypted vault on Redis with key rotation; tenant derived from authenticated API keys
- NER served on a separate worker (batching, GPU optional); detection latency budget
- OpenTelemetry traces and Langfuse integration, Helm chart, deployment on Azure Container Apps with Azure OpenAI
- Hosted demo: side-by-side view of what the user sends and what the provider receives
