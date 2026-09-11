#!/usr/bin/env python3
"""CLI runner for LongTaskSupervisor executing unattended long tasks with auto-rotation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.model_client import ModelClient
from harness.supervisor import LongTaskSupervisor
from tools.registry import ToolRegistry


def load_profile(profile_name: str) -> dict:
    profile_path = REPO_ROOT / "config" / "model_profiles" / f"{profile_name}.json"
    if not profile_path.exists():
        print(f"Error: Profile '{profile_name}' not found at {profile_path}", file=sys.stderr)
        sys.exit(1)
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run unattended engineering tasks with the LongTaskSupervisor")
    parser.add_argument("--task", "-t", type=str, default="Implement and verify project features according to specifications.", help="Task goal or specification")
    parser.add_argument("--task-file", "-f", type=str, help="Path to markdown specification file containing task requirements")
    parser.add_argument("--profile", "-p", type=str, default=os.environ.get("MODEL_PROFILE", "gemma-4-e4b"), help="Model profile to load")
    parser.add_argument("--host", type=str, default=os.environ.get("LLM_HOST", "192.168.1.3"), help="Inference server host IP")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LLM_PORT", "1234")), help="Inference server port")
    parser.add_argument("--max-turns-per-phase", type=int, default=15, help="Max turns per milestone phase")
    parser.add_argument("--max-sessions", type=int, default=5, help="Max session rotations before halting")

    args = parser.parse_args()

    task_goal = args.task
    if args.task_file:
        tf_path = Path(args.task_file)
        if not tf_path.is_absolute():
            tf_path = REPO_ROOT / args.task_file
        if tf_path.exists():
            task_goal = tf_path.read_text(encoding="utf-8")
        else:
            print(f"Warning: Task file '{args.task_file}' not found, using task string instead.", file=sys.stderr)

    profile = load_profile(args.profile)
    base_url = f"http://{args.host}:{args.port}/v1"
    model_id = profile.get("model_id", "google/gemma-4-e4b")

    print(f"============================================================")
    print(f"  sandboxed-opencode: Long Task Unattended Supervisor")
    print(f"============================================================")
    print(f"Active Profile : {args.profile} ({model_id})")
    print(f"Endpoint       : {base_url}")
    print(f"Context Window : {profile.get('context_window', {}).get('max_context_length', 131072):,} tokens")
    print(f"Auto-Compaction: Enabled (>80% utilization)")
    print(f"Auto-Rotation  : Enabled (>90% utilization or phase boundary)")
    print(f"============================================================\n")

    client = ModelClient(profile=profile, base_url=base_url)
    project_dir = Path(os.environ.get("PROJECTS_ROOT_PATH", "/home/agent/projects"))
    if not project_dir.exists():
        project_dir = REPO_ROOT

    tools = ToolRegistry(project_dir=project_dir)

    def on_step(info: dict) -> None:
        p = info.get("phase", "General")
        s = info.get("step", 0)
        t = info.get("elapsed", 0.0)
        tc_count = len(info.get("tool_calls") or [])
        print(f"  [{p} | Step {s}] Elapsed: {t:.2f}s | Tools: {tc_count}")

    supervisor = LongTaskSupervisor(
        model_client=client,
        tool_registry=tools,
        profile=profile,
        project_dir=project_dir,
        max_turns_per_phase=args.max_turns_per_phase,
        max_sessions=args.max_sessions,
        on_step_callback=on_step,
    )

    print(f"Starting execution for goal:\n{task_goal[:200]}...\n")
    report = supervisor.run_unattended_task(goal=task_goal)

    print(f"\n============================================================")
    print(f"  Task Finished: Status = {report['status'].upper()}")
    print(f"============================================================")
    print(f"Phases Completed : {report['phases_completed']}/{report['total_phases']}")
    print(f"Total Steps      : {report['total_steps']}")
    print(f"Duration         : {report['duration_seconds']}s")
    t_summary = report.get("telemetry", {})
    print(f"Token Velocity   : {t_summary.get('token_velocity_tps', 0.0)} t/s")
    print(f"Reasoning Ratio  : {t_summary.get('reasoning_ratio', 0.0) * 100:.1f}%")
    print(f"Context Utilized : {t_summary.get('context_utilization_pct', 0.0)}%")
    print(f"State Saved To   : logs/agent_state.json")
    print(f"============================================================\n")


if __name__ == "__main__":
    main()
