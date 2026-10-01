"""Leak-rate evaluation.

A *leak* is an annotated sensitive value that is still present, in clear, in
the text that would leave the perimeter. The CI gate fails if the leak rate of
any structured entity type exceeds the threshold.

    python -m evals.leak_eval --threshold 0.0 --out evals/results/leak.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from sovgate.pii import Pseudonymizer, RegexDetector

from .synthetic import generate


def _compact(s: str) -> str:
    return re.sub(r"[\s.]", "", s).lower()


def run(n: int, seed: int) -> dict:
    pseudo = Pseudonymizer([RegexDetector()], secret=b"eval-secret-0123456789")
    totals: dict[str, int] = defaultdict(int)
    leaks: dict[str, int] = defaultdict(int)
    roundtrip_ok = 0
    samples = generate(n, seed)
    for i, s in enumerate(samples):
        sid = f"eval-{i}"
        out = pseudo.pseudonymise(s.text, sid).text
        for etype, value in s.entities.items():
            totals[etype] += 1
            if _compact(value) in _compact(out):
                leaks[etype] += 1
        roundtrip_ok += pseudo.reidentify(out, sid) == s.text
    per_type = {
        t: {"total": totals[t], "leaked": leaks[t], "leak_rate": round(leaks[t] / totals[t], 4)}
        for t in sorted(totals)
    }
    return {
        "samples": len(samples),
        "per_entity": per_type,
        "overall_leak_rate": round(sum(leaks.values()) / max(1, sum(totals.values())), 4),
        "roundtrip_exact": round(roundtrip_ok / len(samples), 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--threshold", type=float, default=0.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    res = run(args.n, args.seed)
    print(f"{'entity':<14}{'total':>7}{'leaked':>8}{'rate':>8}")
    for t, r in res["per_entity"].items():
        print(f"{t:<14}{r['total']:>7}{r['leaked']:>8}{r['leak_rate']:>8.2%}")
    print(
        f"overall leak rate: {res['overall_leak_rate']:.2%}   round-trip exact: {res['roundtrip_exact']:.2%}"
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(res, indent=2))
    worst = max(r["leak_rate"] for r in res["per_entity"].values())
    return 1 if worst > args.threshold else 0


if __name__ == "__main__":
    raise SystemExit(main())
