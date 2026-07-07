# Corveon — developer convenience targets. See docs/SETUP.md for details.
.DEFAULT_GOAL := help
.PHONY: help up down backend-install backend-check frontend-install frontend-check check

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

up: ## Start local services (Postgres+pgvector, Redis, Ollama)
	docker compose -f infra/docker-compose.yml up -d

down: ## Stop local services
	docker compose -f infra/docker-compose.yml down

backend-install: ## Install backend (editable, dev extras)
	cd backend && pip install -e ".[dev]"

backend-check: ## Backend quality gate
	cd backend && ruff check . && ruff format --check . && mypy app && pytest && bandit -q -r app && pip-audit

frontend-install: ## Install frontend deps
	cd frontend && pnpm install

frontend-check: ## Frontend quality gate
	cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build

check: backend-check frontend-check ## Run all quality gates
