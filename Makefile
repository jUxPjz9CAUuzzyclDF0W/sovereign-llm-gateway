.PHONY: install install-ner test lint eval dataset benchmark utility run up verify-audit

install:
	pip install -e ".[dev]"

install-ner:
	pip install -e ".[dev,ner]"
	python -m spacy download en_core_web_sm
	python -m spacy download fr_core_news_sm
	python -m spacy download de_core_news_sm

lint:
	ruff check . && ruff format --check .

test:
	pytest -q

eval:
	PYTHONPATH=src python -m evals.leak_eval --threshold 0.0 --out evals/results/leak.json

dataset:
	PYTHONPATH=src:. python -m evals.data.build_dataset
	PYTHONPATH=src:. python -m evals.data.build_qa

benchmark:
	PYTHONPATH=src:. python -m evals.benchmark

# any OpenAI-compatible endpoint, e.g. make utility BASE_URL=http://localhost:11434/v1 MODEL=qwen2.5:7b
BASE_URL ?= http://localhost:11434/v1
MODEL ?= qwen2.5:7b
API_KEY_ENV ?=
utility:
	for c in plaintext sovgate redact presidio llm-guard; do \
	  PYTHONPATH=src:. python -m evals.utility --base-url $(BASE_URL) --model $(MODEL) \
	    $(if $(API_KEY_ENV),--api-key-env $(API_KEY_ENV)) --conditions $$c --out evals/results/utility || exit 1; \
	done
	PYTHONPATH=src:. python -m evals.plot_utility evals/results/utility docs/img/privacy-utility.png

run:
	uvicorn sovgate.main:app --reload --port 8080

up:
	docker compose up --build

verify-audit:
	python -m sovgate.audit verify audit/audit.jsonl
