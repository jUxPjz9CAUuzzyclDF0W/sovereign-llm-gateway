import json
from pathlib import Path

from evals.benchmark import score
from evals.data.build_dataset import build_gold, build_synthetic
from sovgate.pii import Span

DATA = Path("evals/data")


def test_committed_datasets_are_reproducible():
    for name, docs in (("gold", build_gold()), ("synthetic", build_synthetic())):
        committed = [
            json.loads(line) for line in (DATA / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert committed == docs, f"{name}.jsonl is stale: run `make dataset`"


def test_spans_match_text():
    for d in build_gold() + build_synthetic(n_per_lang=20):
        for e in d["entities"]:
            assert d["text"][e["start"] : e["end"]] == e["text"]


def test_partial_masking_counts_as_leak():
    doc = {"text": "Anna Meier", "lang": "en", "entities": [{"start": 0, "end": 10, "type": "PERSON"}]}
    partial = score([doc], [[Span(5, 10, "PERSON", "Meier")]], [0.0])
    full = score([doc], [[Span(0, 10, "PERSON", "Anna Meier")]], [0.0])
    assert partial["residual_leak_rate"] == 1.0 and partial["full_leak_rate"] == 0.0
    assert full["residual_leak_rate"] == 0.0 and full["precision"] == 1.0
