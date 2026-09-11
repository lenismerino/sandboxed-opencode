#!/usr/bin/env python3
"""Skills Manager & Validator for sandboxed-opencode.

Parses, validates, and indexes skills with YAML frontmatter.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"


def parse_skill_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Extract YAML frontmatter and markdown body from a skill file."""
    content = file_path.read_text(encoding="utf-8", errors="replace")
    if not content.startswith("---"):
        # Legacy skill without frontmatter
        return {
            "name": file_path.stem,
            "description": "Legacy skill without YAML frontmatter",
            "file_path": str(file_path),
            "category": "legacy",
            "body": content,
        }

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    frontmatter_raw = parts[1]
    body = parts[2].strip()

    # Simple line-by-line YAML parser without external dependencies
    metadata: Dict[str, Any] = {"file_path": str(file_path), "body": body}
    for line in frontmatter_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                # Parse list of strings
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                metadata[key] = items
            elif val.lower() in ("true", "false"):
                metadata[key] = val.lower() == "true"
            else:
                metadata[key] = val.strip("'\"")

    return metadata


def discover_skills(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan and return all skills within the skills directory."""
    target_root = root or SKILLS_ROOT
    skills: List[Dict[str, Any]] = []
    if not target_root.is_dir():
        return skills

    for path in sorted(target_root.rglob("*.md")):
        if path.name == "README.md":
            continue
        skill = parse_skill_file(path)
        if skill:
            skills.append(skill)
    return skills


def validate_skills() -> bool:
    """Validate all skills for required metadata."""
    skills = discover_skills()
    if not skills:
        print("No skills found.")
        return True

    all_valid = True
    print(f"\n--- Validating {len(skills)} Skill(s) in {SKILLS_ROOT} ---")
    for s in skills:
        name = s.get("name", "unnamed")
        errs = []
        if "description" not in s or not s["description"]:
            errs.append("Missing 'description'")
        if "category" not in s:
            errs.append("Missing 'category'")

        if errs:
            all_valid = False
            print(f"✗ {name} ({s['file_path']}): {', '.join(errs)}")
        else:
            print(f"✓ {name} [{s.get('category')}] - {s.get('description')[:60]}...")

    return all_valid


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage and inspect sandboxed skills.")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("list", help="List all discovered skills")
    sub.add_parser("validate", help="Validate skills frontmatter")

    args = parser.parse_args()

    if args.cmd == "validate":
        ok = validate_skills()
        return 0 if ok else 1

    # Default: list
    skills = discover_skills()
    print(f"\n{'NAME':<25} {'CATEGORY':<15} {'TOOLS REQUIRED':<25} {'DESCRIPTION'}")
    print("-" * 90)
    for s in skills:
        name = s.get("name", "unknown")
        cat = s.get("category", "general")
        tools = ", ".join(s.get("tools_required", [])) or "none"
        desc = s.get("description", "")[:50]
        print(f"{name:<25} {cat:<15} {tools:<25} {desc}")
    print(f"\nTotal: {len(skills)} skill(s) registered.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
