# Security Policy

## Supported Use

This project is intended for local, private development with a local OpenAI-compatible model endpoint. It is not designed to expose OpenCode, generated applications, or model servers directly to a public network.

## Reporting Security Issues

Do not open a public issue with exploit details or secrets. Report privately to the repository owner or maintainer using the private channel configured for the project.

## Operator Responsibilities

- Bind published ports to `127.0.0.1`.
- Keep Docker Desktop, Docker Engine, and the host OS patched.
- Prefer Docker rootless mode or a dedicated VM for stronger isolation.
- Use fine-grained GitHub tokens with minimum required permissions.
- Review all additions to `config/apt-package-allowlist.txt` and `config/port-allowlist.txt`.
- Rebuild after changing pinned versions or allowlists.
- Run `make check` before every commit.
- Run `make scan` periodically to check the built image for known CVEs.

## Container Hardening Controls

The workspace container enforces multiple layers of defense:

- **Read-only root filesystem** with targeted tmpfs mounts for runtime-writable paths.
- **Custom seccomp profile** (`config/seccomp-workspace.json`) blocking dangerous syscalls such as `ptrace`, `mount`, `reboot`, kernel module loading, and swap management.
- **Capability dropping** — all capabilities dropped, only `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `KILL`, `SETGID`, and `SETUID` re-added for the constrained sudo wrappers.
- **Resource limits** — CPU, memory, PID, file descriptor, and process count limits. Core dumps are disabled.
- **Log rotation** — Docker json-file driver with configurable size and count limits to prevent disk exhaustion.
- **Healthchecks** — both workspace and LLM backend services are monitored for responsiveness.
- **Explicit environment pass-through** — only variables needed by the container are injected. Host paths, build-time image tags, and SHA checksums are excluded.
- **Graceful shutdown** — SIGTERM is trapped and forwarded to monitoring processes.

## Optional Runtime Monitoring

When enabled via `.env`, background monitoring scripts run inside the container:

- **Port scanning** (`PORTSCAN_ENABLED`) — detects unexpected TCP listeners.
- **Resource snapshots** (`RESOURCE_MONITOR_ENABLED`) — captures process and memory state periodically.
- **Security reports** (`AUTOLOG_ENABLED`) — aggregates monitoring data into hourly summaries.

## Network Egress

By default, the workspace container has full outbound internet access (required for `uv add`, `pip install`, etc.). For hardened deployments where the agent should only reach the local LLM endpoint, use `make run-restricted` to switch to an internal-only Docker network.

## MCP Security Considerations

MCP servers extend the agent's capabilities by connecting to external tools and services. Operators should review MCP configurations carefully:

- **Local MCP servers** (stdio) run inside the container as the `agent` user. They inherit the sandbox's filesystem and network restrictions.
- **Remote MCP servers** (HTTP) can be reached if the container has network egress. Use `make run-restricted` to block outbound access when remote MCP is not needed.
- **Host MCP servers** require their ports added to `config/port-allowlist.txt` and exposed in `docker-compose.yml`. Each new port is a security change — review before adding.
- MCP config files should not contain secrets inline. Use environment variable references (`{env:VAR_NAME}`) for API keys and tokens.

## Dashboard

When `DASHBOARD_ENABLED=true`, a Python HTTP server runs on `DASHBOARD_PORT` (default 8080) serving a static HTML page generated from monitoring logs. The server is bound to `0.0.0.0` inside the container but Compose maps it to `127.0.0.1` on the host. The dashboard displays only aggregate metrics (memory usage, process counts, port scan results) — no secrets or credentials are included.

## Conductor Mode Security

In conductor mode (`OPERATION_MODE=conductor`), an MCP bridge server runs on `MCP_BRIDGE_PORT` (default 8443) and accepts JSON-RPC requests from any local client. The bridge forwards instructions to OpenCode's internal serve API. The `delegate_task` tool allows the external orchestrator to send arbitrary prompts to the local agent, which has full filesystem access within the sandbox. All container security controls remain active. The MCP bridge port is bound to `127.0.0.1` on the host.

## Autonomous Mode Security

In autonomous mode (`OPERATION_MODE=autonomous`), all tool calls are auto-approved via `--dangerously-skip-permissions`. The agent can read, write, delete files, and run arbitrary shell commands within the sandbox. The container's security controls (read-only root, capability dropping, seccomp, resource limits) remain active and are the primary defense layer in this mode.

## Known Boundaries

The workspace container starts as a non-root user, but it intentionally includes constrained sudo wrappers for allowlisted apt installs and port cleanup. This means Docker `no-new-privileges` is not enabled for the workspace service. The read-only root filesystem with tmpfs mounts for `/var/lib/apt` and `/var/cache/apt` allows runtime apt installs to function, but installed packages are ephemeral and lost on container restart. The sandbox reduces host exposure but is not equivalent to a separate VM security boundary.
