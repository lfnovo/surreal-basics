.PHONY: help install test test-unit test-integration lint format typecheck check db-up db-down bench

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with dev dependencies
	uv sync --all-extras

test: ## Run the full test suite (starts SurrealDB via docker compose)
	uv run pytest

test-unit: ## Run only unit tests (no database required)
	uv run pytest -m "not integration"

test-integration: ## Run integration tests (SurrealDB v2; override SBL_TEST_SURREAL_VERSION)
	uv run pytest -m integration

test-integration-v3: ## Run integration tests against SurrealDB v3
	SBL_TEST_SURREAL_VERSION=v3 uv run pytest -m integration

lint: ## Lint with ruff
	uv run ruff check surreal_basics tests

format: ## Format with ruff
	uv run ruff format surreal_basics tests

typecheck: ## Static type-check with mypy
	uv run mypy surreal_basics

check: lint typecheck ## Run lint + typecheck, then format-check
	uv run ruff format --check surreal_basics tests

db-up: ## Start the local SurrealDB v2 container
	docker compose up -d --wait surrealdb-v2

db-up-v3: ## Start the local SurrealDB v3 container
	docker compose up -d --wait surrealdb-v3

db-down: ## Stop and remove the local SurrealDB containers
	docker compose down -v

bench: ## Run the benchmark
	uv run python benchmark_library.py
