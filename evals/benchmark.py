"""Detector benchmark: how much personal data would leave the perimeter?

    pip install ".[ner]" && python -m spacy download en_core_web_sm fr_core_news_sm de_core_news_sm
    python -m evals.benchmark                    # gold + synthetic
    python -m evals.benchmark --only gold --limit 10

Metrics (computed on character spans, so any system that returns spans can be
compared on equal terms):

* residual leak rate: share of gold entities that are NOT fully masked. An
  entity counts as protected only if every alphanumeric character of it is
  covered by a masked span ("Anna Meier" with only "Meier" masked is a leak:
  the provider still sees "Anna").
* full leak rate: share of gold entities with no character masked at all.
* precision: share of masked spans that overlap a gold entity. Low precision
  means over-masking (cities, ordinary dates...), which costs answer quality.
* latency: detection time per document on CPU.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sovgate.pii import RegexDetector, Span, resolve_overlaps
from sovgate.pii.propagation import propagate

DATA = Path(__file__).parent / "data"
RESULTS = Path(__file__).parent / "results"


@dataclass
class System:
    name: str
    note: str
    detect: Callable[[str], list[Span]]


def load(sources: list[str], limit: int | None) -> list[dict]:
    docs: list[dict] = []
    for src in sources:
        with (DATA / f"{src}.jsonl").open(encoding="utf-8") as fh:
            part = [json.loads(line) for line in fh]
        docs.extend(part[:limit] if limit else part)
    return docs


def _alnum_positions(text: str, start: int, end: int) -> set[int]:
    return {i for i in range(start, end) if text[i].isalnum()}


def score(docs: list[dict], predictions: list[list[Span]], latencies: list[float]) -> dict:
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # total, protected, untouched
    by_lang: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # total, protected (free-text types)
    tp = fp = 0
    for doc, preds in zip(docs, predictions, strict=True):
        text = doc["text"]
        masked: set[int] = set()
        for s in preds:
            masked.update(range(s.start, s.end))
        gold_chars: set[int] = set()
        for e in doc["entities"]:
            chars = _alnum_positions(text, e["start"], e["end"])
            gold_chars.update(range(e["start"], e["end"]))
            covered = len(chars & masked)
            row = by_type[e["type"]]
            row[0] += 1
            row[1] += covered == len(chars)
            row[2] += covered == 0
            if e["type"] in {"PERSON", "ORG", "ADDRESS", "DATE_OF_BIRTH"}:
                by_lang[doc["lang"]][0] += 1
                by_lang[doc["lang"]][1] += covered == len(chars)
        for s in preds:
            if gold_chars & set(range(s.start, s.end)):
                tp += 1
            else:
                fp += 1
    total = sum(r[0] for r in by_type.values())
    protected = sum(r[1] for r in by_type.values())
    untouched = sum(r[2] for r in by_type.values())
    return {
        "entities": total,
        "residual_leak_rate": round(1 - protected / total, 4) if total else 0.0,
        "full_leak_rate": round(untouched / total, 4) if total else 0.0,
        "precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
        "masked_spans": tp + fp,
        "latency_ms_mean": round(statistics.mean(latencies) * 1000, 1),
        "latency_ms_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))] * 1000, 1),
        "per_type": {
            t: {"total": r[0], "residual_leak_rate": round(1 - r[1] / r[0], 4)}
            for t, r in sorted(by_type.items())
        },
        "free_text_leak_by_lang": {
            lang: round(1 - r[1] / r[0], 4) for lang, r in sorted(by_lang.items()) if r[0]
        },
    }


def run_system(system: System, docs: list[dict]) -> tuple[list[list[Span]], list[float]]:
    preds, lats = [], []
    for d in docs:
        t = time.perf_counter()
        preds.append(resolve_overlaps(system.detect(d["text"])))
        lats.append(time.perf_counter() - t)
    return preds, lats


def build_systems(gliner_thresholds: list[float]) -> list[tuple[System, Callable | None]]:
    """Return systems; GLiNER variants share one inference pass (filtered by score)."""
    regex = RegexDetector()
    systems: list[tuple[System, Callable | None]] = [
        (System("regex (v0.1)", "structured identifiers with checksums only", regex.detect), None)
    ]
    try:
        from sovgate.pii.ner import PresidioDetector

        p_en = PresidioDetector(("en",), threshold=0.5)
        p_multi = PresidioDetector(("en", "fr", "de"), threshold=0.5)
        systems.append(
            (
                System(
                    "presidio-en",
                    "Presidio default English config (engine behind LiteLLM's PII guardrail)",
                    p_en.detect,
                ),
                None,
            )
        )
        systems.append(
            (System("presidio-multi", "Presidio with EN+FR+DE spaCy models", p_multi.detect), None)
        )
    except RuntimeError as exc:
        print(f"skipping Presidio: {exc}")
    try:
        from sovgate.pii.ner import GlinerDetector

        low = min(gliner_thresholds)
        gl = GlinerDetector(threshold=low)

        def chain(th: float, with_propagation: bool) -> Callable[[str], list[Span]]:
            def run(text: str) -> list[Span]:
                spans = resolve_overlaps(regex.detect(text) + [s for s in gl.detect(text) if s.score >= th])
                return spans + propagate(text, spans) if with_propagation else spans

            return run

        default = low  # ablation at the recommended threshold
        systems.append(
            (
                System(
                    f"regex+gliner@{default} (no propagation)",
                    "ablation: name propagation disabled",
                    chain(default, False),
                ),
                None,
            )
        )
        for th in gliner_thresholds:
            systems.append(
                (
                    System(
                        f"sovgate regex+gliner@{th}",
                        f"gateway chain, GLiNER multi-PII, threshold {th}",
                        chain(th, True),
                    ),
                    None,
                )
            )
    except RuntimeError as exc:
        print(f"skipping GLiNER: {exc}")
    return systems


def to_markdown(results: dict) -> str:
    lines = []
    for source, systems in results.items():
        lines.append(f"### {source} set ({next(iter(systems.values()))['entities']} entities)\n")
        lines.append("| system | residual leak | full leak | precision | ms/doc (p95) |")
        lines.append("|---|---|---|---|---|")
        for name, r in systems.items():
            lines.append(
                f"| {name} | {r['residual_leak_rate']:.1%} | {r['full_leak_rate']:.1%} | "
                f"{r['precision']:.1%} | {r['latency_ms_mean']} ({r['latency_ms_p95']}) |"
            )
        types = sorted({t for r in systems.values() for t in r["per_type"]})
        lines.append("\nResidual leak rate per entity type:\n")
        lines.append("| system | " + " | ".join(types) + " |")
        lines.append("|---|" + "---|" * len(types))
        for name, r in systems.items():
            cells = [f"{r['per_type'].get(t, {}).get('residual_leak_rate', 0):.0%}" for t in types]
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        langs = sorted({lang for r in systems.values() for lang in r["free_text_leak_by_lang"]})
        lines.append(
            "\nResidual leak rate on free-text entities (person, org, address, birth date) per language:\n"
        )
        lines.append("| system | " + " | ".join(langs) + " |")
        lines.append("|---|" + "---|" * len(langs))
        for name, r in systems.items():
            lines.append(
                f"| {name} | " + " | ".join(f"{r['free_text_leak_by_lang'][x]:.0%}" for x in langs) + " |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["gold", "synthetic"], default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--gliner-thresholds", type=float, nargs="+", default=[0.3, 0.5])
    args = ap.parse_args()

    sources = [args.only] if args.only else ["gold", "synthetic"]
    systems = build_systems(args.gliner_thresholds)
    results: dict[str, dict] = {}
    for src in sources:
        docs = load([src], args.limit)
        results[src] = {}
        for system, _ in systems:
            preds, lats = run_system(system, docs)
            results[src][system.name] = {"note": system.note, **score(docs, preds, lats)}
            r = results[src][system.name]
            print(
                f"[{src}] {system.name:<28} leak {r['residual_leak_rate']:.1%}  "
                f"precision {r['precision']:.1%}  {r['latency_ms_mean']} ms/doc"
            )

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "benchmark.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    (RESULTS / "benchmark.md").write_text(to_markdown(results), encoding="utf-8")
    print(f"\nwritten to {RESULTS}/benchmark.(json|md)")


if __name__ == "__main__":
    main()
