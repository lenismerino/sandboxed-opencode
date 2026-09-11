#!/usr/bin/env python3
"""Run autonomous evaluation tasks using the Harness and Model Profiles."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from harness.evaluator import TaskEvaluator
from harness.model_client import ModelClient
from harness.runner import AgentLoopRunner
from plugins.hooks.token_telemetry import TokenTelemetryHook
from scripts.model_profile import load_profile
from tools.registry import ToolRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute task with agent loop harness.")
    parser.add_argument("--profile", default="gemma-4-e4b", help="Model profile name (default: gemma-4-e4b)")
    parser.add_argument("--task", help="Inline task instructions")
    parser.add_argument("--task-file", help="Path to markdown task specification file")
    parser.add_argument("--host", default=None, help="LLM Host override (e.g. 192.168.1.3)")
    parser.add_argument("--port", type=int, default=None, help="LLM Port override (e.g. 1234)")
    parser.add_argument("--project-dir", default=".", help="Project root directory")
    parser.add_argument("--max-steps", type=int, default=None, help="Maximum steps override")

    args = parser.parse_args()

    task_content = ""
    if args.task:
        task_content = args.task
    elif args.task_file:
        task_path = Path(args.task_file)
        if not task_path.is_file():
            sys.stderr.write(f"Error: Task file '{args.task_file}' not found.\n")
            return 1
        task_content = task_path.read_text(encoding="utf-8")
    else:
        sys.stderr.write("Error: Must specify either --task or --task-file.\n")
        return 1

    try:
        profile_data = load_profile(args.profile)
    except Exception as err:
        sys.stderr.write(f"Error loading profile '{args.profile}': {err}\n")
        return 1

    host = args.host or os.environ.get("LLM_HOST") or "192.168.1.3"
    port = args.port or int(os.environ.get("LLM_PORT", "1234"))
    base_url = f"http://host.docker.internal:{port}/v1" if os.environ.get("IN_CONTAINER") else f"http://{host}:{port}/v1"

    print(f"=== Initializing Harness with Profile: {profile_data['display_name']} ===")
    print(f"Base URL: {base_url}")
    print(f"Context Window: {profile_data.get('context_window', {}).get('max_context_length')} tokens")
    print(f"Project Directory: {Path(args.project_dir).resolve()}\n")

    client = ModelClient(base_url=base_url, profile=profile_data)
    tools = ToolRegistry(project_dir=args.project_dir)
    telemetry = TokenTelemetryHook()

    def step_hook(record: dict) -> None:
        telemetry.on_step_complete(record)
        step = record["step"]
        elapsed = record["elapsed"]
        t_calls = [tc.get("function", {}).get("name") for tc in record.get("tool_calls", [])]
        reasoning = record.get("reasoning", "")
        print(f"Step {step:02d} [{elapsed:.2f}s]: Tools={t_calls}")
        if reasoning:
            snippet = reasoning.strip().replace("\n", " ")[:120]
            print(f"  Thinking: {snippet}...")

    runner = AgentLoopRunner(
        model_client=client,
        tool_registry=tools,
        profile=profile_data,
        max_steps=args.max_steps,
        on_step_hook=step_hook,
    )

    print("Executing task...")
    result = runner.run_task(task_instruction=task_content)
    print(f"\nTask finished with status: {result['status']}")

    if "metrics" in result:
        m = result["metrics"]
        print(f"Duration: {m.get('duration_seconds')}s | Prompt Tokens: {m.get('total_prompt_tokens')} | Completion: {m.get('total_completion_tokens')} | Reasoning Tokens: {m.get('total_reasoning_tokens')}")

    # Evaluate project state
    evaluator = TaskEvaluator(project_dir=args.project_dir)
    report = evaluator.evaluate(task_name=f"Harness execution ({args.profile})", run_ruff=False, run_pytest=False)
    print("\n" + report.summary())

    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
