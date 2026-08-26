# ==============================================================================
# Makefile para bio-agent (ADK 2.0 & Cloud Run)
# ==============================================================================

.PHONY: help install run test-remote playground server eval deploy dashboard lint test sessions-demo clean

export PATH := /Users/jburmester/Downloads/google-cloud-sdk/bin:$(HOME)/.local/bin:$(HOME)/.cargo/bin:$(PATH)

PROJECT_ID ?= gke-service-project-081292
REGION ?= us-central1
EVALSET ?= tests/eval/evalsets/biography.evalset.json
EVAL_CONFIG ?= tests/eval/eval_config.json
CLOUD_RUN_URL ?= https://biography-agent-938422762731.us-central1.run.app



help: ## Muestra este menú de ayuda
	@echo "Operaciones disponibles para bio-agent:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Instala dependencias del proyecto usando uv
	uv sync --index-url https://pypi.org/simple
	uv pip install "google-adk[eval]" --index-url https://pypi.org/simple

run: ## Ejecuta una prueba rápida del agente local (ej: make run PROMPT="Genera una biografía de Ada Lovelace")
	@PROMPT="$(PROMPT)"; \
	if [ -z "$$PROMPT" ]; then PROMPT="Genera una biografía de Ada Lovelace"; fi; \
	agents-cli run "$$PROMPT"

test-remote: ## Pruebas en el agente remoto desplegado en Cloud Run (ej: make test-remote PROMPT="...")
	@PROMPT="$(PROMPT)"; \
	if [ -z "$$PROMPT" ]; then PROMPT="Genera una biografía breve de Rosalind Franklin"; fi; \
	TOKEN=$$(gcloud auth print-identity-token 2>/dev/null); \
	if [ -n "$$TOKEN" ]; then \
		agents-cli run --url $(CLOUD_RUN_URL) --mode adk -H "Authorization: Bearer $$TOKEN" "$$PROMPT"; \
	else \
		agents-cli run --url $(CLOUD_RUN_URL) --mode adk "$$PROMPT"; \
	fi


playground: ## Inicia el ADK Web Playground interactivo
	agents-cli playground

server: ## Inicia el servidor FastAPI local con auto-reload en http://localhost:8000
	uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000 --reload

eval: ## Ejecuta el set de pruebas de evaluación con juez LLM (evalset)
	uv run python -m google.adk.cli eval app $(EVALSET) --config_file_path $(EVAL_CONFIG)

deploy: ## Despliega el agente en Agent Engine (Agent Runtime)
	agents-cli deploy --deployment-target agent_runtime --project $(PROJECT_ID) --region $(REGION) --no-confirm-project

publish-gemini-enterprise: ## Registra el agente en Gemini Enterprise
	agents-cli publish gemini-enterprise \
		--registration-type adk \
		--gemini-enterprise-app-id projects/938422762731/locations/global/collections/default_collection/engines/generic-application_1750093244833 \
		--display-name "Biography Agent" \
		--description "Agente especializado en investigacion y redaccion de biografias profesionales a partir de nombres o documentos adjuntos combinados con Google Search."


lint: ## Ejecuta el linter (ruff) y verificación de código
	agents-cli lint

test: ## Ejecuta las pruebas unitarias e integración con pytest
	uv run pytest

sessions-demo: ## Ejecuta la demostración del servicio de sesiones (VertexAiSessionService)
	uv run python examples/manage_sessions.py

clean: ## Limpia archivos temporales, caché de python y builds
	rm -rf .venv __pycache__ app/__pycache__ .pytest_cache artifacts/
