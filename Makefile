.PHONY: install init demo test lint typecheck check serve clean

install:
	uv sync --all-extras --group dev

init:
	uv run workflow-ai init

demo:
	bash scripts/demo.sh

test:
	uv run pytest --cov=workflow_ai --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src

check: lint typecheck test

serve:
	uv run workflow-ai serve --host 0.0.0.0 --port 8080

clean:
	rm -rf .workflow-ai .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
