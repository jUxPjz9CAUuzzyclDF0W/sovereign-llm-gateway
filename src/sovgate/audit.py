"""Tamper-evident audit log (hash chain over JSON Lines).

Each record embeds the hash of the previous one, so any edit, deletion or
reordering breaks verification. Records never contain raw sensitive values:
only entity counts, routing decisions and operational metrics.

Usage:  python -m sovgate.audit verify audit/audit.jsonl
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _canonical(record: dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class AuditLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = GENESIS
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = json.loads(line)["hash"]
        return last

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            body = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "prev": self._last,
                **event,
            }
            body["hash"] = hashlib.sha256(_canonical(body)).hexdigest()
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(body, ensure_ascii=False) + "\n")
            self._last = body["hash"]
            return body


def verify(path: str | Path) -> tuple[bool, int, str]:
    """Return (ok, records_checked, message)."""
    prev = GENESIS
    n = 0
    with Path(path).open(encoding="utf-8") as fh:
        for n, line in enumerate((ln for ln in fh if ln.strip()), start=1):
            rec = json.loads(line)
            claimed = rec.pop("hash")
            if rec.get("prev") != prev:
                return False, n, f"record {n}: broken chain (prev mismatch)"
            if hashlib.sha256(_canonical(rec)).hexdigest() != claimed:
                return False, n, f"record {n}: content altered"
            prev = claimed
    return True, n, f"{n} records verified"


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) != 3 or sys.argv[1] != "verify":
        print("usage: python -m sovgate.audit verify <file>")
        sys.exit(2)
    ok, _, msg = verify(sys.argv[2])
    print(("OK  " if ok else "FAIL ") + msg)
    sys.exit(0 if ok else 1)
