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

## Known Boundaries

The workspace container starts as a non-root user, but it intentionally includes constrained sudo wrappers for allowlisted apt installs and port cleanup. This means Docker `no-new-privileges` is not enabled for the workspace service. The sandbox reduces host exposure but is not equivalent to a separate VM security boundary.
