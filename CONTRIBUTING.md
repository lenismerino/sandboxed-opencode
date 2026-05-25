# Contributing

This repository is security-sensitive infrastructure for a local coding-agent sandbox. Treat changes to Docker, Compose, sudo rules, exposed ports, dependencies, and generated project templates as security changes.

## Development Workflow

1. Create or update `.env` from `.env.example`.
2. Run `make validate` before launching the sandbox.
3. Run `make check` before committing.
4. For Docker changes, run `make build` and a short image smoke test.
5. Update `docs/development_cycle_X.md` for meaningful behavior, policy, or operator-facing changes.

## Security-Sensitive Files

- `Dockerfile`
- `docker-compose.yml`
- `entrypoint.sh`
- `new_project.sh`
- `AGENTS.md`
- `config/apt-package-allowlist.txt`
- `config/port-allowlist.txt`
- `scripts/agent-apt-install`
- `scripts/agent-kill-port`
- `scripts/validate_config.sh`
- `scripts/security_check.sh`

## Dependency Policy

- Pin versions for images, npm packages, and downloaded release assets.
- Prefer official repositories and signed or checksum-verified artifacts.
- Do not install npm or system packages at container startup.
- Runtime apt installs must go through `sudo agent-apt-install` and the checked-in allowlist.

## Secrets

Never commit `.env`, tokens, private keys, cloud credentials, or copied contents from the read-only shared mount. Redact tokens in logs, docs, reports, and examples.
