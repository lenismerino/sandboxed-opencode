# Development Cycle 3: Renamed 'opencoder' to 'opencode' everywhere

Date: 2026-05-25

## Scope

Changed all occurrences of the old name 'opencoder' (e.g., `xl-sandboxed-opencoder`) to 'opencode' (`xl-sandboxed-opencode`) in the workspace, documents, script templates, and Docker configs to establish a consistent, polished brand.

## Changes Implemented

- Updated `AGENTS.md` to reference `xl-sandboxed-opencode` in the introduction.
- Updated `Dockerfile` comment header with `xl-sandboxed-opencode`.
- Updated `README.md` title and first-paragraph description to `xl-sandboxed-opencode`.
- Updated `new_project.sh` workspace template config headers and initialization welcome messages to use `xl-sandboxed-opencode`.

## Security Notes

- No changes were made to sandbox boundaries, port controls, or package allowlists.
- Re-verified configuration validation and execution constraints remain completely intact.

## Validation Evidence

- Executed `make check` successfully:
  - Configuration is valid.
  - Security checks passed.
- Conducted case-insensitive grep checks confirming 0 occurrences of 'opencoder' remain across the entire workspace.
