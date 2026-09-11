# Tools Architecture & Registry

This directory defines the sandbox tools available to AI coding agents operating in autonomous mode, harness evaluations, and MCP conductor bridge.

## Security Constraints
Every tool exposed to an agent must enforce:
1. **Path Traversal Protection**: Filesystem tools must resolve paths relative to the active project root and disallow escapes (`..`, symlinks outside project).
2. **Deterministic Schemas**: Tool parameters use the standard OpenAI Function JSON schema format.
3. **Execution Timeouts**: Shell commands executed via `run_command` are bounded by strict timeouts (default 120 seconds).
4. **No Destructive Escapes**: Destructive root commands and shell bombs are rejected prior to execution.

## Built-In Tools
- `read_file(path)`: Inspect source code and documentation.
- `write_file(path, content)`: Create or replace files within the project.
- `patch_file(path, find_text, replace_text)`: Perform surgical, atomic block replacements.
- `list_files(path, pattern)`: Discover project files and folder structure.
- `grep_search(query, path)`: Fast ripgrep text and regex search across project files.
- `run_command(command)`: Execute builds, linters (`ruff check`), formatters (`ruff format`), and tests (`pytest`).
