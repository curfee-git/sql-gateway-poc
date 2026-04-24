# MIT License
#
# Copyright (c) 2026 Philipp Höllinger
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

.DEFAULT_GOAL := help
.PHONY: help setup run test test-integration fmt lint typecheck gate clean compose-up compose-down

VENV_BIN := .venv/bin

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[1;36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Copy .env.example to .env (if missing) and install dev dependencies
	@test -f .env || cp .env.example .env
	$(VENV_BIN)/pip install -e ".[dev]"

run: ## Start the gateway locally via uvicorn
	$(VENV_BIN)/uvicorn main:app --host 0.0.0.0 --port 8080 --reload

test: ## Run unit tests
	$(VENV_BIN)/pytest

test-integration: ## Run integration tests (needs Docker)
	$(VENV_BIN)/pytest -m integration

fmt: ## Format with ruff
	$(VENV_BIN)/ruff format .

lint: ## Lint with ruff
	$(VENV_BIN)/ruff check .

typecheck: ## Type-check with mypy
	$(VENV_BIN)/mypy .

gate: lint typecheck test ## Full quality gate: lint + mypy + unit tests

compose-up: ## Start the full stack (postgres + gateway) via docker compose
	docker compose up --build

compose-down: ## Stop the docker compose stack
	docker compose down

clean: ## Remove caches and compiled bytecode
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
	rm -rf .mypy_cache .ruff_cache .pytest_cache
