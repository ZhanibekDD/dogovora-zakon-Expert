.PHONY: install test lint typecheck run-bot run-api run-worker migrate template backup up down logs

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

typecheck:
	mypy app scripts

migrate:
	alembic upgrade head

template:
	python scripts/build_master_template.py

run-bot:
	python -m app.bot.main

run-api:
	uvicorn app.api.main:app --reload

run-worker:
	python -m app.worker

backup:
	python scripts/backup_db.py

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f
