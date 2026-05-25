ifneq (,$(wildcard ./.env))
    include .env
    export
endif

.PHONY: setup validate check versions allowlist ports build run run-tui run-autonomous run-conductor run-restricted stop clean-cache logs nuke-all delete-project scan

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
	@echo "OpenCode: $${OPENCODE_VERSION:-1.15.10}"
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
		if ! curl -s http://localhost:$${LLM_PORT:-52625}/v1/models | grep -q "$(FASTFLOW_MODEL)"; then \
			echo "WARNING: Could not detect $(FASTFLOW_MODEL) via FastFlowLM. Ensure 'flm serve $(FASTFLOW_MODEL)' is running."; \
		fi; \
	else \
		echo "Error: Invalid LLM_SOURCE '$(LLM_SOURCE)' in .env"; exit 1; \
	fi

run-tui: validate setup
	@if [ -z "$(PROJECT_NAME)" ]; then echo "Error: PROJECT_NAME is not set in .env."; exit 1; fi
	@./new_project.sh
	ACTIVE_PROJECT=$(PROJECT_NAME) OPENCODE_INTERFACE=tui docker compose run --rm -it workspace

run-conductor: validate setup
	@if [ -z "$(PROJECT_NAME)" ]; then echo "Error: PROJECT_NAME is not set in .env."; exit 1; fi
	@./new_project.sh
	@echo "Starting conductor mode. Connect your AI coding agent to: http://localhost:$${MCP_BRIDGE_PORT:-8443}/mcp"
	ACTIVE_PROJECT=$(PROJECT_NAME) OPERATION_MODE=conductor docker compose up -d --build workspace
	@echo "Conductor is running. Use 'make logs' to follow output."

run-autonomous: validate setup
	@if [ -z "$(PROJECT_NAME)" ]; then echo "Error: PROJECT_NAME is not set in .env."; exit 1; fi
	@if [ -z "$(TASK_FILE)" ]; then echo "Error: TASK_FILE is not set in .env."; exit 1; fi
	@./new_project.sh
	ACTIVE_PROJECT=$(PROJECT_NAME) OPERATION_MODE=autonomous docker compose run --rm workspace

run-restricted: validate setup
	@if [ -z "$(PROJECT_NAME)" ]; then echo "Error: PROJECT_NAME is not set in .env."; exit 1; fi
	@./new_project.sh
	@echo "Starting in restricted network mode (no internet egress)..."
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose up -d --build
	@docker network disconnect sandboxed-opencode_agent_network opencode-workspace 2>/dev/null || true
	@docker network connect sandboxed-opencode_agent_network_restricted opencode-workspace 2>/dev/null || true
	@echo "Workspace is on the restricted (internal) network."

stop:
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose --profile local-llm down

clean-cache:
	rm -rf $(TEMP_PATH)/*

delete-project: validate stop
	rm -rf $(PROJECTS_ROOT_PATH)/$(PROJECT_NAME)

logs:
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose --profile local-llm logs -f

scan: build
	@echo "Scanning workspace image for vulnerabilities..."
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
	  aquasec/trivy:latest image opencode-workspace:latest \
	  --severity HIGH,CRITICAL --exit-code 1

nuke-all: stop clean-cache delete-project
	ACTIVE_PROJECT=$(PROJECT_NAME) docker compose --profile local-llm down -v --rmi all
