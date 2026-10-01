"""Session-scoped mapping between pseudonyms and original values.

The vault is the most sensitive component of the gateway: it is the only place
where re-identification is possible. The in-memory implementation is meant for
development; a production deployment should back it with an encrypted store
(Redis with TLS + envelope encryption, or a KMS-backed database).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Session:
    mapping: dict[str, str] = field(default_factory=dict)
    expires_at: float = 0.0


class InMemoryVault:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl = ttl_seconds
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def _session(self, session_id: str) -> _Session:
        now = time.monotonic()
        s = self._sessions.get(session_id)
        if s is None or s.expires_at < now:
            s = _Session()
            self._sessions[session_id] = s
        s.expires_at = now + self.ttl
        return s

    def put(self, session_id: str, token: str, original: str) -> None:
        with self._lock:
            self._session(session_id).mapping.setdefault(token, original)

    def items(self, session_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._session(session_id).mapping)

    def purge(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def purge_expired(self) -> int:
        now = time.monotonic()
        with self._lock:
            dead = [k for k, v in self._sessions.items() if v.expires_at < now]
            for k in dead:
                del self._sessions[k]
        return len(dead)
