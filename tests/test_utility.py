import json
from pathlib import Path

from evals.data.build_qa import build
from evals.utility import build_messages, is_correct, leaked_values


def test_committed_qa_set_is_reproducible():
    committed = [json.loads(x) for x in Path("evals/data/qa.jsonl").read_text(encoding="utf-8").splitlines()]
    assert committed == build(), "qa.jsonl is stale: run `python -m evals.data.build_qa`"


def test_every_answer_is_in_the_relevant_document():
    for item in build():
        relevant = next(d for d in item["docs"] if d["relevant"])
        assert item["answer"] in relevant["text"], item["id"]
        for d in item["docs"]:
            for e in d["entities"]:
                assert d["text"][e["start"] : e["end"]] == e["text"]


def test_messages_wrap_documents_for_spotlighting():
    item = build()[0]
    user = build_messages(item)[1]["content"]
    assert user.count("<document id=") == 3 and user.endswith(item["question"])


def test_answer_matching_is_format_tolerant():
    item = {"answer": "CH12 3470 3970 1176 0865 0", "aliases": []}
    assert is_correct(item, "The account is CH1234703970117608650.")
    item = {"answer": "Thomas Keller", "aliases": ["Keller"]}
    assert is_correct(item, "Mr Keller") and not is_correct(item, "<PERSON>")
    assert is_correct({"answer": "CHF 152'000", "aliases": []}, "CHF 152'000")


def test_leak_counts_values_still_readable():
    item = {"docs": [{"entities": [{"text": "Anna Meier"}, {"text": "+41 44 123 45 67"}]}]}
    assert leaked_values(item, "call <PERSON_ab12cd> on +41441234567") == (1, 2)


def test_leak_is_word_bounded():
    item = {"docs": [{"entities": [{"text": "Ana"}]}]}
    assert leaked_values(item, "please analyse the banana") == (0, 1)
    assert leaked_values(item, "Ana called") == (1, 1)
