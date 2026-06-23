# Contributing to surreal-basics

Thanks for your interest in improving surreal-basics! This guide covers the
local setup and the checks your change needs to pass.

## Prerequisites

- Python 3.11+ (the repo pins 3.13 via `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- Docker (only for the integration test suite)

## Setup

```bash
git clone https://github.com/lfnovo/surreal-basics
cd surreal-basics
make install            # uv sync --all-extras
uv run pre-commit install   # optional but recommended
```

## Running tests

The integration suite starts and stops a SurrealDB container automatically via
`docker compose`, so the plain command runs everything:

```bash
make test               # full suite (unit + integration)
make test-unit          # no database required
make test-integration   # integration only
```

If you already have a SurrealDB instance you'd rather use, point the tests at it
and skip the Docker management:

```bash
SBL_TEST_DOCKER=0 TEST_SURREAL_HOST=localhost TEST_SURREAL_PORT=8000 uv run pytest
```

## Quality checks

CI runs the same checks; run them locally before opening a PR:

```bash
make check              # ruff lint + mypy + format check
make format             # apply formatting
```

## Pull requests

- Branch off `main` and open a PR; do not push directly to `main`.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit
  messages and the PR title (e.g. `fix:`, `feat:`, `docs:`, `chore:`).
- Keep changes focused and include tests for new behavior.
- Update `CHANGELOG.md` under an `Unreleased` heading when your change is
  user-facing.
