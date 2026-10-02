"""Utility benchmark: what does privacy cost in answer quality?

Every question of `evals/data/qa.jsonl` is answered by the same LLM under
several privacy conditions. For each condition we measure:

* accuracy: the expected answer (or an accepted alias) appears in the answer the
  *user* receives, i.e. after re-identification when the condition supports it;
* outbound leak rate: share of personal-data values from the documents that are
  still readable in the prompt sent to the model;
* latency per question (privacy processing + model call).

    # any OpenAI-compatible endpoint: OpenAI, Azure OpenAI, Ollama, llama.cpp server...
    python -m evals.utility --base-url http://localhost:11434/v1 --model qwen2.5:7b
    python -m evals.utility --base-url https://api.openai.com/v1 --model gpt-4o-mini --api-key-env OPENAI_API_KEY

Conditions (skipped automatically when their dependency is missing):

* `plaintext`   no protection (upper bound for accuracy, worst case for privacy)
* `sovgate`     this gateway: regex + GLiNER + propagation, typed reversible tokens, spotlighting
* `redact`      same detection, but values replaced by [REDACTED] (no way back)
* `presidio`    Presidio analyzer + anonymizer defaults: `<PERSON>`-style placeholders, no way back
* `llm-guard`   LLM Guard Anonymize + Deanonymize scanners, default configuration
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import statistics
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DATA = Path(__file__).parent / "data" / "qa.jsonl"
RESULTS = Path(__file__).parent / "results"

SYSTEM = (
    "You answer questions using only the documents provided. Reply with the answer only: a name, a number, "
    "a date or a short phrase, never a full sentence. Answer in the language of the question."
)


def build_messages(item: dict) -> list[dict[str, str]]:
    docs = "\n".join(f'<document id="{i + 1}">{d["text"]}</document>' for i, d in enumerate(item["docs"]))
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{docs}\n\nQuestion: {item['question']}"},
    ]


def norm(s: str) -> str:
    return re.sub(r"[^0-9a-zà-ÿăćčđşšžğı]", "", s.casefold())


def is_correct(item: dict, answer: str) -> bool:
    a = norm(answer)
    return any(norm(x) and norm(x) in a for x in [item["answer"], *item["aliases"]])


def leaked_values(item: dict, outbound: str) -> tuple[int, int]:
    """Count personal-data values still readable in the outbound prompt.

    Word-bounded and separator-tolerant: "+41 44 123 45 67" matches
    "+41441234567", but the first name "Ana" does not match inside "analyse".
    """
    text = outbound.casefold()
    values = {e["text"] for d in item["docs"] for e in d["entities"]}
    leaked = 0
    for v in values:
        tokens = re.findall(r"\w+", v.casefold())
        if tokens and re.search(r"(?<!\w)" + r"\W*".join(map(re.escape, tokens)) + r"(?!\w)", text):
            leaked += 1
    return leaked, len(values)


# ------------------------------------------------------------------ conditions


@dataclass
class Prepared:
    messages: list[dict[str, Any]]
    restore: Callable[[str], str]


@dataclass
class Condition:
    name: str
    description: str
    prepare: Callable[[dict], Prepared]


def plaintext() -> Condition:
    return Condition("plaintext", "no protection", lambda item: Prepared(build_messages(item), lambda a: a))


def _gateway(threshold: float):
    from sovgate.config import Action, Policy, Sensitivity
    from sovgate.pii import DictionaryDetector, Pseudonymizer, RegexDetector
    from sovgate.pii.ner import GlinerDetector
    from sovgate.pipeline import Gateway

    policy = Policy.load("config/policy.yaml")
    # measure pseudonymisation itself: nothing is routed to a local model here
    policy.actions[Sensitivity.RESTRICTED] = Action.PSEUDONYMISE
    pseudo = Pseudonymizer(
        [RegexDetector(), DictionaryDetector(policy.dictionary), GlinerDetector(threshold=threshold)],
        secret=b"utility-benchmark-secret",
    )
    return Gateway(policy, pseudo)


def sovgate(threshold: float = 0.3) -> Condition:
    gw = _gateway(threshold)
    counter = iter(range(10**9))

    def prepare(item: dict) -> Prepared:
        p = gw.prepare({"messages": build_messages(item)}, "bench", f"q{next(counter)}")

        def restore(answer: str) -> str:
            payload = {"choices": [{"message": {"role": "assistant", "content": answer}}]}
            return gw.restore(payload, p)["choices"][0]["message"]["content"]

        return Prepared(p.outbound["messages"], restore)

    return Condition("sovgate", "typed reversible tokens + spotlighting", prepare)


def redact(threshold: float = 0.3) -> Condition:
    gw = _gateway(threshold)
    token = re.compile(r"<[A-Z_]+_[0-9a-f]{4,12}>")

    def prepare(item: dict) -> Prepared:
        p = gw.prepare({"messages": build_messages(item)}, "bench", "redact")
        msgs = [
            {**m, "content": token.sub("[REDACTED]", m["content"])}
            if isinstance(m.get("content"), str)
            else m
            for m in p.outbound["messages"]
        ]
        return Prepared(msgs, lambda a: a)

    return Condition("redact", "same detection, irreversible [REDACTED]", prepare)


def presidio() -> Condition:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    analyzer, anonymizer = AnalyzerEngine(), AnonymizerEngine()

    def prepare(item: dict) -> Prepared:
        msgs = build_messages(item)
        text = msgs[1]["content"]
        results = analyzer.analyze(text, language="en")
        msgs[1] = {"role": "user", "content": anonymizer.anonymize(text, results).text}
        return Prepared(msgs, lambda a: a)

    return Condition("presidio", "Presidio defaults, <TYPE> placeholders, irreversible", prepare)


def llm_guard() -> Condition:
    from llm_guard.input_scanners import Anonymize
    from llm_guard.output_scanners import Deanonymize
    from llm_guard.vault import Vault

    vault = Vault()
    anonymize, deanonymize = Anonymize(vault), Deanonymize(vault)  # load models once

    def prepare(item: dict) -> Prepared:
        vault.get().clear()  # one vault per question, like one per conversation
        msgs = build_messages(item)
        sanitized, _, _ = anonymize.scan(msgs[1]["content"])
        msgs[1] = {"role": "user", "content": sanitized}

        def restore(answer: str) -> str:
            out, _, _ = deanonymize.scan(sanitized, answer)
            return out

        return Prepared(msgs, restore)

    return Condition("llm-guard", "LLM Guard Anonymize/Deanonymize defaults", prepare)


FACTORIES: dict[str, Callable[[], Condition]] = {
    "plaintext": plaintext,
    "sovgate": sovgate,
    "redact": redact,
    "presidio": presidio,
    "llm-guard": llm_guard,
}


# ------------------------------------------------------------------ runner


def ask(client: httpx.Client, args, messages: list[dict]) -> str:
    headers = {"Content-Type": "application/json"}
    key = os.getenv(args.api_key_env) if args.api_key_env else None
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {"model": args.model, "messages": messages, "temperature": 0, "max_tokens": 60}
    for attempt in range(3):
        try:
            r = client.post(f"{args.base_url.rstrip('/')}/chat/completions", json=body, headers=headers)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return ""


def summarise(rows: list[dict]) -> dict:
    def acc(rs: list[dict]) -> float:
        return round(sum(r["correct"] for r in rs) / len(rs), 4) if rs else 0.0

    leaked = sum(r["leaked"] for r in rows)
    total = sum(r["values"] for r in rows)
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_lang[r["lang"]].append(r)
    return {
        "questions": len(rows),
        "accuracy": acc(rows),
        "accuracy_entity": acc([r for r in rows if r["kind"] == "entity"]),
        "accuracy_non_entity": acc([r for r in rows if r["kind"] == "non_entity"]),
        "outbound_leak_rate": round(leaked / total, 4) if total else 0.0,
        "privacy_ms_mean": round(statistics.mean(r["privacy_ms"] for r in rows), 1),
        "llm_ms_mean": round(statistics.mean(r["llm_ms"] for r in rows), 1),
        "accuracy_by_lang": {k: acc(v) for k, v in sorted(by_lang.items())},
    }


def to_markdown(summary: dict, meta: dict) -> str:
    lines = [
        f"Model: `{meta['model']}` · {meta['questions']} questions · temperature 0\n",
        "| condition | accuracy | entity answers | non-entity answers | outbound leak | privacy ms | "
        "accuracy EN / FR / DE |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in summary.items():
        langs = " / ".join(f"{s['accuracy_by_lang'].get(x, 0):.0%}" for x in ("en", "fr", "de"))
        lines.append(
            f"| {name} | {s['accuracy']:.1%} | {s['accuracy_entity']:.1%} | {s['accuracy_non_entity']:.1%} | "
            f"{s['outbound_leak_rate']:.1%} | {s['privacy_ms_mean']} | {langs} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true", help="re-score existing rows, no model calls")
    ap.add_argument(
        "--recompute-leak",
        action="store_true",
        help="recompute outbound leak of existing rows (no model calls)",
    )
    ap.add_argument("--base-url", default="")
    ap.add_argument("--model", default="")
    ap.add_argument("--api-key-env", default=None)
    ap.add_argument("--conditions", nargs="+", default=list(FACTORIES))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(RESULTS / "utility"))
    args = ap.parse_args()
    if args.recompute_leak:
        recompute_leak(Path(args.out), args.conditions)
    if args.report_only or args.recompute_leak:
        meta = json.loads((Path(args.out) / "summary.json").read_text())["meta"]
        report(Path(args.out), meta)
        return
    if not args.base_url or not args.model:
        ap.error("--base-url and --model are required")

    items = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    items = items[: args.limit] if args.limit else items

    rows: list[dict] = []
    names: list[str] = []
    with httpx.Client(timeout=180) as client:
        for name in args.conditions:
            try:
                cond = FACTORIES[name]()  # loaded one at a time to bound memory
            except ImportError as exc:
                print(f"skipping {name}: missing dependency ({exc.name})")
                continue
            names.append(cond.name)
            for i, item in enumerate(items):
                t0 = time.perf_counter()
                prepared = cond.prepare(item)
                t1 = time.perf_counter()
                raw = ask(client, args, prepared.messages)
                t2 = time.perf_counter()
                answer = prepared.restore(raw)
                t3 = time.perf_counter()
                outbound = "\n".join(
                    m["content"] for m in prepared.messages if isinstance(m.get("content"), str)
                )
                leaked, values = leaked_values(item, outbound)
                rows.append(
                    {
                        "condition": cond.name,
                        "id": item["id"],
                        "lang": item["lang"],
                        "kind": item["kind"],
                        "question": item["question"],
                        "expected": item["answer"],
                        "model_answer": raw,
                        "user_answer": answer,
                        "correct": is_correct(item, answer),
                        "leaked": leaked,
                        "values": values,
                        "privacy_ms": round(((t1 - t0) + (t3 - t2)) * 1000, 1),
                        "llm_ms": round((t2 - t1) * 1000, 1),
                    }
                )
                if (i + 1) % 20 == 0:
                    done = [r for r in rows if r["condition"] == cond.name]
                    print(
                        f"[{cond.name}] {i + 1}/{len(items)} accuracy so far {summarise(done)['accuracy']:.1%}"
                    )
            del cond
            gc.collect()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for n in names:  # one file per condition, so conditions can run in separate processes
        part = [r for r in rows if r["condition"] == n]
        (out / f"rows-{n}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in part) + "\n"
        )
    report(out, {"model": args.model, "base_url": args.base_url, "questions": len(items)})


def recompute_leak(out: Path, conditions: list[str]) -> None:
    """Privacy processing is deterministic (fixed HMAC key, fixed tenant scope): rebuild each outbound
    prompt, re-measure the leak and re-restore the stored model answer with the current code."""
    qa = {
        it["id"]: it
        for it in (json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip())
    }
    for name in conditions:
        f = out / f"rows-{name}.jsonl"
        if not f.exists():
            continue
        cond = FACTORIES[name]()
        rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        for r in rows:
            prepared = cond.prepare(qa[r["id"]])
            outbound = "\n".join(m["content"] for m in prepared.messages if isinstance(m.get("content"), str))
            r["leaked"], r["values"] = leaked_values(qa[r["id"]], outbound)
            # privacy processing is deterministic too: re-apply the current restore step
            r["user_answer"] = prepared.restore(r["model_answer"])
        f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
        print(f"[{name}] leak recomputed")
        del cond
        gc.collect()


def report(out: Path, meta: dict) -> None:
    """Summarise every rows-*.jsonl present in `out`."""
    order = list(FACTORIES)
    rows = [
        json.loads(line)
        for f in sorted(out.glob("rows-*.jsonl"))
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # re-score from the current QA file, so metric fixes never need new model calls
    qa = {
        it["id"]: it
        for it in (json.loads(x) for x in DATA.read_text(encoding="utf-8").splitlines() if x.strip())
    }
    for r in rows:
        if r["id"] in qa:
            r["correct"] = is_correct(qa[r["id"]], r["user_answer"])
    names = sorted({r["condition"] for r in rows}, key=lambda n: order.index(n) if n in order else 99)
    summary = {n: summarise([r for r in rows if r["condition"] == n]) for n in names}
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, indent=2))
    (out / "summary.md").write_text(to_markdown(summary, meta), encoding="utf-8")
    print(to_markdown(summary, meta))


if __name__ == "__main__":
    main()
