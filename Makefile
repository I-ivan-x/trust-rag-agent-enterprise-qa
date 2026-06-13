PYTHON ?= python
UV ?= $(PYTHON) -m uv
API_URL ?= http://127.0.0.1:8000
EMBEDDING_PROVIDER ?= mock

.PHONY: sync lint test ingest index-mock index-real run docker-build docker-up docker-down smoke smoke-data docker-smoke

sync:
	$(UV) sync

lint:
	$(UV) run ruff check .

test:
	$(UV) run pytest

ingest:
	$(UV) run python scripts/ingest_corpus.py

index-mock:
	$(UV) run python scripts/rebuild_indexes.py --embedding-provider mock

index-real:
	$(UV) run python scripts/rebuild_indexes.py --embedding-provider sentence_transformer

run:
	$(UV) run uvicorn app.main:app --reload

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down

smoke-data:
	$(UV) run python scripts/smoke_test.py --prepare --skip-health --embedding-provider $(EMBEDDING_PROVIDER)

smoke:
	$(UV) run python scripts/smoke_test.py --base-url $(API_URL) --chat

docker-smoke:
	docker compose up -d --build
	docker compose exec -T api python scripts/smoke_test.py --base-url http://127.0.0.1:8000 --prepare --embedding-provider mock --require-vector --chat
