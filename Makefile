SHELL := powershell

.DEFAULT_GOAL := help

GREEN := "\e[32m"
YELLOW := "\e[33m"
BLUE := "\e[34m"
RESET := "\e[0m"

help:
	@echo "${BLUE}Aries OS - comandos disponibles${RESET}"
	@echo "  make install     -> Instala dependencias de desarrollo"
	@echo "  make dev         -> Inicia la API con hot reload"
	@echo "  make test        -> Ejecuta pruebas con cobertura"
	@echo "  make lint        -> Revisa estilo con ruff"
	@echo "  make format      -> Formatea con black e isort"
	@echo "  make type-check  -> Comprueba tipos con mypy"
	@echo "  make clean       -> Elimina archivos temporales"
	@echo "  make docs        -> Sirve la documentación con mkdocs"

install:
	@echo "Instalando dependencias de desarrollo..."
	@python -m pip install --upgrade pip
	@python -m pip install -e .[dev,voice,desktop,docs]

dev:
	@echo "Iniciando Aries API en modo desarrollo..."
	@uvicorn aries.api:app --reload --host 0.0.0.0 --port 8000

test:
	@echo "Ejecutando pruebas con cobertura..."
	@python -m pytest --cov=src/aries --cov-report=term

lint:
	@echo "Ejecución de ruff..."
	@ruff check src tests

format:
	@echo "Formateando código con black e isort..."
	@black src tests
	@isort src tests

type-check:
	@echo "Verificando tipos con mypy..."
	@mypy src tests

clean:
	@echo "Limpiando archivos temporales y caches..."
	@Remove-Item -Recurse -Force .mypy_cache, .pytest_cache, htmlcov, dist, build, __pycache__ -ErrorAction SilentlyContinue

docs:
	@echo "Sirviendo documentación con mkdocs..."
	@mkdocs serve
