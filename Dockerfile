# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ARG INSTALL_SENTENCE_TRANSFORMER=false

ENV PATH="/app/.venv/bin:${PATH}" \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip uv

COPY pyproject.toml uv.lock README.md ./

RUN if [ "${INSTALL_SENTENCE_TRANSFORMER}" = "true" ]; then \
        uv sync --frozen --no-dev --no-install-project --extra sentence-transformer; \
    else \
        uv sync --frozen --no-dev --no-install-project; \
    fi

COPY app ./app
COPY scripts ./scripts
COPY data/sample_corpus ./data/sample_corpus
COPY data/gold_eval ./data/gold_eval

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
