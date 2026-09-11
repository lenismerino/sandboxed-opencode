# Skills, Tools & Plugins System

This guide explains how to author, categorize, and extend domain skills, sandboxed tools, and lifecycle plugins.

## 1. Skills System

Skills teach the AI coding agent standard project operating procedures.

### Location & Organization
```
skills/
├── coding/
│   └── fast_refactor/SKILL.md
├── testing/
│   └── pytest_hardening/SKILL.md
├── security/
│   └── secret_remediation/SKILL.md
└── orchestration/
    └── conductor_subagent/SKILL.md
```

### Frontmatter Schema
```yaml
---
name: my_procedure
description: Clear, 1-line description of when and why to invoke.
version: 1.0.0
category: coding
tags: [optimization, python]
tools_required: [read_file, patch_file, run_command]
model_compatibility:
  min_context_window: 16384
  requires_reasoning: true
---
```

### Managing Skills
```bash
# List all registered skills
make skills
# or
./scripts/skills_manager.py list

# Validate all skills frontmatter
./scripts/skills_manager.py validate
```

### Skill Crystallization
To extract a repeatable workflow from recent git commits and logs into a skill file:
```bash
python3 scripts/crystallize_skill.py my_new_skill
```

---

## 2. Tools Architecture

Tools are sandbox-isolated operations exposed to agent loops, harness runs, and conductor mode.

### Invariants & Boundaries
- **Path Traversal Shield**: Paths are strictly checked against `PROJECT_DIR`.
- **Command Whitelisting**: Forbidden destructive commands (`rm -rf /`, fork bombs) are rejected.
- **Strict Timeouts**: Commands time out after 120s to prevent hanging loops.

---

## 3. Plugins & Hooks Architecture

Plugins hook into agent loop execution events (`plugins/hooks/`):
- `on_task_start(task_instruction, model_profile)`
- `on_step_complete(step_record)`
- `on_task_finish(task_result)`

### Built-in: Token Telemetry
`plugins/hooks/token_telemetry.py` logs structured metrics to `logs/telemetry.jsonl` tracking step latency, token count, and context utilization.
