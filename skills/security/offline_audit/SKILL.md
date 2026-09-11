---
name: offline_audit
description: Perform comprehensive static security audits offline without external network or SaaS scanning dependencies.
version: 1.0.0
category: security
tags: [security, offline-audit, owasp, path-traversal, injection, static-analysis]
tools_required: [grep_search, read_file, patch_file, run_command]
model_compatibility:
  min_context_window: 16384
  requires_reasoning: true
  recommended_profiles: [gemma-4-e4b, qwen-3.5-9b]
---

# Offline Security Audit Skill

## When To Use
- Prior to creating release branches or major commits.
- When validating input handlers, file system access, shell execution, or web endpoints.
- When operating in strict offline/air-gapped environments without internet access to external CVE scanners.

## Key Vulnerability Patterns to Inspect
1. **Path Traversal**:
   - Check all file operations (`open`, `Path.read_text`, `os.path.join`) for un-sanitized user inputs or lack of `resolve().relative_to(...)` bounds checks.
2. **Command Injection**:
   - Check all `subprocess.run`, `os.system`, or `run_command` invocations for `shell=True` or unescaped string interpolations.
3. **SSRF / Host Escapes**:
   - Verify network requests (`urllib.request`, `httpx`, `requests`) do not accept arbitrary user-controlled URLs without host/port allowlisting.
4. **Hardcoded Secrets / Tokens**:
   - Scan for raw API keys, bearer tokens, passwords, and private certificates in non-ignored files.
5. **Insecure Deserialization**:
   - Scan for unsafe `pickle.loads()`, `yaml.load()` without SafeLoader, or `eval()`/`exec()`.

## Procedure
1. **Static Grep Sweep**:
   - Run grep sweeps across the codebase for dangerous keywords:
     ```bash
     grep -rnE "(shell=True|os\.system|eval\(|exec\(|pickle\.loads)" src/ tools/ harness/
     ```
2. **Path Boundary Verification**:
   - Ensure all file path arguments enforce project boundary containment:
     ```python
     target = (base_dir / user_path).resolve()
     if not target.is_relative_to(base_dir.resolve()):
         raise ValueError("Path traversal attempt detected")
     ```
3. **Automated Sandbox Check**:
   - Execute the sandbox security test suite:
     ```bash
     ./scripts/security_check.sh
     ```
4. **Remediate Findings**:
   - Refactor vulnerable calls using safe alternatives (`subprocess.run(["cmd", "arg"], shell=False)`).
   - Re-verify using tests to confirm zero regressions.
