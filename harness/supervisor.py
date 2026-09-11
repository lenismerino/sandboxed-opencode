"""Supervisor for unattended, long-running multi-phase engineering tasks."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from harness.context import ContextManager
from harness.evaluator import TaskEvaluator
from harness.model_client import ModelClient
from harness.session import SessionManager
from harness.telemetry import TelemetryTracker
from tools.registry import ToolRegistry


class LongTaskSupervisor:
    """Supervises long-running, complex tasks across multiple autonomous sessions.

    Maintains execution continuity through:
    1. Phased milestone progression (Discovery -> Plan -> Implement -> Verify -> Finalize).
    2. Automatic context compaction when token limits approach saturation.
    3. Automatic session rotation when context reaches capacity, carrying forward
       executive handoff documents with zero loss of critical state.
    4. Integrated verification loops (ruff, mypy, pytest) with self-correcting feedback.
    5. Live telemetry reporting for terminal dashboards and external monitors.
    """

    DEFAULT_PHASES = [
        ("Discovery", "Explore the workspace, inspect existing modules, and identify key interfaces."),
        ("Architecture & Plan", "Design the technical approach, identify modified files, and define test cases."),
        ("Implementation", "Write robust, typed production code and necessary modules."),
        ("Verification & Testing", "Run formatting, linting, and automated tests to verify correctness."),
        ("Finalization", "Perform final self-review, document changes, and summarize achievements."),
    ]

    def __init__(
        self,
        model_client: ModelClient,
        tool_registry: ToolRegistry,
        profile: Dict[str, Any],
        project_dir: Optional[Path] = None,
        max_turns_per_phase: int = 15,
        max_sessions: int = 5,
        on_step_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.profile = profile
        self.project_dir = project_dir or Path(os.environ.get("PROJECTS_ROOT_PATH", "/home/agent/projects"))
        self.max_turns_per_phase = max_turns_per_phase
        self.max_sessions = max_sessions
        self.on_step_callback = on_step_callback

        self.session_manager = SessionManager(project_dir=self.project_dir)
        self.telemetry = TelemetryTracker(project_dir=self.project_dir)
        self.evaluator = TaskEvaluator(project_dir=self.project_dir)

        cw_cfg = profile.get("context_window", {})
        harness_cfg = profile.get("harness_profile", {})

        self.context = ContextManager(
            max_context_length=cw_cfg.get("max_context_length", 131072),
            reserved_completion_tokens=cw_cfg.get("reserved_completion_tokens", 8192),
            prune_threshold_tokens=harness_cfg.get("prune_threshold_tokens", 115000),
            preserved_initial_turns=harness_cfg.get("preserved_initial_turns", 2),
            recent_turns_budget=harness_cfg.get("recent_turns_budget", 15),
        )

    def run_unattended_task(
        self,
        goal: str,
        phases: Optional[List[tuple[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Execute a long task unattended across phased milestones with auto-rotation."""
        task_phases = phases or self.DEFAULT_PHASES
        session_state = self.session_manager.start_session(goal=goal)
        self.telemetry.active_session_id = session_state.session_id

        # Register milestones in session and telemetry
        for name, desc in task_phases:
            self.session_manager.record_milestone(title=name, status="pending", details=desc)
            self.telemetry.record_milestone(title=name, status="pending", details=desc)

        sys_prompt = self.profile.get(
            "system_prompt",
            "You are an expert autonomous software engineer operating inside a secure container sandbox.",
        )
        self.context.add_message("system", sys_prompt)
        self.context.add_message("user", f"OVERALL PROJECT GOAL:\n{goal}\n\nYou will work through this task unattended.")

        tools = self.tool_registry.get_openai_tool_specs()
        total_phases_completed = 0
        phase_reports: List[Dict[str, Any]] = []
        t_global_start = time.time()

        for phase_idx, (phase_name, phase_desc) in enumerate(task_phases, start=1):
            self.session_manager.record_milestone(title=phase_name, status="in_progress")
            self.telemetry.record_milestone(title=phase_name, status="in_progress")

            phase_instruction = (
                f"### CURRENT PHASE {phase_idx}/{len(task_phases)}: {phase_name.upper()}\n"
                f"Objective: {phase_desc}\n"
                f"Proceed with this phase using appropriate tools. Once finished, summarize the outcomes."
            )
            self.context.add_message("user", phase_instruction)

            phase_steps = 0
            phase_completed = False

            while phase_steps < self.max_turns_per_phase and not phase_completed:
                phase_steps += 1
                stats = self.context.get_stats()

                # 1. Proactive Context Compaction check (>80% utilization)
                if stats["utilization_pct"] > 80.0:
                    compact_res = self.context.compact()
                    if compact_res.get("compacted"):
                        self.telemetry.record_milestone(
                            title=f"Context Compacted (Turn {self.telemetry.total_steps})",
                            status="completed",
                            details=f"Compacted {compact_res['pruned_turns']} intermediate turns",
                        )

                # 2. Session Rotation check (>90% utilization or session budget)
                if stats["utilization_pct"] > 90.0:
                    if self.session_manager.current_state and self.session_manager.current_state.session_index < self.max_sessions:
                        self.context = self.session_manager.rotate_session(
                            context=self.context,
                            next_goal=f"Resume Phase {phase_idx}: {phase_name} immediately.",
                            system_prompt=sys_prompt,
                        )
                        self.telemetry.active_session_id = self.session_manager.current_state.session_id

                # 3. Model Completion Step
                messages = self.context.get_messages()
                try:
                    result = self.model_client.complete(messages=messages, tools=tools)
                except Exception as err:
                    self.telemetry.record_step(
                        step_idx=self.telemetry.total_steps + 1,
                        elapsed_seconds=1.0,
                        error=str(err),
                    )
                    time.sleep(2)
                    continue

                content = result["content"]
                reasoning = result["reasoning_content"]
                tool_calls = result["tool_calls"]
                usage = result.get("usage", {})

                p_tokens = usage.get("prompt_tokens", 0)
                c_tokens = usage.get("completion_tokens", 0)
                r_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

                # 4. Record Telemetry
                self.telemetry.record_step(
                    step_idx=self.telemetry.total_steps + 1,
                    elapsed_seconds=result["elapsed_seconds"],
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    reasoning_tokens=r_tokens,
                    tool_calls=tool_calls,
                    context_stats=self.context.get_stats(),
                )

                if self.on_step_callback:
                    self.on_step_callback({
                        "phase": phase_name,
                        "step": phase_steps,
                        "elapsed": result["elapsed_seconds"],
                        "tool_calls": tool_calls,
                    })

                # 5. Handle model conclusion or tool execution
                if not tool_calls:
                    self.context.add_message("assistant", content, reasoning_content=reasoning)
                    # If model has no tool calls, it concluded this phase
                    phase_completed = True
                    break

                self.context.add_message("assistant", content, tool_calls=tool_calls, reasoning_content=reasoning)

                # 6. Execute Tools
                for tc in tool_calls:
                    call_id = tc.get("id", f"call_{phase_steps}")
                    fn_name = tc.get("function", {}).get("name", "unknown")
                    raw_args = tc.get("function", {}).get("arguments", "{}")

                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception as p_err:
                        self.context.add_message("tool", f"Error parsing arguments: {p_err}", tool_call_id=call_id, name=fn_name)
                        continue

                    # Record modified files
                    if fn_name in ("write_file", "patch_file") and "path" in args:
                        self.session_manager.record_modified_files([args["path"]])

                    out = self.tool_registry.execute(fn_name, args)
                    self.context.add_message("tool", out, tool_call_id=call_id, name=fn_name)

            # Verification checkpoint at end of Implementation/Testing phases
            if phase_name in ("Implementation", "Verification & Testing"):
                eval_res = self.evaluator.run_full_evaluation()
                if not eval_res.all_passed:
                    # Provide automated corrective feedback
                    diag = f"Automated evaluation reported issues:\n{eval_res.to_summary()}"
                    self.context.add_message("user", f"Verification Warning:\n{diag}\nPlease correct these issues.")

            self.session_manager.record_milestone(title=phase_name, status="completed")
            self.telemetry.record_milestone(title=phase_name, status="completed")
            total_phases_completed += 1
            phase_reports.append({"phase": phase_name, "steps": phase_steps, "status": "completed"})

        total_duration = round(time.time() - t_global_start, 2)
        summary = {
            "status": "completed" if total_phases_completed == len(task_phases) else "partial",
            "goal": goal,
            "phases_completed": total_phases_completed,
            "total_phases": len(task_phases),
            "total_steps": self.telemetry.total_steps,
            "duration_seconds": total_duration,
            "telemetry": self.telemetry.get_summary(),
            "phase_reports": phase_reports,
        }

        # Write final state report to disk
        state_file = self.project_dir / "logs" / "agent_state.json"
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
        except Exception:
            pass

        return summary
