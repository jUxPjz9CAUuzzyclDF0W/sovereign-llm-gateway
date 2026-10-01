"""OpenAI-compatible gateway.

Point any OpenAI SDK client (or a LangChain / LlamaIndex RAG) at this service
by changing `base_url`. Each request goes through:

    detect entities -> scan for injection -> route -> pseudonymise -> forward
    -> re-identify response -> append audit record
"""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from . import __version__
from .audit import AuditLog
from .config import Action, Policy, Settings
from .guards import scan
from .pii import DictionaryDetector, Pseudonymizer, RegexDetector, Span
from .pii.vault import InMemoryVault
from .router import decide

PLACEHOLDER_NOTICE = (
    "Some values in this conversation were replaced by placeholders such as "
    "<PERSON_3f9a1c>. Treat each placeholder as an opaque name and reproduce it "
    "verbatim, including the angle brackets, whenever you refer to it."
)


def _iter_text_parts(message: dict[str, Any]):
    """Yield (container, key) pairs pointing at every text field of a message."""
    content = message.get("content")
    if isinstance(content, str):
        yield message, "content"
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                yield part, "text"


def create_app(
    settings: Settings | None = None,
    policy: Policy | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or Settings()
    policy = policy or Policy.load(settings.policy_path)
    if not settings.hmac_secret:
        raise RuntimeError("SOVGATE_HMAC_SECRET must be set")

    pseudo = Pseudonymizer(
        detectors=[RegexDetector(), DictionaryDetector(policy.dictionary)],
        secret=settings.hmac_secret.encode(),
        vault=InMemoryVault(settings.vault_ttl_seconds),
    )
    audit = AuditLog(settings.audit_path)
    client = httpx.AsyncClient(transport=transport, timeout=120)

    app = FastAPI(title="Sovereign LLM Gateway", version=__version__)
    app.state.pseudonymizer = pseudo
    app.state.audit = audit

    def analyse(messages: list[dict[str, Any]]):
        spans: list[Span] = []
        joined: list[str] = []
        for msg in messages:
            for container, key in _iter_text_parts(msg):
                spans.extend(pseudo.detect(container[key]))
                if msg.get("role") != "system":
                    joined.append(container[key])
        verdict = scan("\n".join(joined))
        return spans, verdict, decide(spans, verdict, policy)

    def transform(messages: list[dict[str, Any]], session_id: str) -> list[dict[str, Any]]:
        out = copy.deepcopy(messages)
        for msg in out:
            for container, key in _iter_text_parts(msg):
                container[key] = pseudo.pseudonymise(container[key], session_id).text
        return [{"role": "system", "content": PLACEHOLDER_NOTICE}, *out]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/v1/inspect")
    async def inspect(body: dict[str, Any], x_session_id: str | None = Header(default=None)):
        """Dry run: show what would leave the perimeter, without calling any model."""
        session_id = x_session_id or f"inspect-{uuid.uuid4()}"
        messages = body.get("messages", [])
        spans, verdict, decision = analyse(messages)
        outbound = transform(messages, session_id) if decision.action == Action.PSEUDONYMISE else messages
        pseudo.vault.purge(session_id)
        return {
            "decision": {
                "action": decision.action.value,
                "upstream": decision.upstream,
                "sensitivity": decision.sensitivity.value,
                "reasons": decision.reasons,
            },
            "entities": [{"type": s.entity_type, "source": s.source} for s in spans],
            "injection": {"flagged": verdict.flagged, "rules": verdict.rules},
            "outbound_messages": outbound,
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(body: dict[str, Any], x_session_id: str | None = Header(default=None)):
        if body.get("stream"):
            raise HTTPException(400, "streaming is not supported yet (see ROADMAP)")
        session_id = x_session_id or str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        started = time.perf_counter()

        messages = body.get("messages", [])
        spans, verdict, decision = analyse(messages)

        record: dict[str, Any] = {
            "request_id": request_id,
            "session_id": session_id,
            "action": decision.action.value,
            "upstream": decision.upstream,
            "sensitivity": decision.sensitivity.value,
            "entities": _count(spans),
            "injection_rules": verdict.rules,
        }

        if decision.action == Action.BLOCK or decision.upstream is None:
            audit.append({**record, "status": "blocked"})
            raise HTTPException(403, {"error": "blocked by policy", "reasons": decision.reasons})

        upstream = policy.upstreams[decision.upstream]
        outbound = dict(body)
        outbound["model"] = upstream.model
        if decision.action == Action.PSEUDONYMISE:
            outbound["messages"] = transform(messages, session_id)

        headers = {"Content-Type": "application/json"}
        if upstream.api_key:
            headers["Authorization"] = f"Bearer {upstream.api_key}"
        try:
            resp = await client.post(
                f"{upstream.base_url.rstrip('/')}/chat/completions", json=outbound, headers=headers
            )
        except httpx.HTTPError as exc:
            audit.append({**record, "status": "upstream_error", "error": type(exc).__name__})
            raise HTTPException(502, "upstream unavailable") from exc

        payload = resp.json()
        if resp.status_code >= 400:
            audit.append({**record, "status": "upstream_error", "http_status": resp.status_code})
            return JSONResponse(payload, status_code=resp.status_code)

        if decision.action == Action.PSEUDONYMISE:
            for choice in payload.get("choices", []):
                msg = choice.get("message") or {}
                if isinstance(msg.get("content"), str):
                    msg["content"] = pseudo.reidentify(msg["content"], session_id)

        usage = payload.get("usage") or {}
        audit.append(
            {
                **record,
                "status": "ok",
                "model": upstream.model,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            }
        )
        return JSONResponse(
            payload,
            headers={
                "X-Sovgate-Action": decision.action.value,
                "X-Sovgate-Upstream": decision.upstream,
                "X-Sovgate-Request-Id": request_id,
            },
        )

    return app


def _count(spans: list[Span]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in spans:
        counts[s.entity_type] = counts.get(s.entity_type, 0) + 1
    return counts
