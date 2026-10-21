.DEFAULT_GOAL := help

.PHONY: help up down logs psql migrate info validate test lint fmt check

help:
	@printf '%s\n' \
		'up        Start PostgreSQL' \
		'down      Stop Compose services' \
		'logs      Follow PostgreSQL logs' \
		'psql      Open PostgreSQL shell' \
		'migrate   Apply pending Flyway migrations' \
		'info      Show Flyway migration history' \
		'validate  Validate applied migrations' \
		'test      Run pytest' \
		'lint      Run Ruff checks' \
		'fmt       Format Python files' \
		'check     Run lint and tests'

up:
	docker compose up -d --wait db

down:
	docker compose down

logs:
	docker compose logs -f db

psql: up
	docker compose exec db psql -U cashflow -d cashflow

migrate: up
	docker compose run --rm flyway migrate

info: up
	docker compose run --rm flyway info

validate: up
	docker compose run --rm flyway validate

test:
	uv run --env-file .env pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

check: lint test
