# Recipe: Google Gemma 4 E4B + LM Studio Quickstart

This recipe walks through configuring and running `sandboxed-opencode` with Google Gemma 4 E4B served via LM Studio on LAN or host.

## Prerequisites
1. **LM Studio**: Download and load `google/gemma-4-e4b` (Q4_K_M or higher).
2. **Server Configuration in LM Studio**:
   - Enable the Local Inference Server.
   - Context length: Set to **131,072** tokens.
   - Bind address: Bind to `0.0.0.0` or your LAN IP (e.g. `192.168.1.3`).
   - Port: `1234`.

---

## Step 1: Configure the Sandbox

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Ensure the following variables are configured in `.env`:

```bash
PROJECT_NAME=my_gemma_project
PROJECTS_ROOT_PATH=/Users/youruser/sandboxed-projects
SHARED_SYSTEM_PATH=/Users/youruser/read-only-shared
TEMP_PATH=/Users/youruser/sandbox-temp

# Flagship Model Profile
MODEL_PROFILE=gemma-4-e4b

# LM Studio Server Host (LAN IP or host.docker.internal)
LLM_HOST=192.168.1.3
LLM_PORT=1234
LLM_SOURCE=lm_studio
LM_STUDIO_MODEL=google/gemma-4-e4b

# Gemma 4 E4B Hyperparameters
TEMPERATURE=0.2
TOP_P=0.95
TOP_K=40
MAX_CONTEXT_LENGTH=131072
```

---

## Step 2: Validate the Connection

Run the model profile test CLI to verify connectivity, reasoning trace extraction, and native tool calling:

```bash
make test-model
```

You should see output similar to:
```
--- Running Live Profile Tests for 'Google Gemma 4 E4B (LM Studio)' ---
[1/4] Checking model visibility at http://192.168.1.3:1234/v1/models...
  ✓ Model 'google/gemma-4-e4b' found in available models list.
[2/4] Testing basic completion and reasoning...
  ✓ Response received in 3.38s
  ✓ Reasoning trace captured (433 chars, 77 tokens)
[3/4] Testing native function/tool calling...
  ✓ Tool call generated: check_service_status({"service_name":"mcp-bridge"})
[4/4] Testing structured JSON schema output...
  ✓ Structured JSON parsed successfully!
✓ Live test sequence completed.
```

---

## Step 3: Launch the Sandbox

### Interactive Web Mode (OpenCode Web UI)
```bash
make run
```
Navigate to `http://localhost:3000` to interact with Gemma 4 E4B inside the sandbox.

### Terminal UI Mode (OpenCode TUI)
```bash
make run-tui
```

### Autonomous Mode
```bash
make run-autonomous TASK_FILE=sample_project_prompt.md
```

### Conductor Mode (MCP Bridge)
```bash
make run-conductor
```
Connect your external AI coding agent (e.g. Antigravity, Claude Code) to `http://localhost:8443/mcp`.
