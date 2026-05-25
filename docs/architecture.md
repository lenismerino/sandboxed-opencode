# Architecture

## Components

- **Host:** Runs Docker, LM Studio or another OpenAI-compatible model endpoint, and owns the mounted project directories.
- **Workspace container:** Runs OpenCode as the non-root `agent` user and mounts exactly one active project at `/home/agent/projects`.
- **Optional LLM container:** Runs Ollama behind a Compose profile when `LLM_SOURCE=ollama_docker`.
- **Generated projects:** Receive `AGENTS.md`, `.env`, `Makefile`, `src/`, `docs/`, `artifacts/`, `logs/`, and `skills/`.

## Data Flow

1. The operator configures `.env`.
2. `make run` validates configuration and initializes the active project.
3. Compose starts the workspace with local-only port bindings.
4. `entrypoint.sh` generates OpenCode provider config from environment variables.
5. OpenCode connects to LM Studio, FastFlowLM, or Ollama through the configured OpenAI-compatible endpoint.

## Security Controls

- Non-root container user with UID/GID validation.
- One read/write project mount.
- Optional read-only shared mount.
- Disposable temp/cache mount.
- Pinned toolchain versions.
- Local-only exposed ports validated against `config/port-allowlist.txt`.
- Runtime apt installs mediated by `sudo agent-apt-install` and `config/apt-package-allowlist.txt`.
- Lightweight secret-pattern scan through `make check`.

## Operational Checks

Use these commands before starting work:

```bash
make validate
make check
make versions
make ports
make allowlist
```
