"""OpenAI-compatible gateway (FastAPI layer).

Point any OpenAI SDK client (or a LangChain / LlamaIndex RAG) at this service
by changing `base_url`. The security logic lives in `pipeline.Gateway`; this
module only handles HTTP, upstream calls and audit records.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from . import __version__
from .audit import AuditLog
from .config import Action, Policy, Settings
from .pii import Pseudonymizer
from .pii.factory import build_detectors
from .pii.vault import InMemoryVault
from .pipeline import DetectionFailure, Gateway, Prepared

_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def _checked_id(value: str | None, default: str, name: str) -> str:
    if value is None:
        return default
    if not _ID_RE.fullmatch(value):
        raise HTTPException(400, f"invalid {name}")
    return value


def create_app(
    settings: Settings | None = None,
    policy: Policy | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    detectors: list | None = None,
) -> FastAPI:
    settings = settings or Settings()
    policy = policy or Policy.load(settings.policy_path)
    if len(settings.hmac_secret) < 16:
        raise RuntimeError("SOVGATE_HMAC_SECRET must be set (min. 16 characters)")

    pseudo = Pseudonymizer(
        detectors=detectors if detectors is not None else build_detectors(policy),
        secret=settings.hmac_secret.encode(),
        vault=InMemoryVault(settings.vault_ttl_seconds),
    )
    gateway = Gateway(policy, pseudo)
    audit = AuditLog(settings.audit_path)
    client = httpx.AsyncClient(transport=transport, timeout=120)

    app = FastAPI(title="Sovereign LLM Gateway", version=__version__)
    app.state.gateway = gateway
    app.state.audit = audit

    def base_record(p: Prepared, request_id: str, tenant: str, session: str) -> dict[str, Any]:
        # Never put raw text in the audit trail: counts and decisions only.
        return {
            "request_id": request_id,
            "tenant": tenant,
            "session_id": session,
            "action": p.decision.action.value,
            "upstream": p.decision.upstream,
            "sensitivity": p.decision.sensitivity.value,
            "entities": p.entity_counts,
            "injection_rules": p.verdict.rules,
            "scan_scope": p.scan_scope,
            "spotlighted": p.spotlighted,
            "tools_stripped": p.decision.strip_tools,
            "detection_failed": p.detection_failed,
        }

    def prepare_or_fail(body: dict[str, Any], tenant: str, session: str, request_id: str) -> Prepared:
        try:
            return gateway.prepare(body, tenant, session)
        except DetectionFailure as exc:
            audit.append(
                {"request_id": request_id, "tenant": tenant, "status": "detector_error", "error": str(exc)}
            )
            raise HTTPException(503, "entity detection unavailable; request refused (fail-closed)") from exc

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/v1/inspect")
    async def inspect(
        body: dict[str, Any],
        x_tenant_id: str | None = Header(default=None),
    ):
        """Dry run: show exactly what would leave the perimeter, without calling any model."""
        tenant = _checked_id(x_tenant_id, "default", "tenant id")
        session = f"inspect-{uuid.uuid4()}"
        p = prepare_or_fail(body, tenant, session, session)
        pseudo.vault.purge(p.vault_key)
        return {
            "decision": {
                "action": p.decision.action.value,
                "upstream": p.decision.upstream,
                "sensitivity": p.decision.sensitivity.value,
                "reasons": p.decision.reasons,
                "tools_stripped": p.decision.strip_tools,
            },
            "entities": [{"type": s.entity_type, "source": s.source} for s in p.spans],
            "injection": {"flagged": p.verdict.flagged, "rules": p.verdict.rules, "scope": p.scan_scope},
            "spotlighted_segments": p.spotlighted,
            "outbound": p.outbound,
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        body: dict[str, Any],
        x_session_id: str | None = Header(default=None),
        x_tenant_id: str | None = Header(default=None),
    ):
        # In production the tenant comes from the authenticated API key, not a header.
        if body.get("stream"):
            raise HTTPException(400, "streaming is not supported yet (see ROADMAP)")
        tenant = _checked_id(x_tenant_id, "default", "tenant id")
        session = _checked_id(x_session_id, str(uuid.uuid4()), "session id")
        request_id = str(uuid.uuid4())
        started = time.perf_counter()

        p = prepare_or_fail(body, tenant, session, request_id)
        record = base_record(p, request_id, tenant, session)

        if p.decision.action == Action.BLOCK or p.decision.upstream is None:
            audit.append({**record, "status": "blocked"})
            raise HTTPException(403, {"error": "blocked by policy", "reasons": p.decision.reasons})

        upstream = policy.upstreams[p.decision.upstream]
        outbound = {**p.outbound, "model": upstream.model}
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

        payload = gateway.restore(payload, p)
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
                "X-Sovgate-Action": p.decision.action.value,
                "X-Sovgate-Upstream": p.decision.upstream,
                "X-Sovgate-Request-Id": request_id,
            },
        )

    return app
