# xl-sandboxed-opencode

`xl-sandboxed-opencode` runs OpenCode inside a constrained Docker workspace and routes it to a local OpenAI-compatible model server, typically LM Studio on the host. The goal is a local, private coding agent with a smaller blast radius than installing agent tooling directly on the host.

## Security Model

The container is designed around these boundaries:

- OpenCode runs as a non-root `agent` user whose UID/GID match the host user.
- Configuration validation rejects UID/GID `0` so the workspace service is not launched as root.
- Only one project directory is mounted read/write at `/home/agent/projects`.
- Optional shared host material is mounted read-only at `/home/agent/shared`.
- Caches and temporary files are isolated under `/home/agent/temp`.
- Compose drops Linux capabilities and re-adds only a narrow set needed by the sudo wrappers, binds exposed ports to `127.0.0.1`, and applies CPU, memory, and process limits. `no-new-privileges` is intentionally not enabled on the workspace service because it would disable the constrained sudo wrappers used for allowlisted package installs.
- OpenCode is installed at image build time from a pinned npm package version instead of at container startup.
- GitHub CLI is installed from a pinned GitHub release asset with SHA-256 verification.
- The agent cannot use broad `sudo apt-get install` or arbitrary privileged process controls; it can only run `sudo agent-apt-install` for packages in `config/apt-package-allowlist.txt` and `sudo agent-kill-port` for non-privileged TCP ports.
- The entrypoint generates OpenCode provider config from environment variables with `jq` so model names and URLs are not hardcoded into project code.

This is a defense-in-depth sandbox, not a VM-grade security boundary. For stronger host isolation, run Docker rootless or inside a dedicated VM.

## Shielded Image Strengths

- **Host containment:** the agent sees one writable project mount, one read-only shared mount, and one disposable temp mount.
- **Non-root default:** OpenCode and generated project commands run as `agent`, not root.
- **Pinned supply chain:** Python, uv, Node.js, OpenCode, GitHub CLI, and Ollama defaults are version-pinned.
- **Constrained escalation:** runtime elevation is limited to root-owned wrappers for allowlisted apt packages and explicit port cleanup.
- **Small network surface:** Docker publishes only allowlisted ports, and each published port is bound to `127.0.0.1`.
- **Secret hygiene:** GitHub tokens are optional runtime environment values, generated projects get local `.env` files, and checks include a lightweight committed-secret scan.
- **Operational audit trail:** project and sandbox log directories are present, and each development cycle is documented in `docs/`.

## Prerequisites

- Docker and Docker Compose
- One of the supported LLM backends:
  - **LM Studio** serving an OpenAI-compatible API on the host (default, port 1234)
  - **FastFlowLM** for AMD Ryzen AI NPU inference (port 52625)
  - **Ollama** via the included Docker Compose profile (port 11434)
- A configured `.env` file based on `.env.example`

## Configuration

Create a local environment file:

```bash
cp .env.example .env
```

Required fields:

- `PROJECT_NAME`: simple directory name for the active project.
- `PROJECTS_ROOT_PATH`: absolute host directory where coding projects live.
- `SHARED_SYSTEM_PATH`: absolute host directory mounted read-only into the container.
- `TEMP_PATH`: absolute host directory for caches and disposable state.
- `LLM_SOURCE`: one of `lm_studio`, `fastflow_amd`, or `ollama_docker`.
- `LM_STUDIO_MODEL`, `FASTFLOW_MODEL`, or `OLLAMA_MODEL`: set the one matching `LLM_SOURCE`.
- `LLM_PORT`: LLM server port (defaults: 1234 for LM Studio, 52625 for FastFlowLM, 11434 for Ollama).
- `LM_STUDIO_API_KEY`: optional Bearer token when LM Studio authentication is enabled.
- `OLLAMA_KEEP_ALIVE`: how long Ollama keeps a model loaded (default `5m`).
- `OLLAMA_NUM_GPU`: GPU layers to offload (default `999` = all, `0` = CPU only).
- `OPENCODE_PORT`: local host port for OpenCode web.
- `GIT_USERNAME` and `GIT_EMAIL`: Git identity configured inside the container.
- `GITHUB_TOKEN` or `GH_TOKEN`: optional GitHub token for `gh` and HTTPS GitHub operations. Use fine-grained, least-privilege tokens.

Validate configuration before launching:

```bash
make validate
```

Print pinned tool versions:

```bash
make versions
```

List runtime-installable apt packages:

```bash
make allowlist
```

List exposed-port allowlist:

```bash
make ports
```

Run local security/config checks:

```bash
make check
```

## Run

Start the sandbox:

```bash
make run
```

Open the web UI:

```text
http://localhost:${OPENCODE_PORT}
```

The launch flow creates or updates the active project under:

```text
${PROJECTS_ROOT_PATH}/${PROJECT_NAME}
```

Each generated project receives:

- `AGENTS.md`
- `.env` with `LLM_BASE_URL`, `LLM_MODEL_NAME`, and `APP_PORT`
- `Makefile`
- `src/<package_name>/`
- `docs/`, `artifacts/`, `logs/`, and `skills/`

## Operation Modes

The sandbox supports two interface types and three operation modes, controlled by `OPENCODE_INTERFACE` and `OPERATION_MODE` in `.env`.

### Interactive Mode — Web UI (default)

```bash
make run
```

The standard mode. OpenCode starts a web UI at `http://localhost:${OPENCODE_PORT}`. The user interacts with the coding agent through the browser.

### Interactive Mode — Terminal TUI

```bash
make run-tui
```

For users who prefer the terminal. OpenCode starts a full terminal UI directly in your shell. No browser or port required. The container runs interactively and exits when you quit the TUI.

### Autonomous Mode

```bash
make run-autonomous
```

Fire-and-forget mode. Place a project specification as a Markdown file in the project directory, set `TASK_FILE` in `.env` to its filename, and run. The agent reads the spec, plans, implements, tests, and iterates until the project is complete. All tool calls are auto-approved. The container exits when done.

Example `.env` configuration:

```
OPERATION_MODE=autonomous
TASK_FILE=project_spec.md
```

Output goes to `logs/autonomous.log` in the project directory. The agent generates `docs/development_cycle_X.md` at each phase and `docs/final_report.md` when complete.

### Conductor Mode

```bash
make run-conductor
```

A frontier AI coding agent (e.g., Claude Code, Gemini CLI, Codex, Antigravity, or any MCP-compatible tool) acts as the architect, while the local LLM (e.g., Gemma 4, Qwen, Llama) does the development work inside the sandbox. The external agent sends high-level instructions, the local agent executes them, and reports back — saving tokens on the expensive model.

The sandbox starts an MCP bridge server that the external agent connects to as a remote MCP server.

**Setup:**

1. Start the sandbox in conductor mode:

```bash
make run-conductor
```

2. Add the MCP server to your AI coding tool's configuration:

```json
{
  "mcp": {
    "sandbox-agent": {
      "type": "remote",
      "url": "http://localhost:8443/mcp"
    }
  }
}
```

3. Use the `delegate_task` tool from your AI coding agent:

```
You: "Build a FastAPI server that transcribes YouTube audio using Whisper"

Your AI agent calls: delegate_task(instructions="Initialize a Python project with uv.
  Add yt-dlp, transformers, torch, fastapi, uvicorn as dependencies.
  Create src/my_app/settings.py with configurable constants...")

Local agent (Gemma/Qwen): executes the task, writes code, returns summary

Your AI agent: reviews the output, calls delegate_task again with fixes or next steps
```

**Available tools:**

| Tool | Description |
|---|---|
| `delegate_task` | Send instructions to the local agent. Returns the agent's full response. Persistent session retains context across calls. |
| `read_project_file` | Read any file in the project directory. |
| `list_project_files` | List or search files by path or pattern. |
| `get_project_status` | Git status and recent commits. |
| `abort_task` | Cancel a currently running task. |

**Tips for effective orchestration:**

- **Use 9B+ parameter models** for the local agent. 4B models work but struggle with multi-step tool chains and occasionally generate malformed tool calls.
- **Send single-step instructions.** Instead of "fix this, restart, and verify," send three separate `delegate_task` calls. Small models handle atomic tasks much better than compound ones.
- **Review after each delegation.** Use `read_project_file` to inspect what the local agent wrote before sending the next instruction. Catch bugs early.
- **Be explicit about tool usage.** If the local agent's edit tool fails, tell it to use the write tool instead. Small models sometimes pick the wrong tool.
- **Start with project setup.** Delegate dependency installation and project structure first, verify it's correct, then move to implementation.
- **Break implementation into files.** Delegate one file at a time: settings, then core logic, then API endpoints. Don't ask for the entire project in one shot.

## MCP Servers

OpenCode supports external tools via the Model Context Protocol (MCP). To configure MCP servers, create a JSON file and set `MCP_CONFIG_FILE` in `.env`:

```
MCP_CONFIG_FILE=config/mcp-servers.json
```

The file is merged into `opencode.json` at container startup. See `config/mcp-example.json` for the format:

```json
{
  "filesystem": {
    "type": "local",
    "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/home/agent/projects"],
    "enabled": true
  }
}
```

For MCP servers running on the host, add their ports to `config/port-allowlist.txt` and expose them in `docker-compose.yml`. MCP servers running inside the container (local stdio) need no port changes.

## Operations

```bash
make build            # build the workspace image with pinned versions
make check            # run config, shell, compose, and secret-pattern checks
make scan             # scan built image for HIGH/CRITICAL CVEs with Trivy
make run-tui          # start with terminal TUI instead of web UI
make run-autonomous   # run in autonomous mode (task file, exits when done)
make run-conductor    # start conductor mode (MCP bridge for external AI agents)
make run-restricted   # start with restricted network (no internet egress)
make logs             # follow container logs
make stop             # stop containers
make clean-cache      # remove temp/cache files
make delete-project
make nuke-all
```

`delete-project` and `nuke-all` remove project data. Review `PROJECT_NAME` and `PROJECTS_ROOT_PATH` before running them.

## Repository Standards

- Read `CONTRIBUTING.md` before changing security-sensitive files.
- Read `SECURITY.md` before changing sandbox boundaries, tokens, ports, or install policy.
- Architecture and operational checks are summarized in `docs/architecture.md`.
- Run `make check` before every commit.
- Update `docs/development_cycle_X.md` when behavior, policy, docs, or operator workflow changes.

## Security Hardening

The workspace container applies defense-in-depth controls that are enabled by default or toggleable via `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `SECCOMP_PROFILE` | `config/seccomp-workspace.json` | Custom seccomp syscall filter. Set to `unconfined` to disable. |
| `SECRET_SCAN_STRICT` | `true` | Expanded secret pattern scan (AWS, private keys, JWT, Slack). |
| `NETWORK_EGRESS` | `restricted` | Documented network mode. Use `make run-restricted` for enforcement. |
| `HEALTHCHECK_INTERVAL` | `30s` | Healthcheck polling interval for both services. |
| `LOG_MAX_SIZE` | `50m` | Docker log rotation max size per file. |
| `LOG_MAX_FILE` | `5` | Docker log rotation max file count. |
| `ULIMIT_NOFILE` | `4096` | File descriptor soft limit. |
| `ULIMIT_NPROC` | `256` | Process count soft limit. |
| `PORTSCAN_ENABLED` | `false` | Periodic port scan monitoring inside the container. |
| `PORTSCAN_INTERVAL` | `300` | Port scan interval in seconds. |
| `RESOURCE_MONITOR_ENABLED` | `false` | Periodic memory and process snapshots. |
| `RESOURCE_MONITOR_INTERVAL` | `60` | Resource snapshot interval in seconds. |
| `AUTOLOG_ENABLED` | `false` | Hourly security summary report generation. |
| `DASHBOARD_ENABLED` | `false` | Static HTML monitoring dashboard on a separate port. |
| `DASHBOARD_PORT` | `8080` | Dashboard HTTP server port. |
| `DASHBOARD_REFRESH_INTERVAL` | `30` | Dashboard regeneration interval in seconds. |

Always-on controls (not toggleable):

- **Read-only root filesystem** with targeted tmpfs mounts for `/tmp`, `/var/tmp`, `/home/agent/.config`, `/home/agent/.cache`, `/home/agent/.local`, `/run`, `/var/lib/apt`, and `/var/cache/apt`.
- **Core dumps disabled** via ulimit.
- **Explicit environment pass-through** — only required variables reach the container (no host paths or build-time values leaked).
- **Log rotation** on all Docker service logs.
- **Healthchecks** on both workspace and LLM backend services.
- **Graceful signal handling** — SIGTERM propagates to monitoring processes.

When runtime monitoring is enabled, structured JSONL logs are written to the project's `logs/` directory:

- `logs/portscan.jsonl` — port listener scan results.
- `logs/resources.jsonl` — timestamped process and memory snapshots.
- `logs/security_summary.jsonl` — hourly aggregated summaries.

When `DASHBOARD_ENABLED=true`, a static HTML dashboard is generated from these logs and served on `http://localhost:${DASHBOARD_PORT}`. The dashboard auto-refreshes and shows project info, memory/process charts, port scan results, and security summaries — conditionally based on which monitoring features are enabled. Monitoring and dashboard are only available in web and autonomous modes, not TUI.

## Build-Time Controls

The Dockerfile exposes build args:

- `NODE_MAJOR`, default `22`
- `NODE_VERSION`, default `22.22.2-1nodesource1`
- `OPENCODE_VERSION`, default `1.15.10`
- `GH_VERSION`, default `2.92.0`
- `UV_IMAGE`, default `ghcr.io/astral-sh/uv:0.11.16`
- `PYTHON_BASE_IMAGE`, default `python:3.13.13-slim-bookworm`
- `HOST_UID`, `HOST_GID`

To update OpenCode, bump `OPENCODE_VERSION`, rebuild, and review the resulting image behavior before using it on important repositories.

## System Package Policy

The image preinstalls common software development tools for Python, backend, data, and AI workflows, including `curl`, `wget`, `git`, `gh`, `uv`, `cmake`, `make`, `ripgrep`, `jq`, `tree`, `vim`, `nano`, `tmux`, `htop`, `shellcheck`, `sqlite3`, `ffmpeg`, `rsync`, `openssh-client`, and common native libraries used by Python packages.

At runtime, the agent may install only exact package names listed in `config/apt-package-allowlist.txt`:

```bash
sudo agent-apt-install ffmpeg libgl1
```

If a package is not allowlisted, update `config/apt-package-allowlist.txt` and the Dockerfile after user review, then rebuild. Do not grant broad `apt-get` sudo access.

## Port Policy

The workspace exposes only ports listed in `config/port-allowlist.txt`, and Compose binds them to `127.0.0.1` so they are reachable from the host only. Defaults are:

- `OPENCODE_PORT=3000` for the OpenCode web UI.
- `APP_PORT=7860` for one agent-built local app.
- `DASHBOARD_PORT=8080` for the optional monitoring dashboard.
- `MCP_BRIDGE_PORT=8443` for the conductor mode MCP bridge.
- `LLM_PORT=1234` for LM Studio, `52625` for FastFlowLM, or `11434` for the optional Ollama profile.

All other host ports should remain unmapped. If a project needs another port, add it to `config/port-allowlist.txt` after review, run `make validate`, and rebuild/restart.

## Logs

Generated projects include a `logs/` directory for application logs. The root `logs/` directory is reserved for sandbox operation logs, and `make logs` follows Docker service logs. Do not paste secrets into reports or logs; `make check` includes a lightweight committed-secret pattern scan.

## Skills

Place Markdown files in `skills/` to provide reusable task-specific guidance. During project initialization, the root `skills/` directory is copied into the generated project, and `AGENTS.md` instructs the agent to read relevant skill files at the start of a development cycle.
