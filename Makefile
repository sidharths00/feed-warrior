.PHONY: install db-up db-down migrate test test-unit test-integration dev-digest deploy

install:
	pip install -e ".[dev]"

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	feed-warrior db migrate

test: test-unit

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

dev-digest:
	feed-warrior digest --dry-run

deploy:
	vercel deploy --prod
