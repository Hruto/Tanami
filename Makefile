.PHONY: install models test lint type check format contract run docker-test clean

PY := python

install:
	$(PY) -m pip install -e ".[dev]"

models:
	$(PY) scripts/make_stub_models.py --with-shadow

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

type:
	mypy

test: models
	pytest --cov=app --cov-report=term-missing

contract:
	$(PY) scripts/export_openapi.py --check

contract-write:
	$(PY) scripts/export_openapi.py --write

check: lint type contract test

run: models
	uvicorn app.asgi:app --reload --port 8001

docker-test:
	docker build --target test -t tanami-vision:test .
	docker run --rm tanami-vision:test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
