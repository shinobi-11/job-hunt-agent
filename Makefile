.PHONY: help install test lint format check clean run docker-build docker-run

help:
	@echo "Job Hunt Agent - Available Commands:"
	@echo ""
	@echo "  make install        Install all dependencies (prod + dev)"
	@echo "  make run            Run the agent"
	@echo "  make test           Run all tests"
	@echo "  make test-unit      Run unit tests only"
	@echo "  make lint           Check code style (ruff, black)"
	@echo "  make format         Auto-format code (black)"
	@echo "  make check          Run all quality checks"
	@echo "  make clean          Remove build artifacts"
	@echo "  make docker-build   Build production Docker image"
	@echo "  make docker-run     Run in Docker"

install:
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install -e ".[dev]"
	playwright install chromium
	pre-commit install

run:
	python agent.py

test:
	pytest -v

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v -m integration

test-cov:
	pytest --cov=. --cov-report=html --cov-report=term-missing

lint:
	ruff check .
	black --check --diff .

format:
	black .
	ruff check --fix .

check: lint
	mypy . --ignore-missing-imports
	pip-audit -r requirements.txt

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build:
	docker build --target production -t job-hunt-agent:latest .

docker-run:
	docker run --env-file .env -v $(PWD)/data:/app/data -it job-hunt-agent:latest
