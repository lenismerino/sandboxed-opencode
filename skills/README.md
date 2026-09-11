# Skills Architecture & Organizational System

Skills are modular, repeatable domain capabilities that guide the AI coding agent through standardized workflows.

## Taxonomy & Directory Layout

Skills can be placed directly as Markdown files (`skills/<skill_name>.md`) or organized in domain directories with a `SKILL.md`:

```
skills/
├── README.md
├── coding/
│   └── fast_refactor/
│       └── SKILL.md
├── testing/
│   └── pytest_hardening/
│       └── SKILL.md
├── security/
│   └── secret_remediation/
│       └── SKILL.md
└── orchestration/
    └── conductor_subagent/
        └── SKILL.md
```

## Standard Frontmatter Specification

Every skill begins with YAML frontmatter to allow programmatic indexing, model capability matching, and tool validation:

```yaml
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
```

## Skill Structure
Following frontmatter, each skill defines:
1. **Trigger Signals**: When to activate this procedure.
2. **Pre-flight Invariants**: What must be verified before making edits.
3. **Execution Steps**: Concrete, incremental operational steps.
4. **Verification & Hardening**: Strict automated commands (`ruff check`, `pytest`).
5. **Rollback Strategy**: How to recover if validation fails.
