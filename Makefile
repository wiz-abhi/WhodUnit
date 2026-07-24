.PHONY: lint fix type test check

lint:
	uv run ruff check .

fix:
	uv run ruff check --fix .
	uv run ruff format .

type:
	uv run mypy

test:
	uv run pytest -q

check: lint type test
