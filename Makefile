.PHONY: sync test test-fast demo deploy run clean

sync:
	uv sync --extra dev

test:
	uv run pytest -v

test-fast:
	uv run pytest --tb=no -q

demo:
	bash scripts/demo.sh

deploy:
	bash scripts/deploy.sh

run:
	uv run adk web

clean:
	rm -rf dist/ .pytest_cache/ reports/*.md
	find . -type d -name __pycache__ -exec rm -rf {} +
