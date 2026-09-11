---
name: pytest_hardening
description: Systematically build comprehensive, robust unit and integration tests.
version: 1.0.0
category: testing
tags: [testing, pytest, coverage, mocking]
tools_required: [read_file, write_file, run_command]
model_compatibility:
  min_context_window: 16384
  requires_reasoning: true
  recommended_profiles: [gemma-4-e4b, qwen-3.5-9b]
---

# Pytest Hardening Skill

## When To Use
- Adding test coverage for newly created features or endpoints.
- Writing regression tests after diagnosing a bug.
- Testing edge cases, invalid inputs, and error boundaries.

## Pre-flight Invariants
1. Identify target module and its external dependencies.
2. Determine if external dependencies (e.g. network, filesystem) should be mocked using `unittest.mock` or `tmp_path`.

## Procedure
1. **Analyze Interface**: Read target module using `read_file`. Map all public methods, parameter types, and possible exception types.
2. **Draft Test File**: Create `tests/test_<module_name>.py` following standard test structure:
   - Happy path tests.
   - Boundary condition tests (empty strings, zero values, maximum lengths).
   - Error handling and exception tests (`pytest.raises`).
   - Mocked external interactions (`monkeypatch` or `unittest.mock.patch`).
3. **Execute and Measure**:
   - Run tests: `uv run pytest -v tests/test_<module_name>.py`
   - Measure coverage: `uv run pytest --cov=src -v`
4. **Iterate**: Address any assertion failures or uncaught exceptions immediately.
