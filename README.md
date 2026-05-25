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
- LM Studio serving an OpenAI-compatible API on the host, or the optional Ollama Compose profile
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

## Operations

```bash
make build        # build the workspace image with pinned versions
make check        # run config, shell, compose, and secret-pattern checks
make logs         # follow container logs
make stop         # stop containers
make clean-cache  # remove temp/cache files
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

## Build-Time Controls

The Dockerfile exposes build args:

- `NODE_MAJOR`, default `22`
- `NODE_VERSION`, default `22.22.2-1nodesource1`
- `OPENCODE_VERSION`, default `0.6.6`
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
- `LLM_PORT=1234` for LM Studio, or `11434` for the optional Ollama profile.

All other host ports should remain unmapped. If a project needs another port, add it to `config/port-allowlist.txt` after review, run `make validate`, and rebuild/restart.

## Logs

Generated projects include a `logs/` directory for application logs. The root `logs/` directory is reserved for sandbox operation logs, and `make logs` follows Docker service logs. Do not paste secrets into reports or logs; `make check` includes a lightweight committed-secret pattern scan.

## Skills

Place Markdown files in `skills/` to provide reusable task-specific guidance. During project initialization, the root `skills/` directory is copied into the generated project, and `AGENTS.md` instructs the agent to read relevant skill files at the start of a development cycle.
