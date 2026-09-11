#!/usr/bin/env python3
"""Zero-Config Auto-Discovery & Setup Wizard for sandboxed-opencode.

Automatically scans for local or LAN inference servers (LM Studio, Ollama),
detects loaded models (Google Gemma 4 E4B, Qwen, etc.), pairs them with
the optimal Model Profile, and configures .env for instant plug-and-play usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
PROFILES_DIR = CONFIG_DIR / "model_profiles"
DOTENV_PATH = ROOT_DIR / ".env"
DOTENV_EXAMPLE = ROOT_DIR / ".env.example"

# Candidate servers to probe
CANDIDATE_ENDPOINTS = [
    {"source": "lm_studio", "host": "127.0.0.1", "port": 1234, "desc": "LM Studio (Localhost)"},
    {"source": "lm_studio", "host": "192.168.1.3", "port": 1234, "desc": "LM Studio (Private LAN)"},
    {"source": "ollama_docker", "host": "127.0.0.1", "port": 11434, "desc": "Ollama (Localhost)"},
    {"source": "fastflow_amd", "host": "127.0.0.1", "port": 52625, "desc": "FastFlowLM (NPU)"},
]


def probe_endpoint(host: str, port: int, timeout: int = 2) -> Optional[Dict[str, Any]]:
    """Probe an HTTP endpoint for model information."""
    url = f"http://{host}:{port}/v1/models"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sandboxed-opencode-quickstart"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                return {"url": url, "models": models, "host": host, "port": port}
    except Exception:
        pass
    return None


def match_model_profile(model_id: str) -> str:
    """Find the best matching model profile for a detected model ID."""
    m_lower = model_id.lower()
    if "gemma-4" in m_lower or "gemma4" in m_lower:
        return "gemma-4-e4b"
    if "qwen3.5" in m_lower or "qwen-3.5" in m_lower or "qwen/qwen3.5" in m_lower:
        return "qwen-3.5-9b"
    if "qwen" in m_lower and ("4b" in m_lower or "3-4b" in m_lower or "qwen3:4b" in m_lower):
        return "qwen-3-4b"
    # Fallback to gemma-4-e4b as default flagship
    return "gemma-4-e4b"


def configure_dotenv(
    host: str,
    port: int,
    source: str,
    model_id: str,
    profile_name: str,
    dry_run: bool = False,
) -> None:
    """Write or update .env with auto-discovered values."""
    template = DOTENV_EXAMPLE.read_text(encoding="utf-8") if DOTENV_EXAMPLE.exists() else ""
    target_env = DOTENV_PATH if DOTENV_PATH.exists() else DOTENV_EXAMPLE

    lines = target_env.read_text(encoding="utf-8").splitlines()
    updates = {
        "MODEL_PROFILE": profile_name,
        "LLM_HOST": host,
        "LLM_PORT": str(port),
        "LLM_SOURCE": source,
    }
    if source == "lm_studio":
        updates["LM_STUDIO_MODEL"] = model_id
    elif source == "ollama_docker":
        updates["OLLAMA_MODEL"] = model_id

    new_lines: List[str] = []
    seen_keys = set()

    for line in lines:
        matched = False
        for k, v in updates.items():
            if re.match(rf"^{k}\s*=", line):
                new_lines.append(f"{k}={v}")
                seen_keys.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    # Append any remaining keys
    for k, v in updates.items():
        if k not in seen_keys:
            new_lines.append(f"{k}={v}")

    output_content = "\n".join(new_lines) + "\n"

    if dry_run:
        print("\n--- [DRY RUN] Generated .env Configuration ---")
        for k, v in updates.items():
            print(f"  {k}={v}")
        return

    DOTENV_PATH.write_text(output_content, encoding="utf-8")
    # Set permissions to 600
    try:
        os.chmod(DOTENV_PATH, 0o600)
    except Exception:
        pass
    print(f"\n✓ Successfully updated {DOTENV_PATH} (permissions set to 600).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-detect local/LAN LLM servers and configure sandbox.")
    parser.add_argument("--dry-run", action="store_true", help="Display discovered settings without modifying .env")
    parser.add_argument("--custom-host", help="Probe a specific custom host IP or hostname")
    parser.add_argument("--custom-port", type=int, help="Probe a specific custom port")
    args = parser.parse_args()

    print("=== Sandboxed OpenCode Zero-Config Auto-Discovery ===")
    print("Probing local and LAN inference servers...\n")

    endpoints_to_probe = list(CANDIDATE_ENDPOINTS)
    if args.custom_host:
        port = args.custom_port or 1234
        endpoints_to_probe.insert(
            0, {"source": "lm_studio", "host": args.custom_host, "port": port, "desc": f"Custom ({args.custom_host}:{port})"}
        )

    found_server = None
    for cand in endpoints_to_probe:
        host, port, desc = cand["host"], cand["port"], cand["desc"]
        print(f"  Checking {desc} ({host}:{port})...", end="", flush=True)
        res = probe_endpoint(host, port)
        if res and res.get("models"):
            print(" FOUND!")
            found_server = {**cand, **res}
            break
        else:
            print(" (no response)")

    if not found_server:
        print("\n✗ No active local LLM endpoints detected.")
        print("Ensure LM Studio or Ollama is running and has the local server enabled.")
        print("Supported defaults: LM Studio at 127.0.0.1:1234 or 192.168.1.3:1234, Ollama at 127.0.0.1:11434.")
        return 1

    models = found_server.get("models", [])
    print(f"\n✓ Connected to {found_server['desc']}!")
    print(f"  Available models: {', '.join(models)}")

    # Pick the best coding model
    chosen_model = models[0]
    for m in models:
        if "gemma-4" in m.lower():
            chosen_model = m
            break
        if "qwen" in m.lower():
            chosen_model = m

    matched_profile = match_model_profile(chosen_model)
    print(f"\n  Selected Model:  {chosen_model}")
    print(f"  Matched Profile: {matched_profile}")
    print(f"  Inference Host:  {found_server['host']}:{found_server['port']}")

    configure_dotenv(
        host=found_server["host"],
        port=found_server["port"],
        source=found_server["source"],
        model_id=chosen_model,
        profile_name=matched_profile,
        dry_run=args.dry_run,
    )

    print("\nSandbox is ready to run!")
    print("  To launch Web UI:       make run")
    print("  To launch Terminal UI:  make run-tui")
    print("  To run live tests:      make test-model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
