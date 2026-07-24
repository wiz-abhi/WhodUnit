# Whodunit dev tasks. Run `just` to list.

default:
    @just --list

# Lint with ruff.
lint:
    uv run ruff check .

# Auto-fix lint + format.
fix:
    uv run ruff check --fix .
    uv run ruff format .

# Type-check src/ with mypy (strict).
type:
    uv run mypy

# Run the test suite.
test:
    uv run pytest -q

# Lint + type + test.
check: lint type test
