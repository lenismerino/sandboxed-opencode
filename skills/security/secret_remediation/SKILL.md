---
name: secret_remediation
description: Detect, redact, and migrate hardcoded credentials and tokens to secure environment variables.
version: 1.0.0
category: security
tags: [security, credentials, secrets, redaction]
tools_required: [grep_search, read_file, patch_file, run_command]
model_compatibility:
  min_context_window: 16384
  requires_reasoning: true
  recommended_profiles: [gemma-4-e4b, qwen-3.5-9b]
---

# Secret Remediation Skill

## When To Use
- When `scripts/security_check.sh` fails due to potential committed secrets.
- During security audits prior to git commits.

## Pre-flight Invariants
- Never print full secret values into logs or stdout.

## Procedure
1. **Audit Detection**: Run `./scripts/security_check.sh` or use `grep_search` with credential regex patterns.
2. **Environment Variable Abstraction**:
   - Move the credential to `.env` or fetch dynamically using `os.environ.get("...")`.
   - Update `.env.example` with a placeholder key.
3. **Patch Code**: Use `patch_file` to replace the hardcoded token with the `os.environ` call.
4. **Git Scrubbing**: If the credential was already committed, notify the operator immediately to rotate the credential.
5. **Verification**: Re-run `./scripts/security_check.sh` to confirm zero secret leaks.
