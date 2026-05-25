ifneq (,$(wildcard ./.env))
    include .env
    export
endif

.PHONY: setup validate check versions allowlist ports build run stop clean-cache logs nuke-all delete-project

setup:
	mkdir -p $(PROJECTS_ROOT_PATH) $(SHARED_SYSTEM_PATH) $(TEMP_PATH) logs

validate:
	@./scripts/validate_config.sh

check:
	@./scripts/security_check.sh

versions:
	@echo "Python base: $${PYTHON_BASE_IMAGE:-python:3.13.13-slim-bookworm}"
	@echo "uv image: $${UV_IMAGE:-ghcr.io/astral-sh/uv:0.11.16}"
	@echo "Node package: $${NODE_VERSION:-22.22.2-1nodesource1}"
	@echo "OpenCode: $${OPENCODE_VERSION:-0.6.6}"
	@echo "GitHub CLI: $${GH_VERSION:-2.92.0}"
	@echo "Ollama image tag: $${OLLAMA_IMAGE_TAG:-0.23.1}"

allowlist:
	@grep -Ev '^(#|$$)' config/apt-package-allowlist.txt

ports:
	@grep -Ev '^(#|$$)' config/port-allowlist.txt

build: validate
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose build workspace

run: validate setup
	@if [ -z "$(PROJECT_NAME)" ]; then echo "Error: PROJECT_NAME is not set in .env."; exit 1; fi
	@./new_project.sh
	@if [ "$(LLM_SOURCE)" = "ollama_docker" ]; then \
		ACTIVE_PROJECT=$(PROJECT_NAME) docker compose --profile local-llm up -d --build; \
		while ! docker exec opencode-llm ollama list > /dev/null 2>&1; do sleep 2; done; \
		if ! docker exec opencode-llm ollama list | grep -q "$(OLLAMA_MODEL)"; then \
			docker exec opencode-llm ollama pull $(OLLAMA_MODEL); \
		fi; \
	elif [ "$(LLM_SOURCE)" = "lm_studio" ]; then \
		ACTIVE_PROJECT=$(PROJECT_NAME) docker compose up -d --build; \
		if ! curl -s http://localhost:$${LLM_PORT:-1234}/v1/models | grep -q "$(LM_STUDIO_MODEL)"; then \
			echo "WARNING: Could not detect $(LM_STUDIO_MODEL) via LM Studio."; \
		fi; \
	elif [ "$(LLM_SOURCE)" = "fastflow_amd" ]; then \
		ACTIVE_PROJECT=$(PROJECT_NAME) docker compose up -d --build; \
		if ! curl -s http://localhost:52625/v1/models | grep -q "$(FASTFLOW_MODEL)"; then \
			echo "WARNING: Could not detect $(FASTFLOW_MODEL) via FastFlowLM. Ensure 'flm serve $(FASTFLOW_MODEL)' is running."; \
		fi; \
	else \
		echo "Error: Invalid LLM_SOURCE '$(LLM_SOURCE)' in .env"; exit 1; \
	fi

stop:
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose --profile local-llm down

clean-cache:
	rm -rf $(TEMP_PATH)/*

delete-project: validate stop
	rm -rf $(PROJECTS_ROOT_PATH)/$(PROJECT_NAME)

logs:
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose --profile local-llm logs -f

nuke-all: stop clean-cache delete-project
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose --profile local-llm down -v --rmi all
