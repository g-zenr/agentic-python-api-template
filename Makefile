.PHONY: install dev worker migrate deploy-db test test-cov test-integration lint typecheck fmt docs-check security feature feature-check remove-feature create-admin mcp-key loadtest up down

install:
	uv sync
	uv run prisma generate

dev:
	uv run uvicorn app.main:app --reload

worker:
	uv run python -m app.worker

migrate:
	uv run prisma migrate dev --name $(or $(name),change)

deploy-db:
	uv run prisma migrate deploy

test:
	uv run pytest

test-speed:
	uv run pytest -m speed

test-slo:
	uv run pytest -m speed -o addopts=""

test-cov:
	uv run pytest --cov=app --cov-fail-under=80

test-integration:
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -m integration -o addopts=""

typecheck:
	uv run mypy app

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy app
	uv run python scripts/check_feature.py

fmt:
	uv run ruff check --fix .
	uv run ruff format .

docs-check:
	uv run pytest tests/test_docs.py tests/test_lifecycle.py

security:
	uv run pip-audit
	uv run bandit -r app -ll

feature:
	uv run python scripts/new_feature.py $(name)

feature-check:
	uv run python scripts/check_feature.py $(name)

remove-feature:
	uv run python scripts/remove_feature.py $(name) --reason "$(reason)" --drop-data $(drop_data)

create-admin:
	uv run python scripts/create_admin.py --email $(email) $(if $(promote),--promote,)

mcp-key:
	uv run python scripts/mcp_key.py $(name) $(if $(tools),--tools $(tools),)

loadtest:
	k6 run loadtest/smoke.js

up:
	docker compose up -d db redis

down:
	docker compose down