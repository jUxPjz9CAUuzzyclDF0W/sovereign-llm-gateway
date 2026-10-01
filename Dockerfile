FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# EXTRAS=ner adds GLiNER/Presidio with CPU torch (much larger image): docker build --build-arg EXTRAS=ner .
ARG EXTRAS=""
COPY pyproject.toml README.md ./
COPY src ./src
RUN if [ "$EXTRAS" = "ner" ]; then \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir ".[ner]"; \
    else \
      pip install --no-cache-dir .; \
    fi

COPY config ./config

RUN useradd --create-home --uid 10001 gateway && mkdir -p /app/audit && chown gateway /app/audit
USER gateway

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')"
CMD ["uvicorn", "sovgate.main:app", "--host", "0.0.0.0", "--port", "8080"]
