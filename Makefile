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

test-integration: ## Run only the integration tests
	uv run pytest -m integration

lint: ## Lint with ruff
	uv run ruff check surreal_basics tests

format: ## Format with ruff
	uv run ruff format surreal_basics tests

typecheck: ## Static type-check with mypy
	uv run mypy surreal_basics

check: lint typecheck ## Run lint + typecheck, then format-check
	uv run ruff format --check surreal_basics tests

db-up: ## Start the local SurrealDB container
	docker compose up -d --wait

db-down: ## Stop and remove the local SurrealDB container
	docker compose down -v

bench: ## Run the benchmark
	uv run python benchmark_library.py
