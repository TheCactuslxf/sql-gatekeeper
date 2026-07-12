PYTHON ?= python
PYTEST ?= pytest

.PHONY: up down bootstrap-dev test test-docker

up:
	docker compose up -d

down:
	docker compose down -v

bootstrap-dev:
	$(PYTHON) -m sql_gatekeeper.bootstrap.meta

test:
	$(PYTEST) tests

test-docker:
	RUN_DOCKER_TESTS=1 $(PYTEST) tests
