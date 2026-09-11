#!/usr/bin/env python3
"""Model Profile Management CLI for xl-sandboxed-opencode.

Provides utilities to list, validate, inspect, test, and export model profiles.
Includes live endpoint connectivity tests for models like Google Gemma 4 E4B,
Qwen, and local Ollama instances.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "model_profiles"
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "config" / "model-profile-schema.json"


def load_profile(profile_name: str) -> Dict[str, Any]:
    """Load a model profile JSON file by name.

    Args:
        profile_name: Name of the profile (e.g. 'gemma-4-e4b' or 'gemma-4-e4b.json').

    Returns:
        Dictionary containing profile configuration.

    Raises:
        FileNotFoundError: If profile file does not exist.
        ValueError: If file is not valid JSON.
    """
    clean_name = profile_name[:-5] if profile_name.endswith(".json") else profile_name
    profile_path = PROFILES_DIR / f"{clean_name}.json"
    if not profile_path.is_file():
        raise FileNotFoundError(f"Model profile '{profile_name}' not found at {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def list_profiles() -> List[Dict[str, Any]]:
    """List all available model profiles with high-level summaries.

    Returns:
        List of profile summary dictionaries.
    """
    profiles: List[Dict[str, Any]] = []
    if not PROFILES_DIR.is_dir():
        return profiles

    for path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                profiles.append(
                    {
                        "profile_name": data.get("profile_name", path.stem),
                        "display_name": data.get("display_name", path.stem),
                        "model_id": data.get("model_id", "unknown"),
                        "provider": data.get("provider", "unknown"),
                        "max_context": data.get("context_window", {}).get("max_context_length", 0),
                        "reasoning": data.get("reasoning", {}).get("supported", False),
                        "tool_calling": data.get("tool_calling", {}).get("supported", False),
                        "file_path": str(path),
                    }
                )
        except Exception as err:
            sys.stderr.write(f"Warning: Failed to load profile {path}: {err}\n")

    return profiles


def validate_profile(data: Dict[str, Any]) -> List[str]:
    """Validate a profile dictionary against required fields and ranges.

    Args:
        data: Profile configuration dictionary.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors: List[str] = []
    required_keys = [
        "profile_name",
        "display_name",
        "model_id",
        "provider",
        "context_window",
        "sampling",
        "reasoning",
        "tool_calling",
        "system_prompt",
        "harness_profile",
    ]
    for key in required_keys:
        if key not in data:
            errors.append(f"Missing required top-level key: '{key}'")

    cw = data.get("context_window", {})
    if not isinstance(cw, dict) or "max_context_length" not in cw:
        errors.append("context_window must be an object containing 'max_context_length'")
    elif cw.get("max_context_length", 0) < 1024:
        errors.append("context_window.max_context_length must be >= 1024")

    sampling = data.get("sampling", {})
    if not isinstance(sampling, dict) or "temperature" not in sampling:
        errors.append("sampling must be an object containing 'temperature'")

    return errors


def test_endpoint(
    profile_data: Dict[str, Any],
    base_url: str,
    timeout: int = 60,
    api_key: Optional[str] = None,
) -> bool:
    """Execute live capability tests against the configured model endpoint.

    Tests:
    1. HTTP connectivity and model discovery (/models)
    2. Basic inference and reasoning trace extraction
    3. Function/tool calling
    4. Structured JSON output

    Args:
        profile_data: Loaded profile configuration.
        base_url: Base URL of the OpenAI-compatible endpoint (e.g. http://192.168.1.3:1234/v1).
        timeout: Request timeout in seconds.
        api_key: Optional API key.

    Returns:
        True if all critical tests pass, False otherwise.
    """
    model_id = profile_data["model_id"]
    sampling = profile_data.get("sampling", {})
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"\n--- Running Live Profile Tests for '{profile_data['display_name']}' ---")
    print(f"Target Base URL: {base_url}")
    print(f"Target Model ID: {model_id}\n")

    # Test 1: Models endpoint
    models_url = f"{base_url.rstrip('/')}/models"
    print(f"[1/4] Checking model visibility at {models_url}...")
    try:
        req = urllib.request.Request(models_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            available_ids = [m.get("id") for m in data.get("data", [])]
            if model_id in available_ids:
                print(f"  ✓ Model '{model_id}' found in available models list.")
            else:
                print(
                    f"  ! Model '{model_id}' not explicitly found in list: {available_ids}. Proceeding anyway..."
                )
    except Exception as err:
        print(f"  ✗ Connection check failed: {err}")
        return False

    # Test 2: Basic completion & reasoning trace
    chat_url = f"{base_url.rstrip('/')}/chat/completions"
    print(f"[2/4] Testing basic completion and reasoning...")
    payload_basic = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": profile_data.get("system_prompt", "You are a helpful assistant.")},
            {"role": "user", "content": "Briefly state your name, architecture, and developer in 1 sentence."},
        ],
        "temperature": sampling.get("temperature", 0.2),
        "top_p": sampling.get("top_p", 0.95),
        "max_tokens": 500,
    }
    if "top_k" in sampling:
        payload_basic["top_k"] = sampling["top_k"]

    t0 = time.time()
    try:
        req = urllib.request.Request(
            chat_url,
            data=json.dumps(payload_basic).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            elapsed = time.time() - t0
            choice = resp_data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            reasoning = msg.get("reasoning_content") or ""
            content = msg.get("content") or ""
            usage = resp_data.get("usage", {})

            print(f"  ✓ Response received in {elapsed:.2f}s")
            if reasoning:
                print(f"  ✓ Reasoning trace captured ({len(reasoning)} chars, {usage.get('completion_tokens_details', {}).get('reasoning_tokens', 0)} tokens)")
            print(f"  ✓ Output preview: {content.strip()[:100]}...")
    except Exception as err:
        print(f"  ✗ Basic completion failed: {err}")
        return False

    # Test 3: Tool calling
    tool_spec = profile_data.get("tool_calling", {})
    if tool_spec.get("supported", False):
        print(f"[3/4] Testing native function/tool calling...")
        test_tools = [
            {
                "type": "function",
                "function": {
                    "name": "check_service_status",
                    "description": "Check if a sandbox daemon is currently active.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Name of daemon service"}
                        },
                        "required": ["service_name"],
                    },
                },
            }
        ]
        payload_tool = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": "Check if service 'mcp-bridge' is active using check_service_status."},
            ],
            "tools": test_tools,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": 500,
        }
        try:
            req = urllib.request.Request(
                chat_url,
                data=json.dumps(payload_tool).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                choice = resp_data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    first_call = tool_calls[0].get("function", {})
                    fn_name = first_call.get("name")
                    fn_args = first_call.get("arguments")
                    print(f"  ✓ Tool call generated: {fn_name}({fn_args})")
                else:
                    print(f"  ! Model did not emit tool_calls: {msg.get('content', '')[:100]}")
        except Exception as err:
            print(f"  ✗ Tool calling test failed: {err}")
    else:
        print("[3/4] Tool calling marked unsupported in profile. Skipping.")

    # Test 4: Structured Output (JSON schema)
    struct_spec = profile_data.get("structured_output", {})
    if struct_spec.get("supported", False):
        print(f"[4/4] Testing structured JSON schema output...")
        payload_struct = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": "Report test status for module 'harness'."},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "module_status",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "module": {"type": "string"},
                            "status": {"type": "string", "enum": ["healthy", "degraded", "offline"]},
                            "checks_passed": {"type": "integer"},
                        },
                        "required": ["module", "status", "checks_passed"],
                        "additionalProperties": False,
                    },
                },
            },
            "temperature": 0.1,
            "max_tokens": 500,
        }
        try:
            req = urllib.request.Request(
                chat_url,
                data=json.dumps(payload_struct).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                choice = resp_data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                parsed = json.loads(content)
                print(f"  ✓ Structured JSON parsed successfully: {parsed}")
        except Exception as err:
            print(f"  ✗ Structured output test failed: {err}")
    else:
        print("[4/4] Structured output marked unsupported. Skipping.")

    print("\n✓ Live test sequence completed.")
    return True


def export_opencode_config(profile_data: Dict[str, Any], base_url: Optional[str] = None) -> Dict[str, Any]:
    """Generate OpenCode provider configuration dictionary from a model profile.

    Args:
        profile_data: Loaded profile configuration.
        base_url: Optional base URL override.

    Returns:
        OpenCode-compatible configuration dictionary.
    """
    url = base_url or profile_data.get("default_base_url", "http://127.0.0.1:1234/v1")
    model_id = profile_data["model_id"]
    provider_id = profile_data["provider"]
    display_name = profile_data.get("display_name", model_id)

    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_id: {
                "npm": "@ai-sdk/openai-compatible",
                "name": display_name,
                "options": {
                    "baseURL": url,
                },
                "models": {
                    model_id: {
                        "name": model_id,
                        "limit": {
                            "context": profile_data.get("context_window", {}).get("max_context_length", 131072),
                            "output": profile_data.get("context_window", {}).get("reserved_completion_tokens", 8192),
                        },
                    }
                },
            }
        },
        "model": f"{provider_id}/{model_id}",
    }
    return config


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Manage model profiles for sandboxed-opencode.")
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # list
    subparsers.add_parser("list", help="List all available model profiles")

    # show
    show_p = subparsers.add_parser("show", help="Show profile details")
    show_p.add_argument("profile", help="Profile name (e.g. gemma-4-e4b)")

    # validate
    val_p = subparsers.add_parser("validate", help="Validate profile structure")
    val_p.add_argument("profile", nargs="?", default=None, help="Optional profile name (default: all)")

    # test
    test_p = subparsers.add_parser("test", help="Run live capabilities test on endpoint")
    test_p.add_argument("profile", nargs="?", default="gemma-4-e4b", help="Profile name (default: gemma-4-e4b)")
    test_p.add_argument("--host", default=None, help="Host IP or name override (e.g. 192.168.1.3)")
    test_p.add_argument("--port", type=int, default=None, help="Port override (e.g. 1234)")
    test_p.add_argument("--url", default=None, help="Full base URL override")
    test_p.add_argument("--api-key", default=None, help="Optional Bearer token")
    test_p.add_argument("--timeout", type=int, default=60, help="Request timeout seconds")

    # export-opencode
    exp_p = subparsers.add_parser("export-opencode", help="Export OpenCode configuration JSON")
    exp_p.add_argument("profile", help="Profile name")
    exp_p.add_argument("--url", default=None, help="Base URL override")

    args = parser.parse_args()

    if args.subcommand == "list" or args.subcommand is None:
        profiles = list_profiles()
        print(f"\n{'PROFILE NAME':<20} {'PROVIDER':<15} {'CONTEXT':<10} {'REASONING':<11} {'MODEL ID'}")
        print("-" * 80)
        for p in profiles:
            print(
                f"{p['profile_name']:<20} {p['provider']:<15} {p['max_context']:<10} "
                f"{str(p['reasoning']):<11} {p['model_id']}"
            )
        print(f"\nTotal: {len(profiles)} profile(s) available in {PROFILES_DIR}\n")
        return 0

    if args.subcommand == "show":
        try:
            data = load_profile(args.profile)
            print(json.dumps(data, indent=2))
            return 0
        except Exception as err:
            sys.stderr.write(f"Error: {err}\n")
            return 1

    if args.subcommand == "validate":
        targets = [args.profile] if args.profile else [p["profile_name"] for p in list_profiles()]
        all_ok = True
        for name in targets:
            try:
                data = load_profile(name)
                errs = validate_profile(data)
                if errs:
                    all_ok = False
                    print(f"✗ {name}:")
                    for e in errs:
                        print(f"  - {e}")
                else:
                    print(f"✓ {name} is valid.")
            except Exception as err:
                all_ok = False
                print(f"✗ {name}: {err}")
        return 0 if all_ok else 1

    if args.subcommand == "test":
        try:
            data = load_profile(args.profile)
            base_url = args.url
            if not base_url:
                host = args.host or os.environ.get("LLM_HOST") or "192.168.1.3"
                port = args.port or int(os.environ.get("LLM_PORT", "1234"))
                base_url = f"http://{host}:{port}/v1"

            success = test_endpoint(
                profile_data=data,
                base_url=base_url,
                timeout=args.timeout,
                api_key=args.api_key,
            )
            return 0 if success else 1
        except Exception as err:
            sys.stderr.write(f"Error: {err}\n")
            return 1

    if args.subcommand == "export-opencode":
        try:
            data = load_profile(args.profile)
            cfg = export_opencode_config(data, base_url=args.url)
            print(json.dumps(cfg, indent=2))
            return 0
        except Exception as err:
            sys.stderr.write(f"Error: {err}\n")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
