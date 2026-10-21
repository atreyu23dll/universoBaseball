# Comandos reproducibles. `make help` los lista.
SHELL := /bin/bash
PY ?= .venv/bin/python
PYTHONPATH := .:backend
export PYTHONPATH

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Muestra esta ayuda
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Instalación ---------------------------------------------------------- #

.PHONY: install
install:  ## Crea el entorno virtual e instala las dependencias
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements-dev.txt

.PHONY: freeze
freeze:  ## Regenera requirements.txt con las versiones instaladas
	@$(PY) -m pip freeze | grep -iE '^(fastapi|uvicorn|sqlalchemy|alembic|pydantic|pydantic-settings|psycopg)=='

# --- Base de datos -------------------------------------------------------- #

.PHONY: migrate
migrate:  ## Aplica las migraciones a la base configurada
	cd backend && ../$(PY) -m alembic upgrade head

.PHONY: migrate-down
migrate-down:  ## Revierte la última migración
	cd backend && ../$(PY) -m alembic downgrade -1

.PHONY: revision
revision:  ## Crea una migración nueva: make revision m="mensaje"
	cd backend && ../$(PY) -m alembic revision --autogenerate -m "$(m)"

.PHONY: reset-db
reset-db:  ## Borra la base SQLite local (pide confirmación)
	@read -p "¿Borrar data/baseball.db? [s/N] " ok; [ "$$ok" = "s" ] && rm -f data/baseball.db* && echo borrada || echo cancelado

# --- Ejecución local (sin Docker) ----------------------------------------- #

.PHONY: run-api
run-api: migrate  ## Arranca la API en 127.0.0.1:8000 sobre SQLite
	$(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

.PHONY: run-frontend
run-frontend:  ## Arranca el frontend en 127.0.0.1:5173 (necesita Node)
	cd frontend && npm run dev

.PHONY: seed-demo
seed-demo:  ## Crea un universo de demostración con una temporada simulada
	$(PY) scripts/seed_demo.py

# --- Docker --------------------------------------------------------------- #

.PHONY: up
up:  ## Levanta Postgres, API y frontend con docker compose
	docker compose up --build

.PHONY: down
down:  ## Para los contenedores (conserva el volumen de datos)
	docker compose down

.PHONY: nuke
nuke:  ## Para los contenedores y BORRA el volumen de Postgres
	docker compose down -v

# --- Calidad -------------------------------------------------------------- #

.PHONY: test
test:  ## Pruebas rápidas (excluye rendimiento)
	$(PY) -m pytest -m "not slow"

.PHONY: test-all
test-all:  ## Todas las pruebas, incluidas las de rendimiento
	$(PY) -m pytest -s

.PHONY: test-postgres
test-postgres:  ## Las pruebas del backend contra PostgreSQL en Docker
	# Base APARTE de la de desarrollo: la batería limpia el esquema al empezar,
	# y eso no puede llevarse por delante los universos del usuario.
	docker compose up -d db
	@until docker compose exec -T db pg_isready -U baseball -d baseball_universe >/dev/null 2>&1; do sleep 1; done
	@docker compose exec -T db psql -U baseball -d baseball_universe -tc \
	  "SELECT 1 FROM pg_database WHERE datname='baseball_universe_test'" | grep -q 1 || \
	  docker compose exec -T db createdb -U baseball baseball_universe_test
	BU_DATABASE_URL=postgresql+psycopg://baseball:$${BU_DB_PASSWORD:-baseball_local}@127.0.0.1:5433/baseball_universe_test \
	  $(PY) -m pytest backend/tests -m "not slow"

.PHONY: lint
lint:  ## Linter y formato
	$(PY) -m ruff check backend simulation scripts
	$(PY) -m ruff format --check backend simulation scripts

.PHONY: format
format:  ## Aplica el formato
	$(PY) -m ruff format backend simulation scripts
	$(PY) -m ruff check --fix backend simulation scripts

.PHONY: check-frontend
check-frontend:  ## Tipado del frontend (necesita Node)
	cd frontend && npm run check

.PHONY: build-frontend
build-frontend:  ## Compila el frontend (necesita Node)
	cd frontend && npm run build

.PHONY: calibrate
calibrate:  ## Mide el comportamiento estadístico del motor
	$(PY) scripts/calibrate.py --seasons 2

.PHONY: smoke-stack
smoke-stack:  ## Comprueba el stack por el camino del navegador (necesita docker compose up)
	./scripts/smoke_stack.sh

.PHONY: verify
verify: lint test calibrate  ## Todo lo que debe pasar antes de dar algo por hecho
