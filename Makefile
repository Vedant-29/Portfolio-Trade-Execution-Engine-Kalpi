.PHONY: install dev dev-backend dev-frontend dev-all test lint fmt up down logs shell build rebuild fernet-key

install:
	uv sync
	cd frontend && pnpm install

dev: dev-backend

dev-backend:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && pnpm dev

# Run backend + frontend in parallel (Ctrl-C stops both)
dev-all:
	@trap 'kill 0' INT; \
	(uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 &) ; \
	(cd frontend && pnpm dev) ; \
	wait

test:
	uv run pytest -v

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

build:
	docker compose build

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f app

shell:
	docker compose exec app /bin/bash

rebuild:
	docker compose down
	docker compose build --no-cache
	docker compose up -d

fernet-key:
	@uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
