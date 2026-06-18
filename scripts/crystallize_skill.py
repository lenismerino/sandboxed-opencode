#!/usr/bin/env python3
"""Crystallize agent skills from logs and git history using the local LLM.

Usage:
  python3 crystallize_skill.py <skill_name>
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_DIR = Path("/home/agent/projects")
DOTENV_PATH = PROJECT_DIR / ".env"
LOGS_DIR = PROJECT_DIR / "logs"
SKILLS_DIR = PROJECT_DIR / "skills"


def load_dotenv() -> None:
    if not DOTENV_PATH.exists():
        return
    with open(DOTENV_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key not in os.environ:
                    os.environ[key] = val


def get_git_log() -> str:
    try:
        res = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            capture_output=True,
            text=True,
            cwd=PROJECT_DIR,
            timeout=5,
        )
        return res.stdout.strip()
    except Exception as e:
        return f"Could not read git history: {e}"


def get_autonomous_log() -> str:
    log_file = LOGS_DIR / "autonomous.log"
    if not log_file.exists():
        return "No autonomous log found."
    try:
        # Read last 10,000 bytes/chars to stay within reasonable model prompt window
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
            if len(content) > 10000:
                return "... [TRUNCATED] ...\n" + content[-10000:]
            return content
    except Exception as e:
        return f"Could not read log file: {e}"


def main() -> None:
    if len(sys.argv) < 2:
        print("Error: skill name argument is required.", file=sys.stderr)
        print("Usage: python3 crystallize_skill.py <skill_name>", file=sys.stderr)
        sys.exit(1)

    skill_name = sys.argv[1]
    # Clean the skill name to only alphanumeric and underscores/hyphens
    skill_name_clean = "".join(c for c in skill_name if c.isalnum() or c in ("-", "_")).lower()
    if not skill_name_clean:
        print("Error: invalid skill name.", file=sys.stderr)
        sys.exit(1)

    load_dotenv()

    llm_base_url = os.environ.get("LLM_BASE_URL")
    llm_model = os.environ.get("LLM_MODEL_NAME")

    if not llm_base_url or not llm_model:
        print("Error: LLM_BASE_URL and LLM_MODEL_NAME must be configured in environment or project .env", file=sys.stderr)
        sys.exit(1)

    print("Gathering operational context...")
    git_history = get_git_log()
    log_context = get_autonomous_log()

    prompt = f"""You are an expert AI software engineer. Analyze the logs and git history of a successful software development cycle. Extract the repeatable procedures, patterns, or commands into a reusable skill instruction.

Follow this standard structure strictly:
# Skill Name

## When To Use
Describe the specific scenario, package, or task triggers when this skill should be invoked.

## Procedure
List the step-by-step commands or coding edits required. Keep them clear, robust, and minimal.

## Validation
List the verification tests, logs, or command-line outputs that prove the procedure succeeded.

---
Operational Logs:
{log_context}

---
Git Commit History:
{git_history}
"""

    print(f"Calling LLM ({llm_model}) to distill skill...")
    payload = {
        "model": llm_model,
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant specialized in writing clear agent skills."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    req_url = f"{llm_base_url.rstrip('/')}/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        req_url,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            res_body = json.loads(resp.read().decode("utf-8"))
            skill_content = res_body["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        print(f"Error calling LLM at {req_url}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error parsing LLM response: {e}", file=sys.stderr)
        sys.exit(1)

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = SKILLS_DIR / f"{skill_name_clean}.md"
    out_file.write_text(skill_content, encoding="utf-8")

    print(f"Success! Crystallized skill written to: {out_file}")


if __name__ == "__main__":
    main()
