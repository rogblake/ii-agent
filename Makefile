.DEFAULT_GOAL := help

# ── Paths ───────────────────────────────────────────────────────
COMPOSE_FILE       := docker/docker-compose.stack.yaml
COMPOSE_DEV_FILE   := docker/docker-compose.dev.yaml
STACK_ENV          := docker/.stack.env
STACK_ENV_EXAMPLE  := docker/.stack.env.example
PROJECT_NAME       ?= ii-agent-stack
DEV_PROJECT_NAME   ?= ii-agent-dev

# ── Compose shorthand ──────────────────────────────────────────
DC     := docker compose --project-name $(PROJECT_NAME) --env-file $(STACK_ENV) -f $(COMPOSE_FILE)
DC_DEV := docker compose --project-name $(DEV_PROJECT_NAME) -f $(COMPOSE_DEV_FILE)

# ══════════════════════════════════════════════════════════════
#  Quick-start (single commands)
# ══════════════════════════════════════════════════════════════

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Setup (first-time) ────────────────────────────────────────

.PHONY: setup
setup: _ensure-env _ensure-frontend-env install ## First-time setup: env files + install deps
	@echo ""
	@echo "✓ Setup complete!"
	@echo "  Edit .env to add your LLM API keys, then run: make dev-all"

# ── Install ─────────────────────────────────────────────────────

.PHONY: install
install: ## Install backend + frontend deps
	uv sync --frozen
	cd frontend && npm install

.PHONY: install-backend
install-backend: ## Install backend deps only
	uv sync --frozen

.PHONY: install-frontend
install-frontend: ## Install frontend deps only
	cd frontend && npm install

# ── Infrastructure (Docker) ────────────────────────────────────

.PHONY: infra
infra: ## Start Postgres + Redis + MinIO (docker, no env file needed)
	$(DC_DEV) up -d
	@echo "\n✓ Postgres :5432 | Redis :6379 | MinIO :9000 (console :9001)"

.PHONY: infra-stop
infra-stop: ## Stop infrastructure containers
	$(DC_DEV) stop

.PHONY: infra-down
infra-down: ## Stop + remove infrastructure containers and volumes
	$(DC_DEV) down -v --remove-orphans

.PHONY: infra-wait
infra-wait: ## Wait for Postgres + Redis + MinIO to be healthy
	@echo "Waiting for infrastructure to be healthy..."
	@for i in $$(seq 1 30); do \
		if $(DC_DEV) exec -T postgres pg_isready -U postgres -d ii_agent >/dev/null 2>&1 && \
		   $(DC_DEV) exec -T redis redis-cli ping >/dev/null 2>&1; then \
			echo "✓ Infrastructure is healthy"; \
			exit 0; \
		fi; \
		printf "."; \
		sleep 1; \
	done; \
	echo "\n✗ Infrastructure did not become healthy in 30s"; \
	exit 1

# ── Backend ─────────────────────────────────────────────────────

.PHONY: backend-dev
backend-dev: ## Run backend (uvicorn, reload, port 8000)
	uv run python -m ii_agent.ws_server --reload --port 8000

.PHONY: backend-prod
backend-prod: ## Run backend (gunicorn + uvicorn, port 8000)
	uv run gunicorn ii_agent.ws_server:app \
		-k uvicorn.workers.UvicornWorker \
		--bind 0.0.0.0:8000 \
		--workers 1 \
		--timeout 360

# ── Frontend ────────────────────────────────────────────────────

.PHONY: frontend-dev
frontend-dev: ## Run frontend dev server (vite, port 5173)
	cd frontend && npm run dev

.PHONY: frontend-build
frontend-build: ## Build frontend for production
	cd frontend && npm run build

.PHONY: frontend-preview
frontend-preview: ## Preview production frontend build
	cd frontend && npm run preview

# ── Full Stack (Docker) ────────────────────────────────────────

.PHONY: stack
stack: _ensure-stack-env ## Start full stack via docker compose
	./scripts/run_stack.sh

.PHONY: stack-build
stack-build: _ensure-stack-env ## Start full stack with --build
	./scripts/run_stack.sh --build

.PHONY: stack-down
stack-down: ## Stop full stack and clean up
	$(DC) down --remove-orphans

.PHONY: stack-logs
stack-logs: ## Tail all stack logs
	$(DC) logs -f

# ── Dev (local backend + frontend against docker infra) ────────

.PHONY: dev
dev: ## Start infra, then backend + frontend locally (needs tmux or 2 terminals)
	@echo "Starting infrastructure..."
	@$(MAKE) infra
	@echo ""
	@echo "Infrastructure ready. Now run in separate terminals:"
	@echo "  make backend-dev"
	@echo "  make frontend-dev"
	@echo ""
	@echo "Or run everything in one command:"
	@echo "  make dev-all"

.PHONY: dev-all
dev-all: _preflight _ensure-env _ensure-frontend-env ## One command to start everything (infra + backend + frontend)
	@echo ""
	@echo "══════════════════════════════════════════════════"
	@echo "  II-Agent Development Server"
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@echo "Starting infrastructure (Postgres, Redis, MinIO)..."
	@$(MAKE) infra
	@$(MAKE) infra-wait
	@echo ""
	@echo "Starting backend + frontend..."
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:1420"
	@echo "  MinIO:    http://localhost:9001 (minioadmin/minioadmin)"
	@echo ""
	@echo "Press Ctrl+C to stop all services."
	@echo "══════════════════════════════════════════════════"
	@echo ""
	@cd frontend && npx --yes concurrently \
		--kill-others \
		--names "backend,frontend" \
		--prefix "[{name}]" \
		--prefix-colors "cyan,green" \
		"cd .. && uv run python -m ii_agent.ws_server --reload --port 8000" \
		"npm run dev"

# ── Database ────────────────────────────────────────────────────

.PHONY: db-migrate
db-migrate: ## Run alembic migrations
	uv run alembic upgrade head

.PHONY: db-revision
db-revision: ## Create new alembic revision (usage: make db-revision msg="description")
	uv run alembic revision --autogenerate -m "$(msg)"

.PHONY: db-downgrade
db-downgrade: ## Downgrade one alembic revision
	uv run alembic downgrade -1

.PHONY: db-history
db-history: ## Show alembic migration history
	uv run alembic history --verbose

# ── Lint & Format ──────────────────────────────────────────────

.PHONY: format
format: ## Auto-format backend + frontend
	uv run ruff check --fix-only src
	uv run ruff format src
	cd frontend && npx prettier --write .

.PHONY: lint
lint: ## Lint backend + frontend
	uv run ruff check src
	uv run ruff format --check src
	cd frontend && npm run lint

.PHONY: format-backend
format-backend: ## Auto-format backend only
	uv run ruff check --fix-only src
	uv run ruff format src

.PHONY: lint-backend
lint-backend: ## Lint backend only
	uv run ruff check src
	uv run ruff format --check src

# ── Test ────────────────────────────────────────────────────────

.PHONY: test
test: ## Run all tests
	uv run pytest src/tests/ -v

.PHONY: test-unit
test-unit: ## Run unit tests only
	uv run pytest src/tests/unit/ -v

.PHONY: test-smoke
test-smoke: ## Run smoke tests only
	uv run pytest src/tests/smoke/ -v

.PHONY: test-cov
test-cov: ## Run tests with coverage
	uv run pytest src/tests/ --cov=src --cov-report=term-missing

# ── Utilities ───────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache dist build *.egg-info
	rm -rf frontend/node_modules/.vite frontend/dist

.PHONY: check
check: lint test-unit ## Lint + unit tests (pre-commit check)

# ── Internal targets ───────────────────────────────────────────

.PHONY: _preflight
_preflight:
	@missing=""; \
	command -v docker >/dev/null 2>&1 || missing="$$missing docker"; \
	command -v uv >/dev/null 2>&1     || missing="$$missing uv"; \
	command -v node >/dev/null 2>&1   || missing="$$missing node"; \
	command -v npm >/dev/null 2>&1    || missing="$$missing npm"; \
	if [ -n "$$missing" ]; then \
		echo "✗ Missing required tools:$$missing"; \
		echo ""; \
		echo "Install them:"; \
		echo "  docker  — https://docs.docker.com/get-docker/"; \
		echo "  uv      — curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo "  node    — https://nodejs.org/ (or use nvm)"; \
		echo ""; \
		exit 1; \
	fi; \
	if ! docker info >/dev/null 2>&1; then \
		echo "✗ Docker daemon is not running. Please start Docker Desktop."; \
		exit 1; \
	fi; \
	echo "✓ All prerequisites found (docker, uv, node, npm)"

.PHONY: _ensure-env
_ensure-env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
		echo "  → Edit .env to add your LLM API keys before starting."; \
	fi

.PHONY: _ensure-frontend-env
_ensure-frontend-env:
	@if [ ! -f frontend/.env ]; then \
		cp frontend/.env.example frontend/.env; \
		echo "Created frontend/.env from frontend/.env.example"; \
	fi

.PHONY: _ensure-stack-env
_ensure-stack-env:
	@if [ ! -f $(STACK_ENV) ]; then \
		cp $(STACK_ENV_EXAMPLE) $(STACK_ENV); \
		echo "Created $(STACK_ENV) from template — edit it with real credentials."; \
	fi
