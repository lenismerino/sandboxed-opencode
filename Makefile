CONFIG_FILE ?= $(if $(wildcard ./.env),.env,.env.example)

ifneq (,$(wildcard $(CONFIG_FILE)))
    include $(CONFIG_FILE)
    export
endif

.PHONY: setup validate check versions allowlist ports build run run-tui run-autonomous run-conductor run-restricted stop clean-cache logs nuke-all delete-project scan profiles test-model skills harness supervisor dashboard

setup:
	mkdir -p $(PROJECTS_ROOT_PATH) $(SHARED_SYSTEM_PATH) $(TEMP_PATH) logs

validate:
	@CONFIG_FILE=$(CONFIG_FILE) ./scripts/validate_config.sh

check:
	@CONFIG_FILE=$(CONFIG_FILE) ./scripts/security_check.sh

versions:
	@echo "Python base: $${PYTHON_BASE_IMAGE:-python:3.13.15-slim-bookworm}"
	@echo "uv image: $${UV_IMAGE:-ghcr.io/astral-sh/uv:0.12.13}"
	@echo "Node package: $${NODE_VERSION:-22.23.2-1nodesource1}"
	@echo "OpenCode: $${OPENCODE_VERSION:-1.18.30}"
	@echo "GitHub CLI: $${GH_VERSION:-2.100.0}"
	@echo "Ollama image tag: $${OLLAMA_IMAGE_TAG:-0.34.0}"
	@echo "Active Model Profile: $${MODEL_PROFILE:-gemma-4-e4b}"

quickstart:
	@python3 scripts/quickstart.py

profiles:
	@python3 scripts/model_profile.py list

test-model:
	@python3 scripts/model_profile.py test $${MODEL_PROFILE:-gemma-4-e4b} --host $${LLM_HOST:-192.168.1.3} --port $${LLM_PORT:-1234}

skills:
	@python3 scripts/skills_manager.py list

harness:
	@python3 scripts/run_harness.py --profile $${MODEL_PROFILE:-gemma-4-e4b} --task "$${TASK:-Verify repository structure and run security checks}"

supervisor:
	@python3 scripts/run_supervisor.py --profile $${MODEL_PROFILE:-gemma-4-e4b} --host $${LLM_HOST:-192.168.1.3} --port $${LLM_PORT:-1234} $${TASK_FILE:+--task-file $$TASK_FILE} $${TASK:+--task "$$TASK"}

dashboard:
	@python3 scripts/dashboard.py
	@echo "Dashboard generated at /tmp/dashboard-public/index.html"

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
		if ! curl -s http://$${LLM_HOST:-localhost}:$${LLM_PORT:-1234}/v1/models | grep -q "$(LM_STUDIO_MODEL)"; then \
			echo "WARNING: Could not detect $(LM_STUDIO_MODEL) via LM Studio at $${LLM_HOST:-localhost}:$${LLM_PORT:-1234}."; \
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
	WORKSPACE_NETWORK=agent_network_restricted ACTIVE_PROJECT=$(PROJECT_NAME) docker compose up -d --build
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
