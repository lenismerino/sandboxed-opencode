---
name: fast_refactor
description: Safely refactor Python modules using atomic patches and self-verification.
version: 1.0.0
category: coding
tags: [refactor, python, patch, ruff]
tools_required: [read_file, patch_file, run_command]
model_compatibility:
  min_context_window: 16384
  requires_reasoning: true
  recommended_profiles: [gemma-4-e4b, qwen-3.5-9b]
---

# Fast Refactor Skill

## When To Use
- Renaming functions, variables, or interfaces across a codebase.
- Splitting monolithic functions or classes into smaller modular components.
- Modernizing Python syntax to Python 3.13 idioms (e.g. `type` aliases, modern pattern matching).

## Pre-flight Invariants
1. Check git status to ensure working directory is clean: `git status --porcelain`.
2. Run baseline test suite: `uv run pytest -q`. If baseline fails, resolve failures before refactoring.

## Procedure
1. **Target Inspection**: Read the target file in full using `read_file`.
2. **Callers Discovery**: Search for all callers across the repository using `grep_search`.
3. **Atomic Modification**:
   - For targeted replacements, use `patch_file` with unique before-and-after text blocks.
   - Do NOT rewrite unrelated docstrings, formatting, or unaffected functions.
4. **Immediate Verification**:
   - Format: `uv run ruff format .`
   - Lint & Fix: `uv run ruff check --fix .`
   - Type check: `uv run mypy .`
   - Test suite: `uv run pytest -v`

## Rollback Strategy
If tests fail and the root cause is ambiguous, revert using git:
`git checkout -- path/to/file.py` and formulate a new hypothesis.
