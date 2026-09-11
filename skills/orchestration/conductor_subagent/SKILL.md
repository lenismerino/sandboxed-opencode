---
name: conductor_subagent
description: Guidelines for operating as an autonomous subagent orchestrated by an external frontier AI model.
version: 1.0.0
category: orchestration
tags: [conductor, subagent, mcp, delegation]
tools_required: [read_file, patch_file, run_command]
model_compatibility:
  min_context_window: 16384
  requires_reasoning: true
  recommended_profiles: [gemma-4-e4b, qwen-3.5-9b]
---

# Conductor Subagent Skill

## When To Use
- When operating in `OPERATION_MODE=conductor`.
- When receiving atomic tasks delegated via the MCP bridge.

## Procedure
1. **Direct Execution**: Never ask conversational questions; execute the prompt immediately.
2. **Inspect Before Changing**: Read target code using `read_file` before writing patches.
3. **Run Self-Verification**:
   - `uv run ruff format .`
   - `uv run ruff check --fix .`
   - `uv run pytest`
4. **Structured Status Report**:
   Return concise summary using the required Conductor format:
   ```markdown
   ### Changes Made
   - [Modified] path/to/file.py (description)

   ### Verification & Tests
   - Formatting & Linting: [Pass/Fail]
   - Tests: [Pass/Fail]
   ```
