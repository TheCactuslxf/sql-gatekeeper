VENV := /Users/wan/code/python/sql-gatekeeper/.venv/bin

.PHONY: up down bootstrap-dev test test-docker

up:
	docker compose up -d

down:
	docker compose down -v

bootstrap-dev:
	$(VENV)/python -m sql_gatekeeper.bootstrap.meta

test:
	RUN_DOCKER_TESTS=1 $(VENV)/pytest tests

test-docker:
	RUN_DOCKER_TESTS=1 $(VENV)/pytest tests
