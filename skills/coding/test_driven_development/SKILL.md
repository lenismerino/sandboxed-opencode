---
name: test_driven_development
description: Fast, disciplined Test-Driven Development (TDD) loop optimized for local reasoning models.
version: 1.0.0
category: coding
tags: [tdd, testing, pytest, reasoning]
tools_required: [read_file, write_file, patch_file, run_command]
model_compatibility:
  min_context_window: 16384
  requires_reasoning: true
  recommended_profiles: [gemma-4-e4b, qwen-3.5-9b]
---

# Test-Driven Development (TDD) Skill

## When To Use
- Implementing a new feature, algorithm, or service endpoint from scratch.
- Fixing a reported bug or edge-case regression.
- Refactoring critical logic where behavior must remain invariant.

## Principles for Local Reasoning Models
1. **Red First**: Write an executable test demonstrating the desired behavior or failing edge case before writing production code.
2. **Atomic Verification**: Run `uv run pytest -k <test_name>` immediately after writing the test to confirm it fails for the expected reason.
3. **Minimal Green Implementation**: Write the simplest code that makes the test pass. Avoid speculative over-engineering.
4. **Refactor Under Green**: Clean up formatting (`ruff format`), type hints (`mypy`), and abstractions while keeping tests passing.

## Procedure
1. **Define Test Interface**:
   - Inspect existing tests or modules with `read_file`.
   - Create or update `tests/test_<module>.py`.
2. **Execute Red Phase**:
   - Run: `uv run pytest -v tests/test_<module>.py`
   - Verify that test fails due to `NotImplementedError` or missing attribute.
3. **Implement Feature**:
   - Create or update `src/<package>/<module>.py` using `write_file` or `patch_file`.
4. **Execute Green Phase**:
   - Run: `uv run pytest -v tests/test_<module>.py`
   - Verify all tests pass.
5. **Hardening**:
   - Run: `uv run ruff format . && uv run ruff check --fix .`
   - Re-run full test suite: `uv run pytest -v`
