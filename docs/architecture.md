# Architecture

## Components

- **Host:** Runs Docker, LM Studio or another OpenAI-compatible model endpoint, and owns the mounted project directories.
- **Workspace container:** Runs OpenCode as the non-root `agent` user and mounts exactly one active project at `/home/agent/projects`. Supports two operation modes: interactive (web UI) and autonomous (headless task execution).
- **Optional LLM container:** Runs Ollama behind a Compose profile when `LLM_SOURCE=ollama_docker`.
- **Generated projects:** Receive `AGENTS.md`, `.env`, `Makefile`, `src/`, `docs/`, `artifacts/`, `logs/`, and `skills/`.

## LLM Provider Support

| Provider | Transport | Default Port | Tool Calling | MCP | Auth |
|---|---|---|---|---|---|
| LM Studio | OpenAI-compatible `/v1` | 1234 | Yes | Yes (via API) | Optional Bearer token |
| FastFlowLM | OpenAI-compatible `/v1` | 52625 | Yes | No | No |
| Ollama | OpenAI-compatible `/v1` | 11434 | Yes | No (needs bridge) | No |

## Interface & Operation Modes

- **Web UI** (`OPENCODE_INTERFACE=web`, default): OpenCode starts a browser-based UI at `localhost:${OPENCODE_PORT}`. Use `make run`.
- **Terminal TUI** (`OPENCODE_INTERFACE=tui`): OpenCode starts a terminal UI directly in the shell. No browser or port needed. Use `make run-tui`.
- **Autonomous** (`OPERATION_MODE=autonomous`): OpenCode runs `opencode run` with a task file, auto-approves all tool calls, and exits when complete. Use `make run-autonomous`.
- **Conductor** (`OPERATION_MODE=conductor`): A frontier AI coding agent (e.g., Claude Code, Gemini CLI, Codex, Antigravity) orchestrates the local agent via an MCP bridge. OpenCode runs headless (`opencode serve`), and the MCP bridge server exposes tools for task delegation, file reading, and project status. Use `make run-conductor`.

## Data Flow

1. The operator configures `.env`.
2. `make run` (or `make run-autonomous`) validates configuration and initializes the active project.
3. Compose starts the workspace with local-only port bindings.
4. `entrypoint.sh` generates OpenCode provider config from environment variables, optionally merging MCP server configuration.
5. OpenCode connects to LM Studio, FastFlowLM, or Ollama through the configured OpenAI-compatible endpoint.
6. In autonomous mode, OpenCode processes the task file and exits. In interactive mode, the web UI stays running.

## MCP Integration

External tools are configured via `MCP_CONFIG_FILE` pointing to a JSON file. The entrypoint merges this into `opencode.json` at startup. OpenCode supports local (stdio) and remote (HTTP) MCP servers natively.

## Security Controls

- Non-root container user with UID/GID validation.
- Read-only root filesystem with targeted tmpfs mounts.
- Custom seccomp profile blocking dangerous syscalls (`config/seccomp-workspace.json`).
- Capability dropping (all dropped, narrow set re-added for sudo wrappers).
- One read/write project mount.
- Optional read-only shared mount.
- Disposable temp/cache mount.
- Pinned toolchain versions with SHA-256 verification.
- Local-only exposed ports validated against `config/port-allowlist.txt`.
- Runtime apt installs mediated by `sudo agent-apt-install` and `config/apt-package-allowlist.txt`.
- Explicit environment variable pass-through (no host paths or build-time values leaked).
- Resource limits: CPU, memory, PIDs, file descriptors, process count, core dumps disabled.
- Log rotation on all Docker service logs.
- Healthchecks on workspace and LLM backend services.
- Graceful signal handling with SIGTERM trap.
- Lightweight secret-pattern scan through `make check` (core + expanded patterns).
- Optional runtime monitoring: port scanning, resource snapshots, security reports (JSONL format).
- Optional monitoring dashboard served on a separate port (static HTML with SVG charts).
- Restricted network mode available via `make run-restricted`.
- Image vulnerability scanning via `make scan` (Trivy).

## Operational Checks

Use these commands before starting work:

```bash
make validate
make check
make versions
make ports
make allowlist
make scan
```
